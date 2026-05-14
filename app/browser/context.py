from __future__ import annotations

from pathlib import Path

from playwright.async_api import BrowserContext, Playwright, async_playwright


async def create_context(
    profile_dir: str,
    headless: bool,
) -> tuple[Playwright, BrowserContext]:
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    playwright = await async_playwright().start()

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=headless,
        viewport={"width": 1440, "height": 1200},
        locale="he-IL",
        timezone_id="Asia/Jerusalem",
        args=["--disable-notifications"],
    )

    context.set_default_timeout(30_000)
    return playwright, context
