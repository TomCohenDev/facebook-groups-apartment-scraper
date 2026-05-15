"""Scheduled scraper entry point."""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import BrowserContext

from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.classifier.ai_extractor import extract_post
from app.facebook.group_reader import read_group
from app.facebook.image_extractor import download_images
from app.notifier.telegram import send_post_alert, send_text
from app.settings import load_criteria_config, load_groups_config, settings
from app.storage.db import SessionLocal, engine
from app.storage.repository import (
    get_seen_hashes,
    mark_post_alerted,
    save_post,
    upsert_group,
)
from app.storage.schema import create_tables
from app.utils.logging import get_logger, setup_logging

setup_logging(settings.log_level)
logger = get_logger(__name__)

_SEND_DELAY = 2  # seconds between Telegram messages to avoid flood control


def _passes_hard_filters(ai_result: dict | None, criteria: dict) -> bool:
    if not ai_result:
        return True
    price = ai_result.get("price_ils")
    max_price = criteria.get("price", {}).get("max")
    if price and max_price and price > max_price:
        logger.info("Skipping: price %d > max %d", price, max_price)
        return False
    return True


def _passes_date_filter(timestamp_text: str | None, criteria: dict) -> bool:
    min_date_str = criteria.get("min_date")
    if not min_date_str or not timestamp_text:
        return True
    try:
        post_dt = datetime.fromtimestamp(int(timestamp_text), tz=timezone.utc)
        min_dt = datetime.fromisoformat(min_date_str).replace(tzinfo=timezone.utc)
        if post_dt < min_dt:
            logger.info("Skipping: post date %s < min_date %s", post_dt.date(), min_date_str)
            return False
    except (ValueError, OSError):
        pass
    return True


def _qualifies(db_post, ai_result, criteria, send_non_listings) -> bool:
    return (
        bool(settings.telegram_bot_token)
        and _passes_date_filter(db_post.timestamp_text, criteria)
        and _passes_hard_filters(ai_result, criteria)
        and (send_non_listings or ai_result is None or ai_result.get("is_listing"))
    )


async def _send_with_delay(db_post, group_name, ai_result, img_data=None) -> bool:
    sent = await send_post_alert(db_post, group_name, ai_result, images=img_data or None)
    await asyncio.sleep(_SEND_DELAY)
    return sent



async def process_single_group(
    context: BrowserContext,
    group_cfg: dict,
    criteria: dict,
    ai_model: str,
    send_non_listings: bool,
    semaphore: asyncio.Semaphore,
    telegram_lock: asyncio.Lock,
) -> tuple[int, int, int]:
    """Scrape one group and process its posts. Returns (scraped, sent, filtered)."""
    async with semaphore:
        await asyncio.sleep(random.uniform(0, 1.5))

        with SessionLocal() as session:
            db_group = upsert_group(session, group_cfg)
            session.commit()
            actual_id = db_group.id
            seen = get_seen_hashes(session, actual_id)

        effective_cfg = {**group_cfg, "id": actual_id}
        report = await read_group(context, effective_cfg, seen)
        raw_posts = getattr(report, "raw_posts", [])

        scraped = 0
        sent = 0
        filtered = 0

        with SessionLocal() as session:
            for raw in raw_posts:
                db_post = save_post(session, raw)
                if db_post is None:
                    continue
                session.commit()
                scraped += 1

                ai_result = await extract_post(raw.normalized_text, criteria, model=ai_model)

                if not _qualifies(db_post, ai_result, criteria, send_non_listings):
                    filtered += 1
                    continue

                image_urls = [img.image_url for img in (raw.images or [])]
                img_data = await download_images(context, image_urls) if image_urls else []

                async with telegram_lock:
                    post_sent = await _send_with_delay(db_post, group_cfg["name"], ai_result, img_data)
                if post_sent:
                    with SessionLocal() as s2:
                        mark_post_alerted(s2, db_post.id)
                        s2.commit()
                    sent += 1

        logger.info(
            "Group %s — scraped=%d sent=%d errors=%d",
            group_cfg["id"], report.posts_seen, sent, len(report.errors),
        )
        return scraped, sent, filtered


async def run_all_groups(criteria: dict) -> None:
    run_start = datetime.now(tz=timezone.utc)
    groups = [g for g in load_groups_config() if g.get("enabled", True)]
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


async def main() -> None:
    create_tables(engine)
    criteria = load_criteria_config()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_all_groups,
        "interval",
        minutes=settings.scrape_interval_minutes,
        args=[criteria],
        id="all_groups",
        next_run_time=datetime.now(tz=timezone.utc),
    )

    scheduler.start()
    logger.info("Scheduler started. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
