"""Handlers for /start, /help, /reset."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    URLInputFile,
)

import aria.db.repo as repo
from aria.config import TenantConfig

log = logging.getLogger(__name__)
router = Router()

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[[
        KeyboardButton(text="➕ Новая запись"),
        KeyboardButton(text="📋 Ближайшие"),
    ]],
    resize_keyboard=True,
)

_FIRST_WELCOME = (
    "👋 Добро пожаловать! Вы зарегистрированы как владелец.\n\n"
    "Используйте /admin чтобы добавить свои категории и услуги.\n"
    "После этого кнопка «➕ Новая запись» покажет ваши процедуры."
)

_WELCOME = (
    "Привет! Я Aria, администратор {salon}.\n\n"
    "Я помогу записаться, перенести или отменить визит.\n\n"
    "Просто напишите мне или используйте кнопки внизу."
)


async def _send_avatar(message: Message, tenant: TenantConfig, caption: str) -> bool:
    url = tenant.salon_avatar_url.strip()
    if not url:
        return False
    try:
        photo = URLInputFile(url) if url.startswith("http") else url
        await message.answer_photo(photo=photo, caption=caption)
        return True
    except Exception:
        log.warning("tenant #%d: could not send avatar", tenant.tenant_id)
        return False


async def resolve_owner(user_id: int, tenant: TenantConfig) -> int | None:
    """Return the owner Telegram ID for this tenant (DB or env var)."""
    db_owner = await repo.get_tenant_owner(tenant.tenant_id)
    if db_owner:
        return db_owner
    if tenant.owner_telegram_id:
        return tenant.owner_telegram_id
    return None


@router.message(CommandStart())
async def cmd_start(message: Message, tenant: TenantConfig) -> None:
    user_id = message.from_user.id
    owner_id = await resolve_owner(user_id, tenant)

    if owner_id is None:
        # First person to /start becomes the owner
        await repo.set_tenant_owner(tenant.tenant_id, user_id)
        await repo.upsert_client(user_id)
        await repo.clear_history(user_id)
        sent = await _send_avatar(message, tenant, caption=_FIRST_WELCOME)
        if not sent:
            await message.answer(_FIRST_WELCOME, reply_markup=MAIN_KB)
        else:
            await message.answer("Чем могу помочь?", reply_markup=MAIN_KB)
        return

    await repo.upsert_client(user_id)
    await repo.clear_history(user_id)
    welcome = _WELCOME.format(salon=tenant.salon_name)
    sent = await _send_avatar(message, tenant, caption=welcome)
    if not sent:
        await message.answer(welcome, reply_markup=MAIN_KB)
    else:
        await message.answer("Чем могу помочь?", reply_markup=MAIN_KB)


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    await repo.clear_history(message.from_user.id)
    await message.answer("Начнём сначала — чем могу помочь?", reply_markup=MAIN_KB)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Просто напишите мне — специальные команды не нужны.\n\n"
        "Вы можете:\n"
        "• Записаться на услугу\n"
        "• Перенести или отменить запись\n"
        "• Узнать о ближайших записях\n"
        "• Встать в лист ожидания\n\n"
        "/admin — управление категориями и услугами\n"
        "/reset — начать новый диалог",
        reply_markup=MAIN_KB,
    )
