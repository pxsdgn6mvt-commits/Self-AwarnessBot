"""Handlers for /start, /help, /reset and main-menu button triggers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    URLInputFile,
)

import aria.db.repo as repo
from aria.config import TenantConfig


class GCalSG(StatesGroup):
    waiting_email = State()

log = logging.getLogger(__name__)
router = Router()

# ── Main reply keyboard (matches original screenshot) ─────────────────────────

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Сегодня"),     KeyboardButton(text="📅 Завтра")],
        [KeyboardButton(text="➕ Новая запись"), KeyboardButton(text="📋 Ближайшие")],
        [KeyboardButton(text="📧 Почта"),        KeyboardButton(text="📱 Меню")],
    ],
    resize_keyboard=True,
)

# ── Inline menu (opened by «📱 Меню» button) ──────────────────────────────────

def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💅 Мои услуги",        callback_data="menu:services")],
        [InlineKeyboardButton(text="📧 Email мониторинг",  callback_data="menu:email")],
        [InlineKeyboardButton(text="📅 Google Calendar",   callback_data="menu:gcal")],
        [InlineKeyboardButton(text="ℹ️ Помощь",            callback_data="menu:help")],
    ])


# ── Welcome texts ──────────────────────────────────────────────────────────────

def _welcome(first_name: str, salon: str) -> str:
    return (
        f"Привет, {first_name}! Я Aria — твой ресепшн для <b>{salon}</b>.\n\n"
        "Используй кнопки внизу или просто пиши:\n"
        "• «что у меня сегодня?»\n"
        "• «запиши Катю на ресницы 20 мая в 14:00»\n"
        "• «что на этой неделе?»\n\n"
        "/help — список примеров"
    )


def _first_welcome(first_name: str, salon: str) -> str:
    return (
        f"Привет, {first_name}! Я Aria — твой ресепшн для <b>{salon}</b>.\n\n"
        "Ты зарегистрирован как владелец.\n\n"
        "Начни с <b>📱 Меню → 💅 Мои услуги</b> — добавь свои категории "
        "и процедуры, чтобы они появились в кнопке «➕ Новая запись».\n\n"
        "/help — примеры команд"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

async def resolve_owner(user_id: int, tenant: TenantConfig) -> int | None:
    db_owner = await repo.get_tenant_owner(tenant.tenant_id)
    if db_owner:
        return db_owner
    if tenant.owner_telegram_id:
        return tenant.owner_telegram_id
    return None


async def _send_avatar(message: Message, tenant: TenantConfig, caption: str) -> bool:
    url = tenant.salon_avatar_url.strip()
    if not url:
        return False
    try:
        photo = URLInputFile(url) if url.startswith("http") else url
        await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
        return True
    except Exception:
        log.warning("tenant #%d: could not send avatar", tenant.tenant_id)
        return False


# ── /start ─────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, tenant: TenantConfig) -> None:
    user_id   = message.from_user.id
    first_name = message.from_user.first_name or "друг"
    owner_id  = await resolve_owner(user_id, tenant)

    if owner_id is None:
        await repo.set_tenant_owner(tenant.tenant_id, user_id)
        await repo.upsert_client(user_id)
        await repo.clear_history(user_id)
        text = _first_welcome(first_name, tenant.salon_name)
        if not await _send_avatar(message, tenant, text):
            await message.answer(text, reply_markup=MAIN_KB, parse_mode="HTML")
        else:
            await message.answer("Чем могу помочь?", reply_markup=MAIN_KB)
        return

    await repo.upsert_client(user_id)
    await repo.clear_history(user_id)
    text = _welcome(first_name, tenant.salon_name)
    if not await _send_avatar(message, tenant, text):
        await message.answer(text, reply_markup=MAIN_KB, parse_mode="HTML")
    else:
        await message.answer("Чем могу помочь?", reply_markup=MAIN_KB)


# ── /reset, /help ──────────────────────────────────────────────────────────────

@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    await repo.clear_history(message.from_user.id)
    await message.answer("Начнём сначала.", reply_markup=MAIN_KB)


@router.message(Command("help"))
async def cmd_help(message: Message, tenant: TenantConfig) -> None:
    await message.answer(
        f"<b>Примеры команд для {tenant.salon_name}:</b>\n\n"
        "📅 «что у меня сегодня?»\n"
        "📅 «что на этой неделе?»\n"
        "➕ «запиши Катю на маникюр 22 мая в 11:00»\n"
        "➕ «новая запись» — выбрать услугу кнопками\n"
        "📋 «покажи ближайшие записи»\n"
        "✏️ «перенеси Катю на пятницу в 15:00»\n"
        "❌ «отмени запись Кати»\n\n"
        "📱 <b>Меню</b> — настройки, услуги, email\n"
        "/admin — управление услугами напрямую\n"
        "/reset — сбросить диалог",
        parse_mode="HTML",
        reply_markup=MAIN_KB,
    )


# ── «📱 Меню» button ───────────────────────────────────────────────────────────

@router.message(F.text == "📱 Меню")
async def handle_menu_button(message: Message, tenant: TenantConfig) -> None:
    await message.answer(
        "⚙️ <b>Меню</b>",
        parse_mode="HTML",
        reply_markup=_menu_kb(),
    )


@router.callback_query(F.data == "menu:services")
async def menu_services(callback: CallbackQuery, tenant: TenantConfig) -> None:
    from aria.handlers.admin import _categories_kb, _is_owner
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer("Только для владельца.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "💅 <b>Мои услуги</b>\n\n"
        "Нажмите на категорию для управления.\n"
        "🗑 — удалить категорию со всеми услугами.",
        parse_mode="HTML",
        reply_markup=await _categories_kb(tenant.tenant_id),
    )


@router.callback_query(F.data == "menu:email")
async def menu_email(callback: CallbackQuery, tenant: TenantConfig) -> None:
    from aria.handlers.admin import show_email_menu, _is_owner
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer("Только для владельца.", show_alert=True)
        return
    await show_email_menu(callback, tenant)


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    await callback.message.edit_text(
        f"<b>Примеры команд:</b>\n\n"
        "• «что у меня сегодня?»\n"
        "• «запиши Катю на маникюр 22 мая в 11:00»\n"
        "• «перенеси Катю на пятницу»\n"
        "• «отмени запись Кати»\n"
        "• «что на этой неделе?»\n\n"
        "/admin — управление услугами\n"
        "/reset — сбросить диалог",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="← Назад", callback_data="menu:back"),
        ]]),
    )


@router.callback_query(F.data == "menu:gcal")
async def menu_gcal(callback: CallbackQuery, tenant: TenantConfig) -> None:
    from aria.handlers.admin import _is_owner
    from aria.services.gcal import is_connected, is_configured
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer("Только для владельца.", show_alert=True)
        return
    await callback.answer()

    if not is_configured():
        await callback.message.edit_text(
            "📅 <b>Google Calendar</b>\n\n"
            "Эта функция пока недоступна в вашей версии бота.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="← Назад", callback_data="menu:back"),
            ]]),
        )
        return

    connected = await is_connected(tenant.tenant_id)
    if connected:
        await callback.message.edit_text(
            "📅 <b>Google Calendar</b>\n\n"
            "✅ Подключён\n\n"
            "Все новые записи автоматически появляются в вашем календаре.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔌 Отключить",      callback_data="gcal:disconnect")],
                [InlineKeyboardButton(text="🔄 Переподключить", callback_data="gcal:connect")],
                [InlineKeyboardButton(text="← Назад",           callback_data="menu:back")],
            ]),
        )
    else:
        await callback.message.edit_text(
            "📅 <b>Google Calendar</b>\n\n"
            "❌ Не подключён\n\n"
            "Подключите свой Google Calendar — записи будут появляться там автоматически.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Подключить Google Calendar", callback_data="gcal:connect")],
                [InlineKeyboardButton(text="← Назад", callback_data="menu:back")],
            ]),
        )


@router.callback_query(F.data == "gcal:connect")
async def gcal_connect(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    from aria.handlers.admin import _is_owner
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer("Только для владельца.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(GCalSG.waiting_email)
    await callback.message.edit_text(
        "📅 <b>Подключение Google Calendar</b>\n\n"
        "Введите ваш Gmail адрес — бот создаст отдельный календарь "
        "<b>Aria — Ваш салон</b> и поделится им с вами.\n\n"
        "Все записи будут появляться там автоматически.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="gcal:cancel"),
        ]]),
    )


@router.callback_query(F.data == "gcal:cancel")
async def gcal_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ <b>Меню</b>", parse_mode="HTML", reply_markup=_menu_kb()
    )


@router.message(GCalSG.waiting_email)
async def got_gcal_email(
    message: Message, state: FSMContext, tenant: TenantConfig
) -> None:
    from aria.services.gcal import setup_calendar
    email = message.text.strip().lower() if message.text else ""
    if "@" not in email or "." not in email.split("@")[-1]:
        await message.answer("Введите корректный email адрес (например: name@gmail.com):")
        return

    await state.clear()
    msg = await message.answer("⏳ Создаю календарь...")
    calendar_id = await setup_calendar(email, tenant.salon_name)
    if calendar_id:
        await repo.save_gcal_calendar_id(tenant.tenant_id, calendar_id)
        await msg.edit_text(
            "✅ <b>Google Calendar подключён!</b>\n\n"
            f"Создан календарь <b>Aria — {tenant.salon_name}</b>.\n\n"
            f"На <code>{email}</code> придёт приглашение от Google — "
            "примите его, и календарь появится в вашем Google Calendar.\n\n"
            "Все новые записи будут добавляться туда автоматически.",
            parse_mode="HTML",
        )
    else:
        await msg.edit_text(
            "❌ Не удалось создать календарь. Проверьте адрес и попробуйте снова.\n\n"
            "📱 Меню → Google Calendar → Подключить"
        )


@router.callback_query(F.data == "gcal:disconnect")
async def gcal_disconnect(callback: CallbackQuery, tenant: TenantConfig) -> None:
    from aria.handlers.admin import _is_owner
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer("Только для владельца.", show_alert=True)
        return
    await repo.clear_gcal_tokens(tenant.tenant_id)
    await callback.answer("Google Calendar отключён.", show_alert=True)
    await callback.message.edit_text(
        "📅 <b>Google Calendar</b>\n\n"
        "❌ Отключён.\n\n"
        "Записи больше не будут добавляться в Google Calendar.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Подключить снова", callback_data="gcal:connect")],
            [InlineKeyboardButton(text="← Назад",            callback_data="menu:back")],
        ]),
    )


@router.callback_query(F.data == "menu:back")
async def menu_back(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ <b>Меню</b>", parse_mode="HTML", reply_markup=_menu_kb()
    )
