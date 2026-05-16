"""Main message handler — routes text messages through the AI service."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    URLInputFile,
)

from aria.config import settings
from aria.services.ai import chat

log = logging.getLogger(__name__)
router = Router()

_SERVICES_TRIGGER = {"➕ Новая запись", "+ Новая запись", "новая запись"}


def _parse_services() -> list[str]:
    return [s.strip() for s in settings.SALON_SERVICES.split(",") if s.strip()]


def _build_services_kb(services: list[str]) -> InlineKeyboardMarkup:
    """
    Build inline keyboard limited to settings.MAX_SERVICES buttons.
    callback_data uses the list index (e.g. 'svc:3') — stays well under
    Telegram's 64-byte limit regardless of Cyrillic service name length.
    """
    capped = services[: settings.MAX_SERVICES]
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"svc:{i}")]
        for i, name in enumerate(capped)
    ]
    if len(services) > settings.MAX_SERVICES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"… ещё {len(services) - settings.MAX_SERVICES} скрыто",
                    callback_data="svc:overflow",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _warn_owner_service_limit(bot: Bot, total: int) -> None:
    """Notify the owner once when the service list exceeds MAX_SERVICES."""
    owner_id = settings.OWNER_TELEGRAM_ID
    if not owner_id:
        return
    limit = settings.MAX_SERVICES
    try:
        await bot.send_message(
            chat_id=owner_id,
            text=(
                f"⚠️ <b>Лимит процедур достигнут</b>\n\n"
                f"В SALON_SERVICES настроено <b>{total}</b> услуг, "
                f"но в меню отображается только <b>{limit}</b>.\n\n"
                f"Уберите лишние из переменной SALON_SERVICES "
                f"или увеличьте SALON_MAX_SERVICES."
            ),
            parse_mode="HTML",
        )
    except Exception:
        log.warning("Could not notify owner about service limit overflow")


async def _send_avatar_after_booking(message: Message, reply_text: str) -> None:
    """Send avatar photo with booking confirmation, falling back to plain text."""
    url = settings.SALON_AVATAR_URL.strip()
    if not url:
        await message.answer(reply_text)
        return
    try:
        photo = URLInputFile(url) if url.startswith("http") else url
        await message.answer_photo(photo=photo, caption=reply_text)
    except Exception:
        log.warning("Could not send avatar after booking from %s", url)
        await message.answer(reply_text)


@router.message(F.text.casefold().in_({t.casefold() for t in _SERVICES_TRIGGER}))
async def handle_new_booking(message: Message, bot: Bot) -> None:
    services = _parse_services()
    if not services:
        await message.answer("Напишите, какую услугу хотите записать, и я помогу.")
        return

    if len(services) > settings.MAX_SERVICES:
        await _warn_owner_service_limit(bot, len(services))

    await message.answer(
        "Выберите услугу:",
        reply_markup=_build_services_kb(services),
    )


@router.callback_query(F.data.startswith("svc:"))
async def handle_service_selected(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()

    raw = callback.data.split(":", 1)[1]
    if raw == "overflow":
        await callback.message.answer(
            "Показаны только первые услуги. "
            "Напишите название нужной услуги текстом — я найду её."
        )
        return

    try:
        idx = int(raw)
        service = _parse_services()[idx]
    except (ValueError, IndexError):
        await callback.message.answer("Не удалось определить услугу. Попробуйте снова.")
        return

    user_id = callback.from_user.id
    prompt = f"Хочу записаться на «{service}»"

    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    try:
        reply, booking_confirmed = await chat(user_id=user_id, user_text=prompt, bot=bot)
    except Exception:
        log.exception("AI service error for user %d after service selection", user_id)
        reply = "Что-то пошло не так. Попробуйте ещё раз через несколько секунд."
        booking_confirmed = False

    if booking_confirmed:
        await _send_avatar_after_booking(callback.message, reply)
    else:
        await callback.message.answer(reply)


@router.message()
async def handle_message(message: Message, bot: Bot) -> None:
    if not message.text:
        return

    user_id = message.from_user.id
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        reply, booking_confirmed = await chat(
            user_id=user_id, user_text=message.text, bot=bot
        )
    except Exception:
        log.exception("AI service error for user %d", user_id)
        reply = (
            "Что-то пошло не так. "
            "Пожалуйста, попробуйте ещё раз через несколько секунд."
        )
        booking_confirmed = False

    if booking_confirmed:
        await _send_avatar_after_booking(message, reply)
    else:
        await message.answer(reply)
