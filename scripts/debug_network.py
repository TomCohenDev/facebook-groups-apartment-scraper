"""
Dump all network responses from a group page so we can see what Facebook sends.

Usage:
    python scripts/debug_network.py
    python scripts/debug_network.py --url https://www.facebook.com/groups/XXXXXX/

Saves each response to runtime/network_debug/. Check those files to understand
the response structure and URL patterns we need to match.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.browser.navigation import safe_goto, scroll_down
from app.settings import settings
from app.utils.logging import setup_logging

setup_logging("DEBUG")

OUT_DIR = Path("runtime/network_debug")


async def main(url: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    idx = 0
    all_urls: list[str] = []

    async def handle_response(response):
        nonlocal idx
        try:
            ru = response.url
            all_urls.append(ru)
            # print every XHR/fetch response URL
            content_type = response.headers.get("content-type", "")
            if "json" in content_type or "javascript" in content_type:
                print(f"  [{response.status}] {ru[:120]}")
            if response.status != 200:
                return
            # save any response that might contain post data
            if any(k in ru for k in ("graphql", "api/graphql", "feed", "group")):
                text = await response.text()
                if len(text) > 100:
                    path = OUT_DIR / f"response_{idx:03d}.txt"
                    path.write_text(text[:200_000], encoding="utf-8", errors="replace")
                    print(f"  → saved to {path.name} ({len(text)} bytes)")
                    idx += 1
        except Exception as e:
            print(f"  handler error: {e}")

    playwright, context = await create_context(settings.fb_profile_dir, headless=False)
    try:
        await assert_logged_in(context)
        page = await context.new_page()
        page.on("response", handle_response)

        print(f"\nNavigating to {url}")
        await safe_goto(page, url)
        await asyncio.sleep(5)

        print("\nScrolling 5 times...")
        for i in range(5):
            await scroll_down(page, times=1, delay_ms=2000)
            await asyncio.sleep(2)
            print(f"  scroll {i+1} done — {idx} responses saved so far")

        await page.close()
    finally:
        await context.close()
        await playwright.stop()

    print(f"\n=== Done: {idx} responses saved to {OUT_DIR} ===")
    print(f"Total response URLs seen: {len(all_urls)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="https://www.facebook.com/groups/234893187572065/",
        help="Group URL to debug",
    )
    args = parser.parse_args()
    asyncio.run(main(args.url))
