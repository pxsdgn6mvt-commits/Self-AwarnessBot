"""Main message handler — routes text through the AI service."""

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

import aria.db.repo as repo
from aria.config import TenantConfig
from aria.services.ai import chat

log = logging.getLogger(__name__)
router = Router()

_BOOKING_TRIGGER = {"➕ Новая запись", "+ Новая запись", "новая запись"}


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _flat_kb(services: list[str], limit: int) -> InlineKeyboardMarkup:
    capped = services[:limit]
    rows = [
        [InlineKeyboardButton(text=s, callback_data=f"svc:{i}")]
        for i, s in enumerate(capped)
    ]
    if len(services) > limit:
        rows.append([InlineKeyboardButton(
            text=f"… ещё {len(services) - limit} скрыто",
            callback_data="svc:overflow",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _category_kb(tree: dict[str, list[str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=cat, callback_data=f"cat:{i}")]
        for i, cat in enumerate(list(tree.keys()))
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subcategory_kb(cat_idx: int, subs: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=s, callback_data=f"sub:{cat_idx}:{i}")]
        for i, s in enumerate(subs)
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="cat:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_services(tenant: TenantConfig) -> list[str]:
    return [s.strip() for s in tenant.salon_services.split(",") if s.strip()]


async def _load_tree(tenant: TenantConfig) -> dict[str, list[str]]:
    db_tree = await repo.get_services_tree()
    return db_tree if db_tree else tenant.services_tree_dict


async def _warn_owner(bot: Bot, tenant: TenantConfig, total: int) -> None:
    if not tenant.owner_telegram_id:
        return
    try:
        await bot.send_message(
            chat_id=tenant.owner_telegram_id,
            text=(
                f"⚠️ <b>Лимит процедур достигнут</b>\n\n"
                f"Настроено <b>{total}</b> услуг, "
                f"показывается только <b>{tenant.max_services}</b>.\n\n"
                f"Уберите лишние или увеличьте ARIA_BOT_{tenant.tenant_id}_MAX_SERVICES."
            ),
            parse_mode="HTML",
        )
    except Exception:
        log.warning("tenant #%d: could not notify owner", tenant.tenant_id)


async def _send_avatar_reply(message: Message, tenant: TenantConfig, text: str) -> None:
    url = tenant.salon_avatar_url.strip()
    if not url:
        await message.answer(text)
        return
    try:
        photo = URLInputFile(url) if url.startswith("http") else url
        await message.answer_photo(photo=photo, caption=text)
    except Exception:
        await message.answer(text)


# ── New booking flow ──────────────────────────────────────────────────────────

@router.message(F.text.casefold().in_({t.casefold() for t in _BOOKING_TRIGGER}))
async def handle_new_booking(message: Message, bot: Bot, tenant: TenantConfig) -> None:
    tree = await _load_tree(tenant)
    if tree:
        await message.answer("Выберите категорию:", reply_markup=_category_kb(tree))
        return

    services = _parse_services(tenant)
    if not services:
        await message.answer("Напишите название услуги — я помогу записать.")
        return
    if len(services) > tenant.max_services:
        await _warn_owner(bot, tenant, len(services))
    await message.answer("Выберите услугу:", reply_markup=_flat_kb(services, tenant.max_services))


@router.callback_query(F.data.startswith("cat:"))
async def handle_category(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    raw = callback.data.split(":", 1)[1]
    tree = await _load_tree(tenant)

    if raw == "back":
        await callback.message.edit_text("Выберите категорию:", reply_markup=_category_kb(tree))
        return

    try:
        idx = int(raw)
        cats = list(tree.keys())
        cat_name = cats[idx]
        subs = tree[cat_name]
    except (ValueError, IndexError, KeyError):
        await callback.message.answer("Категория не найдена. Попробуйте снова.")
        return

    await callback.message.edit_text(
        f"<b>{cat_name}</b> — выберите услугу:",
        parse_mode="HTML",
        reply_markup=_subcategory_kb(idx, subs),
    )


@router.callback_query(F.data.startswith("sub:"))
async def handle_subcategory(callback: CallbackQuery, bot: Bot, tenant: TenantConfig) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    try:
        tree = await _load_tree(tenant)
        cats = list(tree.keys())
        cat_name = cats[int(parts[1])]
        service = f"{cat_name} — {tree[cat_name][int(parts[2])]}"
    except (IndexError, ValueError, KeyError):
        await callback.message.answer("Не удалось определить услугу. Попробуйте снова.")
        return

    await _book_service(callback.message, bot, tenant, service)


@router.callback_query(F.data.startswith("svc:"))
async def handle_service_flat(callback: CallbackQuery, bot: Bot, tenant: TenantConfig) -> None:
    await callback.answer()
    raw = callback.data.split(":", 1)[1]
    if raw == "overflow":
        await callback.message.answer(
            "Напишите название нужной услуги текстом — я найду её."
        )
        return
    try:
        service = _parse_services(tenant)[int(raw)]
    except (ValueError, IndexError):
        await callback.message.answer("Не удалось определить услугу. Попробуйте снова.")
        return
    await _book_service(callback.message, bot, tenant, service)


async def _book_service(message: Message, bot: Bot, tenant: TenantConfig, service: str) -> None:
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        reply, confirmed = await chat(
            user_id=message.chat.id,
            user_text=f"Хочу записаться на «{service}»",
            bot=bot,
            tenant=tenant,
        )
    except Exception:
        log.exception("AI error after service selection (tenant #%d)", tenant.tenant_id)
        reply, confirmed = "Что-то пошло не так. Попробуйте ещё раз.", False

    if confirmed:
        await _send_avatar_reply(message, tenant, reply)
    else:
        await message.answer(reply)


# ── Generic message handler ───────────────────────────────────────────────────

@router.message()
async def handle_message(message: Message, bot: Bot, tenant: TenantConfig) -> None:
    if not message.text:
        return
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        reply, confirmed = await chat(
            user_id=message.from_user.id,
            user_text=message.text,
            bot=bot,
            tenant=tenant,
        )
    except Exception:
        log.exception("AI error (tenant #%d)", tenant.tenant_id)
        reply, confirmed = "Что-то пошло не так. Попробуйте ещё раз.", False

    if confirmed:
        await _send_avatar_reply(message, tenant, reply)
    else:
        await message.answer(reply)
