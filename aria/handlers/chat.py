"""Main message handler — routes text through the AI service."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    URLInputFile,
)

import aria.db.repo as repo
from aria.config import TenantConfig
from aria.handlers.booking import start_booking
from aria.services.ai import chat

log = logging.getLogger(__name__)
router = Router()

_BOOKING_TRIGGER  = {"➕ Новая запись", "+ Новая запись", "новая запись"}
_TODAY_TRIGGER    = {"📅 Сегодня"}
_TOMORROW_TRIGGER = {"📅 Завтра"}
_NEAREST_TRIGGER  = {"📋 Ближайшие"}
_MAIL_TRIGGER     = {"📧 Почта"}
_SKIP_TRIGGERS    = {"📱 Меню"}  # handled in start.py


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
    db_tree = await repo.get_services_tree(tenant.tenant_id)
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


# ── Quick-action button handlers ─────────────────────────────────────────────

@router.message(F.text.in_(_TODAY_TRIGGER))
async def handle_today(message: Message, bot: Bot, tenant: TenantConfig) -> None:
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    reply, _ = await _ai(message.from_user.id, "что у меня сегодня?", bot, tenant)
    await message.answer(reply)


@router.message(F.text.in_(_TOMORROW_TRIGGER))
async def handle_tomorrow(message: Message, bot: Bot, tenant: TenantConfig) -> None:
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    reply, _ = await _ai(message.from_user.id, "что у меня завтра?", bot, tenant)
    await message.answer(reply)


@router.message(F.text.in_(_NEAREST_TRIGGER))
async def handle_nearest(message: Message, bot: Bot, tenant: TenantConfig) -> None:
    from aria.handlers.booking import show_bookings_list
    await show_bookings_list(message, message.from_user.id, tenant)


@router.callback_query(F.data == "new:booking")
async def new_booking_callback(
    callback: CallbackQuery, state: FSMContext, bot: Bot, tenant: TenantConfig
) -> None:
    await callback.answer()
    tree = await _load_tree(tenant)
    if tree:
        await callback.message.edit_text(
            "Выберите категорию:", reply_markup=_category_kb(tree)
        )
        return
    services = _parse_services(tenant)
    if not services:
        await callback.message.answer("Напишите название услуги — я помогу записать.")
        return
    if len(services) > tenant.max_services:
        await _warn_owner(bot, tenant, len(services))
    await callback.message.edit_text(
        "Выберите услугу:", reply_markup=_flat_kb(services, tenant.max_services)
    )


@router.message(F.text.in_(_MAIL_TRIGGER))
async def handle_mail_button(message: Message, tenant: TenantConfig) -> None:
    row = await repo.get_email_settings(tenant.tenant_id)
    has_email = row and row["email_address"]
    if has_email:
        senders = row["email_allowed_senders"] or "все"
        text = (
            f"📧 <b>Email мониторинг активен</b>\n\n"
            f"Адрес: <code>{row['email_address']}</code>\n"
            f"Отправители: {senders}\n\n"
            "Управление: /admin → Email мониторинг"
        )
    else:
        text = (
            "📧 <b>Email мониторинг не настроен</b>\n\n"
            "Нажмите /admin → Email мониторинг чтобы подключить."
        )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚙️ Настроить", callback_data="adm:email")
    ]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def _ai(user_id: int, text: str, bot: Bot, tenant: TenantConfig) -> tuple[str, bool]:
    try:
        return await chat(user_id=user_id, user_text=text, bot=bot, tenant=tenant)
    except Exception:
        log.exception("AI error (tenant #%d)", tenant.tenant_id)
        return "Что-то пошло не так. Попробуйте ещё раз.", False


# ── New booking flow ──────────────────────────────────────────────────────────

@router.message(F.text.casefold().in_({t.casefold() for t in _BOOKING_TRIGGER}))
async def handle_new_booking(message: Message, state: FSMContext, bot: Bot, tenant: TenantConfig) -> None:
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
async def handle_subcategory(
    callback: CallbackQuery, state: FSMContext, bot: Bot, tenant: TenantConfig
) -> None:
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

    await start_booking(callback, state, tenant, service)


@router.callback_query(F.data.startswith("svc:"))
async def handle_service_flat(
    callback: CallbackQuery, state: FSMContext, bot: Bot, tenant: TenantConfig
) -> None:
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
    await start_booking(callback, state, tenant, service)


# ── Generic message handler ───────────────────────────────────────────────────

@router.message()
async def handle_message(message: Message, bot: Bot, tenant: TenantConfig) -> None:
    if not message.text or message.text in _SKIP_TRIGGERS:
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
