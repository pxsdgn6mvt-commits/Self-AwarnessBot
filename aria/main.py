"""
Aria salon bot — multi-tenant entry point.

All bots share one Dispatcher. A middleware injects the correct TenantConfig
into each update based on the bot token, then all handlers receive it via DI.

Env vars
--------
Format A (multi-tenant, recommended):
  ARIA_BOT_1_TOKEN=<token>   ARIA_BOT_1_SALON_NAME=...  ARIA_BOT_1_OWNER_ID=...
  ARIA_BOT_2_TOKEN=<token>   ...

Format B (legacy single-bot):
  ARIA_BOT_TOKEN=<token>

Shared:
  ANTHROPIC_API_KEY, ARIA_DATABASE_URL, ARIA_CLAUDE_MODEL,
  SALON_MAX_SERVICES, SALON_OPEN_HOUR, SALON_CLOSE_HOUR, ...
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Callable, Awaitable

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject

from aria.config import TenantConfig, load_tenants
from aria.db.repo import init_db, close_pool
from aria.handlers.admin import router as admin_router
from aria.handlers.start import router as start_router
from aria.handlers.chat import router as chat_router
from aria.services.scheduler import get_scheduler
from aria.services.email_monitor import run_email_monitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")


class TenantMiddleware:
    """Injects the correct TenantConfig into each update based on bot token."""

    def __init__(self, tenant_map: dict) -> None:
        self.tenant_map = tenant_map

    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict,
    ) -> Any:
        bot = data.get("bot")
        if bot:
            data["tenant"] = self.tenant_map.get(bot.token)
        return await handler(event, data)


async def main() -> None:
    tenants = load_tenants()
    if not tenants:
        log.error(
            "No bot tokens found. Set ARIA_BOT_1_TOKEN (multi-tenant) "
            "or ARIA_BOT_TOKEN (single-bot) and restart."
        )
        sys.exit(1)

    await init_db(tenants[0].database_url)
    get_scheduler().start()
    log.info("Aria polling mode — %d bot(s)", len(tenants))

    tenant_map = {t.bot_token: t for t in tenants}

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(TenantMiddleware(tenant_map))
    dp.include_router(admin_router)
    dp.include_router(start_router)
    dp.include_router(chat_router)

    bots = [
        Bot(
            token=t.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        for t in tenants
    ]

    # Start email monitor for every tenant — each loop waits for DB settings
    email_tasks = [
        asyncio.create_task(run_email_monitor(t, bot))
        for t, bot in zip(tenants, bots)
    ]
    log.info("Email monitor loops started for %d bot(s)", len(email_tasks))

    try:
        await dp.start_polling(*bots, drop_pending_updates=True)
    finally:
        for task in email_tasks:
            task.cancel()
        for bot in bots:
            await bot.session.close()

    get_scheduler().shutdown(wait=False)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
