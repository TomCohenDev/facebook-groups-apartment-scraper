from __future__ import annotations

import asyncio

from playwright.async_api import BrowserContext

from app.facebook.models import RawComment
from app.facebook.selectors import COMMENT_EXPAND_TEXTS
from app.utils.hashing import content_hash
from app.utils.logging import get_logger
from app.utils.text import canonicalize_facebook_url, normalize_text

logger = get_logger(__name__)


async def extract_comments_from_post(
    context: BrowserContext,
    post_url: str,
    max_comments: int,
) -> list[RawComment]:
    if not post_url:
        return []

    page = await context.new_page()
    comments: list[RawComment] = []
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)

        for expand_text in COMMENT_EXPAND_TEXTS:
            btns = page.get_by_text(expand_text, exact=True)
            btn_count = await btns.count()
            for i in range(min(btn_count, 3)):
                try:
                    btn = btns.nth(i)
                    if await btn.is_visible():
                        await btn.click(timeout=4000)
                        await asyncio.sleep(1)
                except Exception:
                    pass

        comment_containers = page.locator('div[role="article"] div[role="article"]')
        count = await comment_containers.count()

        seen_hashes: set[str] = set()
        for i in range(min(count, max_comments)):
            ctn = comment_containers.nth(i)
            try:
                raw = await ctn.inner_text(timeout=4000)
            except Exception:
                continue

            norm = normalize_text(raw)
            if not norm or len(norm) < 3:
                continue

            chash = content_hash("comment", norm)
            if chash in seen_hashes:
                continue
            seen_hashes.add(chash)

            author_name = ""
            author_url = ""
            try:
                link = ctn.locator("a[href]").first
                author_name = await link.inner_text(timeout=2000)
                href = await link.get_attribute("href") or ""
                author_url = canonicalize_facebook_url(href) if href else ""
            except Exception:
                pass

            timestamp_text = ""
            try:
                abbr = ctn.locator("abbr, [data-tooltip-content]").first
                timestamp_text = await abbr.inner_text(timeout=2000)
            except Exception:
                pass

            comments.append(
                RawComment(
                    author_name=author_name,
                    author_profile_url=author_url,
                    raw_text=raw,
                    timestamp_text=timestamp_text,
                    content_hash=chash,
                )
            )

    except Exception as e:
        logger.warning("Comment extraction failed for %s: %s", post_url, e)
    finally:
        await page.close()

    return comments
