from __future__ import annotations

import re

from playwright.async_api import BrowserContext, Locator

from app.facebook.models import RawImage
from app.utils.logging import get_logger

logger = get_logger(__name__)

_REJECT_SRC_PATTERNS = re.compile(
    r"emoji|reaction|static|rsrc|ads|logo|avatar|s\d+x\d+",
    re.IGNORECASE,
)


async def extract_images_from_container(container: Locator) -> list[RawImage]:
    images: list[RawImage] = []
    imgs = container.locator("img")
    count = await imgs.count()

    for i in range(count):
        img = imgs.nth(i)
        try:
            src = await img.get_attribute("src") or ""
            alt = await img.get_attribute("alt") or ""
            width_str = await img.get_attribute("width") or "0"
            height_str = await img.get_attribute("height") or "0"

            try:
                width = int(width_str)
                height = int(height_str)
            except ValueError:
                width, height = 0, 0

            if width > 0 and width < 150:
                continue
            if height > 0 and height < 150:
                continue
            if _REJECT_SRC_PATTERNS.search(src):
                continue
            if not src or src.startswith("data:"):
                continue

            images.append(RawImage(image_url=src, alt_text=alt))
        except Exception:
            continue

    return images


async def download_images(
    context: BrowserContext,
    image_urls: list[str],
    max_images: int = 4,
) -> list[bytes]:
    """Download up to max_images using the authenticated browser context."""
    results: list[bytes] = []
    for url in image_urls[:max_images]:
        try:
            response = await context.request.get(url)
            if response.ok:
                data = await response.body()
                if len(data) > 1024:  # skip suspiciously small blobs
                    results.append(data)
            else:
                logger.debug("Image fetch %s → HTTP %d", url, response.status)
        except Exception as exc:
            logger.debug("Image download failed (%s): %s", url, exc)
    return results
