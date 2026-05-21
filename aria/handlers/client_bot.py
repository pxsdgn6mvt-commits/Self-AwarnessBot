"""Handlers for the platform-level client booking bot.

This bot is distinct from per-tenant owner bots. One bot serves all tenants.
Deep link format: /start tenant_{id}
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from aria.config import settings

log = logging.getLogger(__name__)
client_router = Router()


@client_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    payload = args[1] if len(args) > 1 else ""

    if not payload.startswith("tenant_"):
        await message.answer(
            "Привет! 👋\n\n"
            "Чтобы записаться, используй ссылку от своего мастера.\n"
            "Она выглядит так: <code>t.me/&lt;bot&gt;?start=tenant_123</code>",
            parse_mode="HTML",
        )
        return

    try:
        tenant_id = int(payload.replace("tenant_", ""))
    except ValueError:
        await message.answer("Неверная ссылка. Попроси мастера прислать корректную ссылку.")
        return

    miniapp_url = settings.MINIAPP_URL
    if not miniapp_url:
        await message.answer("Онлайн-запись временно недоступна. Свяжитесь с мастером напрямую.")
        log.warning("CLIENT_BOT /start called but MINIAPP_URL is not set")
        return

    url = f"{miniapp_url}?tenant_id={tenant_id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Записаться", web_app=WebAppInfo(url=url))
    ]])

    await message.answer(
        "Добро пожаловать! 👋\n\nНажмите кнопку ниже чтобы выбрать удобное время:",
        reply_markup=keyboard,
    )
    log.info("Client bot /start for tenant #%d from user %d", tenant_id, message.from_user.id)
