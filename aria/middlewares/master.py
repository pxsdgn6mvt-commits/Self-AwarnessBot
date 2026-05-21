"""MasterMiddleware — resolves master_id and tenant_id from bot.token on each update."""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject

log = logging.getLogger(__name__)
_CACHE_TTL = 30


class MasterMiddleware(BaseMiddleware):
    _cache: dict[str, tuple[dict, float]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot: Optional[Bot] = data.get("bot")
        if bot is None:
            return await handler(event, data)

        now = time.monotonic()
        cached = MasterMiddleware._cache.get(bot.token)
        if cached is None or (now - cached[1]) > _CACHE_TTL:
            try:
                import aria.db.repo as repo
                master = await repo.get_master_by_token(bot.token)
                if master:
                    MasterMiddleware._cache[bot.token] = (dict(master), now)
                    cached = MasterMiddleware._cache[bot.token]
                else:
                    MasterMiddleware._cache.pop(bot.token, None)
                    cached = None
                    log.warning("No master found for bot token ...%s", bot.token[-8:])
            except Exception:
                log.exception("DB error in MasterMiddleware for token ...%s", bot.token[-8:])

        if cached is None:
            return

        master_data = cached[0]
        data["master_id"] = master_data["id"]
        data["tenant_id"] = master_data["tenant_id"]
        data["master_name"] = master_data["name"]
        return await handler(event, data)

    @classmethod
    def invalidate(cls, bot_token: str) -> None:
        cls._cache.pop(bot_token, None)
