from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError

from app.settings import settings
from app.storage.schema import FacebookPost
from app.utils.logging import get_logger

logger = get_logger(__name__)

_MAX_TEXT_LEN = 3500


def _format_post_date(post: FacebookPost) -> str:
    """Return a human-readable post date from creation_time (unix ts) or scraped_at."""
    ts_text = post.timestamp_text or ""
    try:
        ts = int(ts_text)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, OSError):
        pass
    if post.scraped_at:
        return post.scraped_at.strftime("%d/%m/%Y %H:%M")
    return ""


def _build_ai_message(post: FacebookPost, group_name: str, ai: dict[str, Any]) -> str:
    lines = []

    if ai.get("is_listing"):
        lines.append("🏠 *דירה להשכרה*")
    else:
        lines.append("📋 *פוסט חדש*")
    lines.append(f"_{group_name}_")
    date_str = _format_post_date(post)
    if date_str:
        lines.append(f"📅 {date_str}")
    lines.append("")

    loc_parts = [ai.get("city"), ai.get("neighborhood"), ai.get("street")]
    loc = " • ".join(p for p in loc_parts if p)
    if loc:
        lines.append(f"📍 {loc}")

    if ai.get("price_ils"):
        lines.append(f"💸 ₪{ai['price_ils']:,} / חודש")

    if ai.get("rooms"):
        lines.append(f"🛏️ {ai['rooms']} חדרים")

    if ai.get("sqm"):
        lines.append(f"📐 {ai['sqm']} מ\"ר")

    if ai.get("floor") is not None:
        lines.append(f"🏢 קומה {ai['floor']}")

    if ai.get("entry_date"):
        lines.append(f"🚪 כניסה: {ai['entry_date']}")

    if ai.get("brokerage") is False:
        lines.append("✅ ללא תיווך")
    elif ai.get("brokerage") is True:
        lines.append("🧾 עם תיווך")

    flags = ai.get("flags") or []
    if flags:
        lines.append("🏷️ " + " · ".join(flags))

    if ai.get("phone_numbers"):
        lines.append("☎️ " + " | ".join(ai["phone_numbers"]))

    summary = ai.get("summary", "")
    if summary:
        lines.append("")
        lines.append(summary)

    if not ai.get("matches_criteria") and ai.get("skip_reason"):
        lines.append("")
        lines.append(f"⚠️ {ai['skip_reason']}")

    lines.append("")
    if post.author_name:
        lines.append(f"👤 {post.author_name}")
    if post.post_url:
        lines.append(f"🔗 {post.post_url}")

    return "\n".join(lines)


def _build_raw_message(post: FacebookPost, group_name: str) -> str:
    date_str = _format_post_date(post)
    lines = [f"📋 *{group_name}*"]
    if date_str:
        lines.append(f"📅 {date_str}")
    lines.append("")
    text = (post.normalized_text or post.raw_text or "").strip()
    if len(text) > _MAX_TEXT_LEN:
        text = text[:_MAX_TEXT_LEN] + "…"
    if text:
        lines.append(text)
    lines.append("")
    if post.author_name:
        lines.append(f"👤 {post.author_name}")
    if post.post_url:
        lines.append(f"🔗 {post.post_url}")
    return "\n".join(lines)


async def send_text(text: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return True
    except TelegramError as e:
        logger.error("Telegram send_text failed: %s", e)
        return False


async def send_post_alert(
    post: FacebookPost,
    group_name: str,
    ai_result: dict[str, Any] | None = None,
    images: list[bytes] | None = None,
) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured — skipping alert")
        return False

    bot = Bot(token=settings.telegram_bot_token)
    message = (
        _build_ai_message(post, group_name, ai_result)
        if ai_result
        else _build_raw_message(post, group_name)
    )
    chat_id = settings.telegram_chat_id

    try:
        if images:
            media = [
                InputMediaPhoto(
                    media=io.BytesIO(data),
                    caption=message if i == 0 else None,
                    parse_mode="Markdown" if i == 0 else None,
                )
                for i, data in enumerate(images[:10])
            ]
            if len(media) == 1:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=io.BytesIO(images[0]),
                    caption=message,
                    parse_mode="Markdown",
                )
            else:
                await bot.send_media_group(chat_id=chat_id, media=media)
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        return True
    except TelegramError as e:
        logger.error("Telegram send failed: %s", e)
        return False
