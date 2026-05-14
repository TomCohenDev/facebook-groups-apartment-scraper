"""
Debug a single group visibly and dump results to runtime/debug/.

Usage:
    python scripts/debug_group.py --group-id tel_aviv_no_broker
    python scripts/debug_group.py --group-id tel_aviv_no_broker --headless false
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.facebook.group_reader import read_group
from app.settings import load_groups_config, settings
from app.utils.logging import get_logger, setup_logging

setup_logging("DEBUG")
logger = get_logger(__name__)


async def main(group_id: str, headless: bool) -> None:
    groups = {g["id"]: g for g in load_groups_config()}
    if group_id not in groups:
        print(f"Group '{group_id}' not found in config/groups.yaml")
        sys.exit(1)

    group_cfg = groups[group_id]
    debug_dir = Path("runtime/debug") / group_id

    playwright, context = await create_context(settings.fb_profile_dir, headless)
    try:
        await assert_logged_in(context)
        report = await read_group(context, group_cfg, seen_hashes=set(), debug_dir=debug_dir)
        raw_posts = getattr(report, "raw_posts", [])
        logger.info(
            "Debug run complete — posts=%d errors=%d",
            len(raw_posts),
            len(report.errors),
        )
        logger.info("Outputs in: %s", debug_dir)
    finally:
        await context.close()
        await playwright.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--headless", default="false", choices=["true", "false"])
    args = parser.parse_args()
    asyncio.run(main(args.group_id, args.headless == "true"))
