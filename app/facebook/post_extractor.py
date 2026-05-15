from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page

from app.browser.navigation import scroll_down
from app.facebook.models import RawImage, RawPost
from app.utils.hashing import content_hash
from app.utils.logging import get_logger
from app.utils.text import canonicalize_facebook_url, normalize_text

logger = get_logger(__name__)

_REJECT_IMG = re.compile(
    r"emoji|reaction|static|rsrc|ads|logo|avatar|s\d+x\d+", re.IGNORECASE
)


def _find_message_text(data, depth: int = 0) -> str:
    """
    Find the actual post text by looking for the Facebook message object,
    which is a dict that has both 'ranges' (list) and 'text' (str) keys.
    This pattern is stable across Facebook's rendering layers.
    """
    if depth > 12:
        return ""
    if isinstance(data, dict):
        if "ranges" in data and isinstance(data.get("text"), str) and len(data["text"]) > 10:
            return data["text"]
        for val in data.values():
            if isinstance(val, (dict, list)):
                result = _find_message_text(val, depth + 1)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = _find_message_text(item, depth + 1)
            if result:
                return result
    return ""


def _extract_stories(data, depth: int = 0) -> list[dict]:
    """Recursively find Story nodes from Facebook feed JSON."""
    if depth > 15:
        return []
    results: list[dict] = []
    if isinstance(data, dict):
        if data.get("__typename") == "Story":
            results.append(data)
            return results  # don't recurse into matched story to avoid nested dupes
        for val in data.values():
            if isinstance(val, (dict, list)):
                results.extend(_extract_stories(val, depth + 1))
    elif isinstance(data, list):
        for item in data:
            results.extend(_extract_stories(item, depth + 1))
    return results


def _collect_images(data, out: list[RawImage], depth: int = 0) -> None:
    if depth > 10:
        return
    if isinstance(data, dict):
        uri = data.get("uri") or data.get("src") or ""
        if (
            isinstance(uri, str)
            and uri.startswith("http")
            and not _REJECT_IMG.search(uri)
        ):
            w = data.get("width") or 0
            h = data.get("height") or 0
            if (w == 0 or w >= 150) and (h == 0 or h >= 150):
                out.append(RawImage(image_url=uri))
        for val in data.values():
            if isinstance(val, (dict, list)):
                _collect_images(val, out, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _collect_images(item, out, depth + 1)


def _story_to_raw_post(
    story: dict,
    group_id: str,
    seen_in_run: set[str],
    seen_hashes: set[str],
    scrape_images: bool,
) -> RawPost | None:
    text = _find_message_text(story)
    if not text:
        return None

    norm = normalize_text(text)
    if not norm:
        return None

    chash = content_hash(group_id, norm)
    if chash in seen_in_run or chash in seen_hashes:
        return None

    # owning_profile is the direct author field in group feed stories
    profile = story.get("owning_profile") or story.get("actor") or {}
    author_name = profile.get("name") if isinstance(profile, dict) else None
    author_url = profile.get("url") if isinstance(profile, dict) else None
    if author_url:
        author_url = canonicalize_facebook_url(author_url)

    post_url = story.get("url") or story.get("permalink_url")
    if post_url:
        post_url = canonicalize_facebook_url(post_url)

    ext_id = str(story.get("id") or "")

    creation_time = story.get("creation_time")
    timestamp_text = str(creation_time) if creation_time else None

    images: list[RawImage] = []
    if scrape_images:
        for att in story.get("attachments") or []:
            _collect_images(att, images)
        # deduplicate by URL
        seen_urls: set[str] = set()
        images = [img for img in images if not (img.image_url in seen_urls or seen_urls.add(img.image_url))]  # type: ignore[func-returns-value]

    return RawPost(
        group_id=group_id,
        raw_text=text,
        normalized_text=norm,
        content_hash=chash,
        post_url=post_url,
        external_post_id=ext_id or None,
        author_name=author_name,
        author_profile_url=author_url,
        timestamp_text=timestamp_text,
        images=images,
        scraped_at=datetime.now(tz=timezone.utc),
    )


def make_graphql_collector(raw_stories: list[dict]):
    """
    Returns a Playwright response handler that appends story nodes to raw_stories.
    Register this on the page BEFORE navigation so initial page load is captured.
    """
    async def handle_response(response):
        try:
            url = response.url
            # Skip static assets — they'll never contain feed data
            if "fbcdn.net" in url or "rsrc.php" in url or "static" in url:
                return
            if "facebook.com" not in url:
                return
            if response.status != 200:
                return
            text = await response.text()
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    raw_stories.extend(_extract_stories(data))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
    return handle_response


async def extract_posts_from_page(
    page: Page,
    group_id: str,
    max_posts: int,
    max_scrolls: int,
    scrape_images: bool,
    seen_hashes: set[str],
    raw_stories: list[dict] | None = None,
    debug_dir: Path | None = None,
) -> list[RawPost]:
    """
    Scroll the group feed and collect posts from intercepted GraphQL responses.
    Pass raw_stories (a list with a handler already attached) to capture data
    from the initial page load as well.
    """
    if raw_stories is None:
        raw_stories = []
        page.on("response", make_graphql_collector(raw_stories))
        await asyncio.sleep(3)

    def _story_hash(story: dict) -> str | None:
        text = _find_message_text(story)
        if not text:
            return None
        return content_hash(group_id, normalize_text(text))

    stale = 0
    processed_idx = 0
    for i in range(max_scrolls):
        before = len(raw_stories)
        await scroll_down(page, times=1, delay_ms=800)
        await asyncio.sleep(0.5)

        after = len(raw_stories)
        logger.debug("Scroll %d — stories so far: %d", i + 1, after)

        if after == before:
            stale += 1
            if stale >= 3:
                logger.debug("No new stories in 3 consecutive scrolls, stopping")
                break
        else:
            stale = 0
            # Stop early if any new story was already alerted — older posts follow
            for story in raw_stories[processed_idx:after]:
                if _story_hash(story) in seen_hashes:
                    logger.debug("Hit already-alerted post during scroll, stopping early")
                    processed_idx = after
                    stale = 99  # force exit
                    break
            processed_idx = after

        if stale >= 3:
            break

        if after >= max_posts * 3:
            break

    posts: list[RawPost] = []
    seen_in_run: set[str] = set()
    for story in raw_stories:
        chash = _story_hash(story)
        if chash and chash in seen_hashes:
            logger.debug("Hit already-alerted post in final pass, stopping")
            break
        post = _story_to_raw_post(story, group_id, seen_in_run, seen_hashes, scrape_images)
        if post:
            seen_in_run.add(post.content_hash)
            posts.append(post)
            if len(posts) >= max_posts:
                break

    logger.debug(
        "Network interception: %d raw stories → %d unique new posts",
        len(raw_stories),
        len(posts),
    )
    return posts
