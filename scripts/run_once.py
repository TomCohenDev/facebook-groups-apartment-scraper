"""
Run a single scrape of all enabled groups.

Usage:
    python scripts/run_once.py
    python scripts/run_once.py --limit 2
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.main import process_single_group
from app.notifier.telegram import send_text
from app.settings import load_criteria_config, load_groups_config, settings
from app.storage.db import engine
from app.storage.schema import create_tables
from app.utils.logging import get_logger, setup_logging

setup_logging(settings.log_level)
logger = get_logger(__name__)


async def main(limit: int | None = None) -> None:
    run_start = datetime.now(tz=timezone.utc)
    create_tables(engine)
    groups = [g for g in load_groups_config() if g.get("enabled", True)]
    if limit:
        groups = groups[:limit]
    criteria = load_criteria_config()
    ai_cfg = criteria.get("ai", {})
    send_non_listings = ai_cfg.get("send_non_listings", False)
    ai_model = ai_cfg.get("model") or settings.ai_model

    total_scraped = 0
    total_sent = 0
    total_filtered = 0

    playwright, context = await create_context(settings.fb_profile_dir, settings.headless)
    try:
        await assert_logged_in(context)

        semaphore = asyncio.Semaphore(settings.max_concurrent_groups)
        telegram_lock = asyncio.Lock()

        tasks = [
            process_single_group(context, g, criteria, ai_model, send_non_listings, semaphore, telegram_lock)
            for g in groups
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.error("Group task failed: %s", r)
            else:
                s, sent, f = r
                total_scraped += s
                total_sent += sent
                total_filtered += f
    finally:
        await context.close()
        await playwright.stop()

    if settings.telegram_bot_token and settings.telegram_chat_id and (total_scraped or total_sent):
        elapsed = (datetime.now(tz=timezone.utc) - run_start).total_seconds()
        mins, secs = int(elapsed // 60), int(elapsed % 60)
        await send_text(
            f"✅ סיום — {total_scraped} נסרקו | {total_sent} נשלחו | {total_filtered} סוננו | {mins}m {secs}s"
        )

    logger.info("Done — scraped=%d sent=%d filtered=%d", total_scraped, total_sent, total_filtered)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max number of groups to process")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit))
