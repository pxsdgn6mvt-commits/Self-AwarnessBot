"""Bot command menu registration."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

log = logging.getLogger(__name__)

_OWNER = [
    BotCommand(command="start",         description="Главное меню"),
    BotCommand(command="help",          description="Справка и примеры"),
    BotCommand(command="reset",         description="Очистить историю диалога"),
    BotCommand(command="status",        description="Статус бота, GCal и почты"),
    BotCommand(command="connect_email", description="Подключить email-уведомления"),
    BotCommand(command="test_cal",      description="Проверить подключение к GCal"),
    BotCommand(command="set_cal",       description="Изменить Google Calendar ID"),
    BotCommand(command="set_tz",        description="Изменить часовой пояс"),
    BotCommand(command="cancel",        description="Отменить текущую операцию"),
]


async def set_commands(bot: Bot, owner_tg_id: Optional[int] = None) -> None:
    try:
        # Clients see no command menu — keyboard buttons are sufficient
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        if owner_tg_id:
            await bot.set_my_commands(_OWNER, scope=BotCommandScopeChat(chat_id=owner_tg_id))
        log.info("Bot commands set (owner_tg_id=%s)", owner_tg_id)
    except Exception as exc:
        log.warning("set_my_commands failed: %s", exc)
