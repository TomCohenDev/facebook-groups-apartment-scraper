"""Scheduled scraper entry point."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.classifier.apartment_rules import extract_apartment
from app.classifier.scoring import ALERT_THRESHOLD, score_extraction
from app.facebook.group_reader import read_group
from app.notifier.telegram import send_candidate_alert
from app.settings import load_criteria_config, load_groups_config, settings
from app.storage.db import SessionLocal, engine
from app.storage.repository import (
    get_seen_hashes,
    get_unsent_candidates,
    mark_alert_sent,
    save_candidate,
    save_post,
    upsert_group,
)
from app.storage.schema import FacebookPost, create_tables
from app.utils.logging import get_logger, setup_logging

setup_logging(settings.log_level)
logger = get_logger(__name__)

_PRIORITY_INTERVALS = {
    "high": 15,
    "medium": 60,
    "low": 120,
}


async def run_group(group_cfg: dict, criteria: dict) -> None:
    playwright, context = await create_context(settings.fb_profile_dir, settings.headless)
    try:
        await assert_logged_in(context)

        with SessionLocal() as session:
            upsert_group(session, group_cfg)
            session.commit()
            seen = get_seen_hashes(session, group_cfg["id"])

        report = await read_group(context, group_cfg, seen)

        raw_posts = getattr(report, "raw_posts", [])
        with SessionLocal() as session:
            for raw in raw_posts:
                db_post = save_post(session, raw)
                if db_post is None:
                    continue
                session.commit()

                extraction = extract_apartment(raw.normalized_text)
                score, reasons = score_extraction(extraction, criteria)

                if extraction.is_listing:
                    save_candidate(session, db_post.id, extraction, score, reasons)
                    session.commit()

            if settings.telegram_bot_token:
                unsent = get_unsent_candidates(session, ALERT_THRESHOLD)
                for cand in unsent:
                    post = session.get(FacebookPost, cand.post_id)
                    if post:
                        sent = await send_candidate_alert(cand, post, group_cfg["name"])
                        if sent:
                            mark_alert_sent(session, cand.id)
                            session.commit()

        logger.info(
            "Group %s — seen=%d new=%d comments=%d errors=%d",
            report.group_id,
            report.posts_seen,
            report.posts_new,
            report.comments_scraped,
            len(report.errors),
        )
    finally:
        await context.close()
        await playwright.stop()


async def run_all(criteria: dict) -> None:
    groups = load_groups_config()
    for g in groups:
        if not g.get("enabled", True):
            continue
        try:
            await run_group(g, criteria)
        except Exception as e:
            logger.error("Group %s failed: %s", g["id"], e)


async def main() -> None:
    create_tables(engine)
    criteria = load_criteria_config()

    scheduler = AsyncIOScheduler()
    groups = load_groups_config()
    for g in groups:
        if not g.get("enabled", True):
            continue
        interval = _PRIORITY_INTERVALS.get(g.get("priority", "medium"), 60)
        scheduler.add_job(
            run_group,
            "interval",
            minutes=interval,
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
