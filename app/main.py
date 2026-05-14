"""Scheduled scraper entry point."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.classifier.ai_extractor import extract_post
from app.facebook.group_reader import read_group
from app.facebook.image_extractor import download_images
from app.notifier.telegram import send_post_alert, send_text
from app.settings import load_criteria_config, load_groups_config, settings
from app.storage.db import SessionLocal, engine
from app.storage.repository import get_seen_hashes, mark_post_alerted, save_post, upsert_group
from app.storage.schema import create_tables
from app.utils.logging import get_logger, setup_logging

setup_logging(settings.log_level)
logger = get_logger(__name__)


def _passes_hard_filters(ai_result: dict | None, criteria: dict) -> bool:
    if not ai_result:
        return True
    price = ai_result.get("price_ils")
    max_price = criteria.get("price", {}).get("max")
    if price and max_price and price > max_price:
        logger.info("Skipping: price %d > max %d", price, max_price)
        return False
    return True


async def run_group(group_cfg: dict, criteria: dict) -> None:
    start_time = datetime.now(tz=timezone.utc)
    ai_cfg = criteria.get("ai", {})
    send_non_listings = ai_cfg.get("send_non_listings", False)
    ai_model = ai_cfg.get("model") or settings.ai_model

    to_send: list[tuple] = []
    total_scraped = 0
    total_filtered = 0
    report = None

    playwright, context = await create_context(settings.fb_profile_dir, settings.headless)
    try:
        await assert_logged_in(context)

        with SessionLocal() as session:
            db_group = upsert_group(session, group_cfg)
            session.commit()
            actual_id = db_group.id
            seen = get_seen_hashes(session, actual_id)

        effective_cfg = {**group_cfg, "id": actual_id}
        report = await read_group(context, effective_cfg, seen)

        raw_posts = getattr(report, "raw_posts", [])
        with SessionLocal() as session:
            for raw in raw_posts:
                db_post = save_post(session, raw)
                if db_post is None:
                    continue
                session.commit()
                total_scraped += 1

                ai_result = await extract_post(raw.normalized_text, criteria, model=ai_model)

                qualifies = (
                    settings.telegram_bot_token
                    and _passes_hard_filters(ai_result, criteria)
                    and (send_non_listings or ai_result is None or ai_result.get("is_listing"))
                )
                if qualifies:
                    image_urls = [img.image_url for img in (raw.images or [])]
                    img_data = await download_images(context, image_urls) if image_urls else []
                    to_send.append((db_post, group_cfg["name"], ai_result, img_data))
                else:
                    total_filtered += 1

    finally:
        await context.close()
        await playwright.stop()

    # Send header
    if settings.telegram_bot_token and settings.telegram_chat_id and to_send:
        date_str = start_time.strftime("%d/%m/%Y %H:%M")
        await send_text(f"🔍 {date_str} — {len(to_send)} דירות חדשות")

    # Send alerts
    total_sent = 0
    for db_post, group_name, ai_result, img_data in to_send:
        sent = await send_post_alert(db_post, group_name, ai_result, images=img_data or None)
        if sent:
            with SessionLocal() as session:
                mark_post_alerted(session, db_post.id)
                session.commit()
            total_sent += 1

    # Send summary
    if settings.telegram_bot_token and settings.telegram_chat_id and (total_scraped or total_sent):
        elapsed = (datetime.now(tz=timezone.utc) - start_time).total_seconds()
        mins, secs = int(elapsed // 60), int(elapsed % 60)
        await send_text(
            f"✅ סיום — {total_scraped} נסרקו | {total_sent} נשלחו | {total_filtered} סוננו | {mins}m {secs}s"
        )

    errors = len(report.errors) if report else 0
    group_id = report.group_id if report else group_cfg["id"]
    logger.info(
        "Group %s — scraped=%d sent=%d filtered=%d errors=%d",
        group_id, total_scraped, total_sent, total_filtered, errors,
    )


async def main() -> None:
    create_tables(engine)
    criteria = load_criteria_config()

    scheduler = AsyncIOScheduler()
    for g in load_groups_config():
        if not g.get("enabled", True):
            continue
        scheduler.add_job(
            run_group,
            "interval",
            minutes=settings.scrape_interval_minutes,
            args=[g, criteria],
            id=g["id"],
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
