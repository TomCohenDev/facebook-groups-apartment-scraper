"""
Run a single scrape of all enabled groups.

Usage:
    python scripts/run_once.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.utils.logging import get_logger, setup_logging

setup_logging(settings.log_level)
logger = get_logger(__name__)


async def main() -> None:
    create_tables(engine)
    criteria = load_criteria_config()
    groups = load_groups_config()

    playwright, context = await create_context(settings.fb_profile_dir, settings.headless)
    try:
        await assert_logged_in(context)

        for group_cfg in groups:
            if not group_cfg.get("enabled", True):
                continue
            logger.info("Processing group: %s", group_cfg["id"])

            with SessionLocal() as session:
                upsert_group(session, group_cfg)
                session.commit()
                seen = get_seen_hashes(session, group_cfg["id"])

            report = await read_group(context, group_cfg, seen)
            raw_posts = getattr(report, "raw_posts", [])

            with SessionLocal() as session:
                new_count = 0
                for raw in raw_posts:
                    db_post = save_post(session, raw)
                    if db_post is None:
                        continue
                    new_count += 1
                    session.commit()

                    extraction = extract_apartment(raw.normalized_text)
                    score, reasons = score_extraction(extraction, criteria)

                    if extraction.is_listing:
                        save_candidate(session, db_post.id, extraction, score, reasons)
                        session.commit()

                logger.info(
                    "Group %s — seen=%d new=%d errors=%d",
                    group_cfg["id"],
                    report.posts_seen,
                    new_count,
                    len(report.errors),
                )

                if settings.telegram_bot_token:
                    unsent = get_unsent_candidates(session, ALERT_THRESHOLD)
                    for cand in unsent:
                        post = session.get(FacebookPost, cand.post_id)
                        if post:
                            sent = await send_candidate_alert(cand, post, group_cfg["name"])
                            if sent:
                                mark_alert_sent(session, cand.id)
                                session.commit()
    finally:
        await context.close()
        await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
