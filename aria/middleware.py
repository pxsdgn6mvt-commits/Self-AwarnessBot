"""TenantMiddleware — resolves TenantConfig from the bot token on each update."""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject

from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
_CACHE_TTL = 30  # seconds


class TenantMiddleware(BaseMiddleware):
    # Shared across all middleware instances (one per process)
    _cache: dict[str, tuple[TenantConfig, float]] = {}
    # Permanent fallback — survives cache invalidation; used when DB is unreachable
    _last_good: dict[str, TenantConfig] = {}

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
        cached = TenantMiddleware._cache.get(bot.token)
        if cached is None or (now - cached[1]) > _CACHE_TTL:
            try:
                import aria.db.repo as repo
                row = await repo.get_tenant_by_token(bot.token)
                if row:
                    config = TenantConfig.from_record(dict(row))
                    TenantMiddleware._cache[bot.token] = (config, now)
                    TenantMiddleware._last_good[bot.token] = config
                    cached = TenantMiddleware._cache[bot.token]
                else:
                    log.warning("No tenant found for bot token ...%s", bot.token[-8:])
            except Exception:
                log.exception("DB error resolving tenant for bot token ...%s", bot.token[-8:])
                # Fall back to last known good config so voice/text messages still work
                if cached is None and bot.token in TenantMiddleware._last_good:
                    fallback = TenantMiddleware._last_good[bot.token]
                    TenantMiddleware._cache[bot.token] = (fallback, now)
                    cached = TenantMiddleware._cache[bot.token]
                    log.warning("Using stale tenant config for bot ...%s", bot.token[-8:])

        tenant = cached[0] if cached else None
        if tenant is None:
            log.warning(
                "tenant=None for bot ...%s — update will be skipped",
                bot.token[-8:],
            )
        data["tenant"] = tenant
        return await handler(event, data)

    @classmethod
    def invalidate(cls, bot_token: str) -> None:
        """Force-refresh on next request (call after tenant config changes)."""
        cls._cache.pop(bot_token, None)
