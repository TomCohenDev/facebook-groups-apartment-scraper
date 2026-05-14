from __future__ import annotations

import asyncio

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from app.settings import settings
from app.storage.schema import ApartmentCandidate, FacebookPost
from app.utils.logging import get_logger

logger = get_logger(__name__)

_FEEDBACK_BUTTONS = [
    [
        InlineKeyboardButton("✅ Relevant", callback_data="feedback:relevant"),
        InlineKeyboardButton("❌ Reject", callback_data="feedback:reject"),
    ],
    [
        InlineKeyboardButton("☎️ Contacted", callback_data="feedback:contacted"),
        InlineKeyboardButton("🕵️ Duplicate", callback_data="feedback:duplicate"),
    ],
    [
        InlineKeyboardButton("💸 Too expensive", callback_data="feedback:expensive"),
        InlineKeyboardButton("📍 Bad location", callback_data="feedback:bad_location"),
    ],
]


def _build_message(candidate: ApartmentCandidate, post: FacebookPost, group_name: str) -> str:
    lines = [f"🏠 *Facebook apartment lead — {candidate.score}/100*", ""]

    if candidate.city or candidate.neighborhood:
        loc = " ".join(filter(None, [candidate.city, candidate.neighborhood]))
        lines.append(f"📍 {loc}")
    if candidate.price_ils:
        lines.append(f"💸 ₪{candidate.price_ils:,}")
    if candidate.rooms:
        lines.append(f"🛏️ {candidate.rooms} rooms")
    if candidate.sqm:
        lines.append(f"📐 {candidate.sqm} sqm")
    if candidate.entry_date:
        lines.append(f"🚪 Entry: {candidate.entry_date}")
    if candidate.brokerage is not None:
        lines.append(f"🧾 Brokerage: {'Yes' if candidate.brokerage else 'No'}")

    if candidate.reasons:
        lines.append("")
        lines.append("Why:")
        for reason in candidate.reasons[:5]:
            lines.append(f"✅ {reason}")

    lines.append("")
    lines.append(f"Group: {group_name}")
    if post.post_url:
        lines.append(f"Post: {post.post_url}")

    return "\n".join(lines)


async def send_candidate_alert(
    candidate: ApartmentCandidate,
    post: FacebookPost,
    group_name: str,
) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured — skipping alert")
        return False

    bot = Bot(token=settings.telegram_bot_token)
    message = _build_message(candidate, post, group_name)
    markup = InlineKeyboardMarkup(_FEEDBACK_BUTTONS)

    try:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=message,
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=False,
        )
        return True
    except TelegramError as e:
        logger.error("Telegram send failed: %s", e)
        return False
