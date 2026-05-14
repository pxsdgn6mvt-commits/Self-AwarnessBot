"""Handlers for /start, /help, /reset commands."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

import aria.db.repo as repo
from aria.config import settings

log = logging.getLogger(__name__)
router = Router()

_WELCOME = (
    "Привет, {owner}! Я Aria — твой личный ассистент-ресепшн для {salon}.\n\n"
    "Помогу:\n"
    "• Посмотреть расписание на сегодня, завтра или любую дату\n"
    "• Записать клиента вручную (позвонили, написали в инстаграм)\n"
    "• Перенести или отменить запись\n"
    "• Проверить свободные слоты\n\n"
    "Просто пиши как обычно — команды не нужны.\n"
    "Например: «что у меня сегодня?» или «запиши Катю на ресницы 20 мая в 14:00»"
)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id
    lang_code = message.from_user.language_code or "ru"

    await repo.upsert_client(user_id, lang_code)
    await repo.clear_history(user_id)

    await message.answer(
        _WELCOME.format(
            owner=settings.OWNER_NAME,
            salon=settings.SALON_NAME,
        )
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    await repo.clear_history(message.from_user.id)
    await message.answer("История очищена. Начнём заново — чем могу помочь?")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Просто пиши мне как обычно:\n\n"
        "• «что у меня сегодня?» — расписание на сегодня\n"
        "• «что на завтра?» — расписание на завтра\n"
        "• «запиши Катю на ресницы 20 мая в 14:00» — добавить запись\n"
        "• «перенеси запись #5 на 22 мая в 11:00» — перенос\n"
        "• «отмени запись #5» — отмена\n"
        "• «свободно ли 20 мая в 15:00?» — проверить слот\n\n"
        "/reset — очистить историю разговора"
    )
