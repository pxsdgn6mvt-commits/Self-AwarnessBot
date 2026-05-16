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


@router.message(CommandStart())
async def cmd_start(message: Message, tenant: TenantConfig) -> None:
    await repo.upsert_client(message.from_user.id)
    await repo.clear_history(message.from_user.id)
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
        "• Узнать о наших услугах\n"
        "• Встать в лист ожидания\n\n"
        "/reset — начать новый диалог",
        reply_markup=MAIN_KB,
    )
