from __future__ import annotations

import re

from playwright.async_api import Locator

from app.facebook.models import RawImage

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
