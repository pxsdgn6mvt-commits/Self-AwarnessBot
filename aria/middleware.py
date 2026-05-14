"""TenantMiddleware — injects a fresh TenantConfig into every handler."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from aria.tenant import TenantConfig

_CACHE_TTL = 30  # seconds before re-fetching tenant from DB


class TenantMiddleware(BaseMiddleware):
    def __init__(self, tenant_id: int) -> None:
        self._tenant_id = tenant_id
        self._cached: Optional[TenantConfig] = None
        self._cached_at: float = 0.0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        now = time.monotonic()
        if self._cached is None or (now - self._cached_at) > _CACHE_TTL:
            import aria.db.repo as repo
            row = await repo.get_tenant(self._tenant_id)
            if row:
                self._cached = TenantConfig.from_record(dict(row))
                self._cached_at = now

        if self._cached is not None:
            data["tenant"] = self._cached
        return await handler(event, data)
