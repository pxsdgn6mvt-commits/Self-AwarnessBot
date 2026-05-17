"""Bot command menu registration."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

log = logging.getLogger(__name__)

_DEFAULT = [
    BotCommand(command="start",  description="Начать / главное меню"),
    BotCommand(command="help",   description="Список команд и примеры"),
    BotCommand(command="reset",  description="Очистить историю диалога"),
]

_OWNER_EXTRA = [
    BotCommand(command="status",        description="Статус бота, GCal и почты"),
    BotCommand(command="connect_email", description="Подключить email-уведомления"),
    BotCommand(command="test_cal",      description="Проверить подключение к GCal"),
    BotCommand(command="set_cal",       description="Изменить Google Calendar ID"),
    BotCommand(command="set_tz",        description="Изменить часовой пояс"),
    BotCommand(command="cancel",        description="Отменить текущую операцию"),
]

_OWNER = _DEFAULT + _OWNER_EXTRA


async def set_commands(bot: Bot, owner_tg_id: Optional[int] = None) -> None:
    try:
        await bot.set_my_commands(_DEFAULT, scope=BotCommandScopeDefault())
        if owner_tg_id:
            await bot.set_my_commands(_OWNER, scope=BotCommandScopeChat(chat_id=owner_tg_id))
        log.info("Bot commands set (owner_tg_id=%s)", owner_tg_id)
    except Exception as exc:
        log.warning("set_my_commands failed: %s", exc)
