from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import BrowserContext

from app.browser.navigation import safe_goto
from app.settings import settings
from app.facebook.models import RunReport
from app.facebook.post_extractor import extract_posts_from_page, make_graphql_collector
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def read_group(
    context: BrowserContext,
    group_cfg: dict,
    seen_hashes: set[str],
    debug_dir: Path | None = None,
) -> RunReport:
    group_id = group_cfg["id"]
    group_url = group_cfg["url"]
    max_posts = settings.max_posts_per_group
    max_scrolls = group_cfg.get("max_scrolls", 30)
    scrape_images = group_cfg.get("scrape_images", True)

    report = RunReport(
        group_id=group_id,
        started_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    page = await context.new_page()
    try:
        # Register handler BEFORE navigation to capture initial page-load responses
        raw_stories: list[dict] = []
        page.on("response", make_graphql_collector(raw_stories))

        logger.info("Navigating to %s", group_url)
        ok = await safe_goto(page, group_url)
        logger.debug("safe_goto returned ok=%s, current URL: %s", ok, page.url)
        if not ok:
            report.errors.append("Failed to navigate to group URL")
            return report

        await asyncio.sleep(3)
        logger.debug("Page title: %s | URL: %s", await page.title(), page.url)
        logger.debug("Stories captured from initial load: %d", len(raw_stories))

        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(debug_dir / "screenshot.png"), full_page=False)
            (debug_dir / "page.html").write_text(await page.content(), encoding="utf-8")
            logger.debug("Debug snapshot saved to %s", debug_dir)

        logger.info("Extracting posts (max=%d, max_scrolls=%d)...", max_posts, max_scrolls)
        posts = await extract_posts_from_page(
            page=page,
            group_id=group_id,
            max_posts=max_posts,
            max_scrolls=max_scrolls,
            scrape_images=scrape_images,
            seen_hashes=seen_hashes,
            raw_stories=raw_stories,
            debug_dir=debug_dir,
        )
        logger.info("Extracted %d posts for %s", len(posts), group_id)

        report.posts_seen = len(posts)
        report.images_found = sum(len(p.images) for p in posts)

        if debug_dir:
            posts_data = [
                {
                    "post_url": p.post_url,
                    "content_hash": p.content_hash,
                    "author": p.author_name,
                    "text_preview": p.normalized_text[:200],
                    "images": len(p.images),
                    "comments": len(p.comments),
                }
                for p in posts
            ]
            (debug_dir / "posts.json").write_text(
                json.dumps(posts_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        report.success = True
        report.raw_posts = posts  # type: ignore[attr-defined]

    except Exception as e:
        logger.exception("Group read failed: %s", e)
        report.errors.append(str(e))
        try:
            snap_dir = debug_dir or Path("runtime/snapshots") / group_id
            snap_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(snap_dir / "failure.png"), full_page=False)
            (snap_dir / "failure.html").write_text(
                await page.content(), encoding="utf-8"
            )
            logger.info("Failure snapshot saved to %s", snap_dir)
        except Exception:
            pass
    finally:
        report.finished_at = datetime.now(tz=timezone.utc).isoformat()
        await page.close()

    return report
