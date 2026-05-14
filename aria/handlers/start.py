"""Handlers for /start, /help, /reset — only runs when setup is complete."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import aria.db.repo as repo
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.setup_complete:
        return  # setup.py handler will catch this

    await repo.upsert_client(tenant.id, message.from_user.id,
                              message.from_user.language_code or "ru")
    await repo.clear_history(tenant.id, message.from_user.id)

    await message.answer(
        f"Привет, {tenant.owner_name}! Я Aria — твой ресепшн для <b>{tenant.salon_name}</b>.\n\n"
        "Просто пиши как обычно:\n"
        "• «что у меня сегодня?»\n"
        "• «запиши Катю на ресницы 20 мая в 14:00»\n"
        "• «что на этой неделе?»\n\n"
        "/help — список примеров"
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message, tenant: TenantConfig) -> None:
    await repo.clear_history(tenant.id, message.from_user.id)
    await message.answer("История очищена. Начнём заново — чем могу помочь?")


@router.message(Command("help"))
async def cmd_help(message: Message, tenant: TenantConfig) -> None:
    await message.answer(
        "Просто пиши мне:\n\n"
        "• «что у меня сегодня?» — расписание на сегодня\n"
        "• «что на завтра?» — расписание на завтра\n"
        "• «что на неделе с 19 по 25 мая?» — диапазон дат\n"
        "• «запиши Катю на ресницы 20 мая в 14:00» — добавить запись\n"
        "• «перенеси запись #5 на 22 мая в 11:00» — перенос\n"
        "• «отмени запись #5» — отмена\n"
        "• «свободно 20 мая в 15:00?» — проверить слот\n\n"
        "/reset — очистить историю\n"
        "/add_bot — добавить новый салон (только для администратора)"
    )
