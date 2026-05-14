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
    """Return False only when we're certain the post fails a hard criterion."""
    if not ai_result:
        return True
    price = ai_result.get("price_ils")
    max_price = criteria.get("price", {}).get("max")
    if price and max_price and price > max_price:
        logger.info("Skipping: price %d > max %d", price, max_price)
        return False
    return True


async def main(limit: int | None = None) -> None:
    start_time = datetime.now(tz=timezone.utc)
    create_tables(engine)
    groups = load_groups_config()
    if limit:
        groups = groups[:limit]
    criteria = load_criteria_config()
    ai_cfg = criteria.get("ai", {})
    send_non_listings = ai_cfg.get("send_non_listings", False)
    ai_model = ai_cfg.get("model") or settings.ai_model

    # Each entry: (db_post, group_name, ai_result, image_bytes)
    to_send: list[tuple] = []
    total_scraped = 0
    total_filtered = 0

    # ── Phase 1: scrape all groups, run AI, collect posts to send ────────────
    playwright, context = await create_context(settings.fb_profile_dir, settings.headless)
    try:
        await assert_logged_in(context)

        for group_cfg in groups:
            if not group_cfg.get("enabled", True):
                continue
            logger.info("Processing group: %s", group_cfg["id"])

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
                    logger.info(
                        "AI: is_listing=%s city=%s price=%s rooms=%s",
                        ai_result.get("is_listing") if ai_result else "?",
                        ai_result.get("city") if ai_result else "?",
                        ai_result.get("price_ils") if ai_result else "?",
                        ai_result.get("rooms") if ai_result else "?",
                    )

                    qualifies = (
                        settings.telegram_bot_token
                        and _passes_hard_filters(ai_result, criteria)
                        and (send_non_listings or ai_result is None or ai_result.get("is_listing"))
                    )
                    if qualifies:
                        image_urls = [img.image_url for img in (raw.images or [])]
                        img_data = await download_images(context, image_urls) if image_urls else []
                        # Reload columns after commit so Telegram phase can read attrs without a Session
                        session.refresh(db_post)
                        to_send.append((db_post, group_cfg["name"], ai_result, img_data))
                    else:
                        total_filtered += 1

            logger.info(
                "Group %s — scraped=%d errors=%d",
                group_cfg["id"], report.posts_seen, len(report.errors),
            )
    finally:
        await context.close()
        await playwright.stop()

    # ── Phase 2: send header ─────────────────────────────────────────────────
    if settings.telegram_bot_token and settings.telegram_chat_id:
        date_str = start_time.strftime("%d/%m/%Y %H:%M")
        await send_text(f"🔍 {date_str} — {len(to_send)} דירות חדשות")

    # ── Phase 3: send alerts ─────────────────────────────────────────────────
    total_sent = 0
    for db_post, group_name, ai_result, img_data in to_send:
        sent = await send_post_alert(db_post, group_name, ai_result, images=img_data or None)
        if sent:
            with SessionLocal() as session:
                mark_post_alerted(session, db_post.id)
                session.commit()
            total_sent += 1

    # ── Phase 4: summary ─────────────────────────────────────────────────────
    if settings.telegram_bot_token and settings.telegram_chat_id and (total_scraped or total_sent):
        elapsed = (datetime.now(tz=timezone.utc) - start_time).total_seconds()
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
