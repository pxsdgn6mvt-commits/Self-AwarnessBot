"""Bot command menu registration."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import BotCommandScopeChat, BotCommandScopeDefault

log = logging.getLogger(__name__)


async def set_commands(bot: Bot, owner_tg_id: Optional[int] = None) -> None:
    try:
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        if owner_tg_id:
            await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=owner_tg_id))
        log.info("Bot commands cleared (owner_tg_id=%s)", owner_tg_id)
    except Exception as exc:
        log.warning("delete_my_commands failed: %s", exc)
