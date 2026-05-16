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


# ── Service list helpers ──────────────────────────────────────────────────────

def _parse_services() -> list[str]:
    return [s.strip() for s in settings.SALON_SERVICES.split(",") if s.strip()]


def _flat_kb(services: list[str]) -> InlineKeyboardMarkup:
    """Single-level keyboard — one button per service, index-based callback."""
    capped = services[: settings.MAX_SERVICES]
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"svc:{i}")]
        for i, name in enumerate(capped)
    ]
    if len(services) > settings.MAX_SERVICES:
        rows.append([
            InlineKeyboardButton(
                text=f"… ещё {len(services) - settings.MAX_SERVICES} скрыто",
                callback_data="svc:overflow",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _category_kb(tree: dict[str, list[str]]) -> InlineKeyboardMarkup:
    """First level: one button per category."""
    cats = list(tree.keys())[: settings.MAX_SERVICES]
    rows = [
        [InlineKeyboardButton(text=cat, callback_data=f"cat:{i}")]
        for i, cat in enumerate(cats)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subcategory_kb(cat_index: int, subs: list[str]) -> InlineKeyboardMarkup:
    """Second level: subcategory buttons + «← Назад»."""
    capped = subs[: settings.MAX_SERVICES]
    rows = [
        [InlineKeyboardButton(text=sub, callback_data=f"sub:{cat_index}:{i}")]
        for i, sub in enumerate(capped)
    ]
    rows.append([
        InlineKeyboardButton(text="← Назад", callback_data="cat:back")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Owner notifications ───────────────────────────────────────────────────────

async def _warn_owner_service_limit(bot: Bot, total: int) -> None:
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
                f"Уберите лишние или увеличьте SALON_MAX_SERVICES."
            ),
            parse_mode="HTML",
        )
    except Exception:
        log.warning("Could not notify owner about service limit overflow")


# ── Avatar helper ─────────────────────────────────────────────────────────────

async def _send_avatar_after_booking(message: Message, reply_text: str) -> None:
    url = settings.SALON_AVATAR_URL.strip()
    if not url:
        await message.answer(reply_text)
        return
    try:
        photo = URLInputFile(url) if url.startswith("http") else url
        await message.answer_photo(photo=photo, caption=reply_text)
    except Exception:
        log.warning("Could not send avatar photo: %s", url)
        await message.answer(reply_text)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(F.text.casefold().in_({t.casefold() for t in _SERVICES_TRIGGER}))
async def handle_new_booking(message: Message, bot: Bot) -> None:
    tree = settings.services_tree
    if tree:
        await message.answer("Выберите категорию:", reply_markup=_category_kb(tree))
        return

    services = _parse_services()
    if not services:
        await message.answer("Напишите, какую услугу хотите записать, и я помогу.")
        return
    if len(services) > settings.MAX_SERVICES:
        await _warn_owner_service_limit(bot, len(services))
    await message.answer("Выберите услугу:", reply_markup=_flat_kb(services))


@router.callback_query(F.data.startswith("cat:"))
async def handle_category(callback: CallbackQuery) -> None:
    await callback.answer()
    raw = callback.data.split(":", 1)[1]

    if raw == "back":
        tree = settings.services_tree
        await callback.message.edit_text(
            "Выберите категорию:", reply_markup=_category_kb(tree)
        )
        return

    try:
        idx = int(raw)
        tree = settings.services_tree
        cats = list(tree.keys())
        cat_name = cats[idx]
        subs = tree[cat_name]
    except (ValueError, IndexError, KeyError):
        await callback.message.answer("Не удалось открыть категорию. Попробуйте снова.")
        return

    await callback.message.edit_text(
        f"<b>{cat_name}</b> — выберите услугу:",
        parse_mode="HTML",
        reply_markup=_subcategory_kb(idx, subs),
    )


@router.callback_query(F.data.startswith("sub:"))
async def handle_subcategory(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    # format: sub:<cat_idx>:<sub_idx>
    try:
        cat_idx = int(parts[1])
        sub_idx = int(parts[2])
        tree = settings.services_tree
        cats = list(tree.keys())
        cat_name = cats[cat_idx]
        service = f"{cat_name} — {tree[cat_name][sub_idx]}"
    except (IndexError, ValueError, KeyError):
        await callback.message.answer("Не удалось определить услугу. Попробуйте снова.")
        return

    user_id = callback.from_user.id
    prompt = f"Хочу записаться на «{service}»"

    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    try:
        reply, booking_confirmed = await chat(user_id=user_id, user_text=prompt, bot=bot)
    except Exception:
        log.exception("AI error for user %d after subcategory selection", user_id)
        reply = "Что-то пошло не так. Попробуйте ещё раз."
        booking_confirmed = False

    if booking_confirmed:
        await _send_avatar_after_booking(callback.message, reply)
    else:
        await callback.message.answer(reply)


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
        log.exception("AI error for user %d after service selection", user_id)
        reply = "Что-то пошло не так. Попробуйте ещё раз."
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
        log.exception("AI error for user %d", user_id)
        reply = "Что-то пошло не так. Попробуйте ещё раз через несколько секунд."
        booking_confirmed = False

    if booking_confirmed:
        await _send_avatar_after_booking(message, reply)
    else:
        await message.answer(reply)
