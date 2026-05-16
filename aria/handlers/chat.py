"""Main message handler — routes text messages through the AI service."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from aria.config import settings
from aria.services.ai import chat

log = logging.getLogger(__name__)
router = Router()

_SERVICES_TRIGGER = {"➕ Новая запись", "+ Новая запись", "новая запись"}


def _parse_services() -> list[str]:
    """Split SALON_SERVICES into a clean list."""
    return [s.strip() for s in settings.SALON_SERVICES.split(",") if s.strip()]


def _build_services_kb() -> InlineKeyboardMarkup:
    """
    Build inline keyboard for procedure selection.
    callback_data uses index (e.g. 'svc:3') to stay well under Telegram's
    64-byte limit regardless of how long the Russian service names are.
    """
    services = _parse_services()
    rows: list[list[InlineKeyboardButton]] = []
    for i, name in enumerate(services):
        rows.append([InlineKeyboardButton(text=name, callback_data=f"svc:{i}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.casefold().in_({t.casefold() for t in _SERVICES_TRIGGER}))
async def handle_new_booking(message: Message) -> None:
    services = _parse_services()
    if not services:
        await message.answer(
            "Напишите, какую услугу хотите записать, и я помогу."
        )
        return

    await message.answer(
        "Выберите услугу:",
        reply_markup=_build_services_kb(),
    )


@router.callback_query(F.data.startswith("svc:"))
async def handle_service_selected(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()

    try:
        idx = int(callback.data.split(":", 1)[1])
        service = _parse_services()[idx]
    except (ValueError, IndexError):
        await callback.message.answer("Не удалось определить услугу. Попробуйте снова.")
        return

    user_id = callback.from_user.id
    prompt = f"Хочу записаться на «{service}»"

    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    try:
        reply = await chat(user_id=user_id, user_text=prompt, bot=bot)
    except Exception:
        log.exception("AI service error for user %d after service selection", user_id)
        reply = "Что-то пошло не так. Попробуйте ещё раз через несколько секунд."

    await callback.message.answer(reply)


@router.message()
async def handle_message(message: Message, bot: Bot) -> None:
    if not message.text:
        return

    user_id = message.from_user.id
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        reply = await chat(user_id=user_id, user_text=message.text, bot=bot)
    except Exception:
        log.exception("AI service error for user %d", user_id)
        reply = (
            "Что-то пошло не так. "
            "Пожалуйста, попробуйте ещё раз через несколько секунд."
        )

    await message.answer(reply)
