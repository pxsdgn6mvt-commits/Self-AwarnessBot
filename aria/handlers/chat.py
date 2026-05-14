"""Main message handler — routes every text message through the AI service."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from aria.services.ai import chat

log = logging.getLogger(__name__)
router = Router()


@router.message()
async def handle_message(message: Message, bot: Bot) -> None:
    if not message.text:
        return

    user_id = message.from_user.id

    # Show typing while Claude thinks
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        reply = await chat(user_id=user_id, user_text=message.text, bot=bot)
    except Exception as exc:
        log.exception("AI service error for user %d: %s", user_id, exc)
        reply = (
            "Something went wrong on my end. "
            "Please try again in a moment."
        )

    await message.answer(reply)
