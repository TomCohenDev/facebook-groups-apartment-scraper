from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import BrowserContext

from app.browser.navigation import safe_goto
from app.classifier.apartment_rules import passes_keyword_gate
from app.facebook.comment_extractor import extract_comments_from_post
from app.facebook.models import RunReport
from app.facebook.post_extractor import extract_posts_from_page
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
    max_posts = group_cfg.get("max_posts_per_run", 20)
    max_scrolls = group_cfg.get("max_scrolls", 5)
    scrape_comments = group_cfg.get("scrape_comments", True)
    max_comments = group_cfg.get("max_comments_per_post", 10)
    scrape_images = group_cfg.get("scrape_images", True)

    report = RunReport(
        group_id=group_id,
        started_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    page = await context.new_page()
    try:
        logger.info("Opening group: %s", group_id)
        ok = await safe_goto(page, group_url)
        if not ok:
            report.errors.append("Failed to navigate to group URL")
            return report

        await asyncio.sleep(3)

        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(debug_dir / "screenshot.png"), full_page=False)
            (debug_dir / "page.html").write_text(await page.content(), encoding="utf-8")

        posts = await extract_posts_from_page(
            page=page,
            group_id=group_id,
            max_posts=max_posts,
            max_scrolls=max_scrolls,
            scrape_images=scrape_images,
            seen_hashes=seen_hashes,
            debug_dir=debug_dir,
        )

        report.posts_seen = len(posts)
        report.images_found = sum(len(p.images) for p in posts)

        if scrape_comments:
            for post in posts:
                if not post.post_url:
                    continue
                if not passes_keyword_gate(post.normalized_text):
                    continue
                try:
                    comments = await extract_comments_from_post(
                        context, post.post_url, max_comments
                    )
                    post.comments = comments
                    report.comments_scraped += len(comments)
                except Exception as e:
                    report.errors.append(f"Comment error for {post.post_url}: {e}")

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
        except Exception:
            pass
    finally:
        report.finished_at = datetime.now(tz=timezone.utc).isoformat()
        await page.close()

    return report
