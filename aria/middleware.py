"""TenantMiddleware — injects TenantConfig into every handler via aiogram DI."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from aria.tenant import TenantConfig


class TenantMiddleware(BaseMiddleware):
    def __init__(self, tenant: TenantConfig) -> None:
        self.tenant = tenant

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["tenant"] = self.tenant
        return await handler(event, data)
