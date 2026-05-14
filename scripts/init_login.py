"""
Bootstrap Facebook login into the persistent browser profile.

Usage:
    python scripts/init_login.py

Steps:
1. Opens a visible Chrome window with the persistent profile.
2. Navigate to https://www.facebook.com
3. Log in manually in the browser.
4. Press Enter here when done.
5. Browser closes and session is saved.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser.context import create_context
from app.settings import settings
from app.utils.logging import setup_logging

setup_logging()


async def main() -> None:
    print("Opening browser with persistent profile...")
    playwright, context = await create_context(settings.fb_profile_dir, headless=False)
    page = await context.new_page()
    await page.goto("https://www.facebook.com/")
    print("\nPlease log in to Facebook in the browser window.")
    print("Press ENTER here when you are logged in and the feed is visible.")
    input()
    print("Saving session...")
    await context.close()
    await playwright.stop()
    print("Done. Session saved to:", settings.fb_profile_dir)


if __name__ == "__main__":
    asyncio.run(main())
