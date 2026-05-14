import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram import Bot
from app.settings import settings


async def main():
    bot = Bot(token=settings.telegram_bot_token)
    updates = await bot.get_updates()
    if not updates:
        print("No messages found. Send any message to your bot in Telegram first, then rerun this script.")
        return
    for u in updates:
        if u.message:
            print(f"chat_id: {u.message.chat.id} | name: {u.message.chat.first_name} {u.message.chat.last_name or ''}")


asyncio.run(main())
