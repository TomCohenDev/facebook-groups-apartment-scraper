from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from app.browser.navigation import click_see_more, scroll_down
from app.facebook.image_extractor import extract_images_from_container
from app.facebook.models import RawPost
from app.facebook.selectors import POST_CONTAINER_SELECTORS
from app.utils.hashing import content_hash
from app.utils.logging import get_logger
from app.utils.text import canonicalize_facebook_url, normalize_text

logger = get_logger(__name__)

_POST_ID_RE = re.compile(r"/posts/(\d+)|/permalink/(\d+)|[?&]story_fbid=(\d+)")


def _extract_post_id(url: str) -> str | None:
    m = _POST_ID_RE.search(url)
    if m:
        return next(g for g in m.groups() if g)
    return None


def _find_post_url(links: list[str]) -> str | None:
    for href in links:
        if "/groups/" in href and ("/posts/" in href or "permalink" in href):
            return canonicalize_facebook_url(href)
    return None


async def extract_posts_from_page(
    page: Page,
    group_id: str,
    max_posts: int,
    max_scrolls: int,
    scrape_images: bool,
    seen_hashes: set[str],
    debug_dir: Path | None = None,
) -> list[RawPost]:
    posts: list[RawPost] = []
    seen_in_run: set[str] = set()

    for scroll_idx in range(max_scrolls):
        for selector in POST_CONTAINER_SELECTORS:
            containers = page.locator(selector)
            count = await containers.count()

            for i in range(count):
                container = containers.nth(i)

                try:
                    await click_see_more(page, container)
                except Exception:
                    pass

                try:
                    raw_text = await container.inner_text(timeout=5000)
                except Exception:
                    continue

                norm = normalize_text(raw_text)
                if not norm:
                    continue

                chash = content_hash(group_id, norm)
                if chash in seen_in_run or chash in seen_hashes:
                    continue
                seen_in_run.add(chash)

                links: list[str] = []
                try:
                    anchors = container.locator("a[href]")
                    a_count = await anchors.count()
                    for j in range(a_count):
                        href = await anchors.nth(j).get_attribute("href")
                        if href:
                            links.append(href)
                except Exception:
                    pass

                post_url = _find_post_url(links)
                ext_id = _extract_post_id(post_url) if post_url else None

                author_name: str | None = None
                author_url: str | None = None
                timestamp_text: str | None = None
                try:
                    profile_link = container.locator('a[href*="/user/"], a[href*="/profile.php"], a[href*="facebook.com/"]').first
                    author_name = await profile_link.inner_text(timeout=3000)
                    author_url = await profile_link.get_attribute("href")
                    if author_url:
                        author_url = canonicalize_facebook_url(author_url)
                except Exception:
                    pass

                try:
                    time_el = container.locator("abbr, [data-tooltip-content], span[title]").first
                    timestamp_text = await time_el.get_attribute("title") or await time_el.inner_text(timeout=2000)
                except Exception:
                    pass

                images = []
                if scrape_images:
                    try:
                        images = await extract_images_from_container(container)
                    except Exception:
                        pass

                post = RawPost(
                    group_id=group_id,
                    raw_text=raw_text,
                    normalized_text=norm,
                    content_hash=chash,
                    post_url=post_url,
                    external_post_id=ext_id,
                    author_name=author_name,
                    author_profile_url=author_url,
                    timestamp_text=timestamp_text,
                    images=images,
                    scraped_at=datetime.now(tz=timezone.utc),
                )
                posts.append(post)

                if len(posts) >= max_posts:
                    return posts

        if len(posts) >= max_posts:
            break

        await scroll_down(page, times=1, delay_ms=2500)

    return posts
