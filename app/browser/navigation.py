from __future__ import annotations

import asyncio

from playwright.async_api import Page


async def safe_goto(page: Page, url: str, timeout: int = 30_000) -> bool:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return True
    except Exception:
        return False


async def scroll_down(page: Page, times: int = 3, delay_ms: int = 2000) -> None:
    for _ in range(times):
        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
        await asyncio.sleep(delay_ms / 1000)


async def click_see_more(page: Page, container_locator) -> None:
    see_more_texts = ["See more", "עוד", "ראה עוד", "הצג עוד"]
    for text in see_more_texts:
        btns = container_locator.get_by_text(text, exact=True)
        count = await btns.count()
        for i in range(count):
            try:
                btn = btns.nth(i)
                if await btn.is_visible():
                    await btn.click(timeout=3000)
                    await asyncio.sleep(0.5)
            except Exception:
                pass
