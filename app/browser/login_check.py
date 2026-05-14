from __future__ import annotations

from playwright.async_api import BrowserContext, Page


async def is_logged_in(context: BrowserContext) -> bool:
    page = await context.new_page()
    try:
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=20_000)
        url = page.url
        if "login" in url or "checkpoint" in url:
            return False
        logged_in = await page.locator('[aria-label="Facebook"]').count() > 0
        return logged_in
    except Exception:
        return False
    finally:
        await page.close()


async def assert_logged_in(context: BrowserContext) -> None:
    if not await is_logged_in(context):
        raise RuntimeError(
            "Not logged in to Facebook. Run scripts/init_login.py first."
        )
