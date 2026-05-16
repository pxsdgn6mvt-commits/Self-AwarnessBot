"""
Aria salon bot — multi-tenant entry point.

Each bot token loaded from env vars gets its own aiogram Dispatcher.
All bots share one Postgres pool and one APScheduler instance.

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

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from aria.config import TenantConfig, load_tenants
from aria.db.repo import init_db, close_pool
from aria.handlers.admin import router as admin_router
from aria.handlers.start import router as start_router
from aria.handlers.chat import router as chat_router
from aria.services.scheduler import get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")


def _make_dispatcher(tenant: TenantConfig) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Inject tenant config — handlers receive it as `tenant: TenantConfig`
    dp["tenant"] = tenant
    dp.include_router(admin_router)
    dp.include_router(start_router)
    dp.include_router(chat_router)
    return dp


async def _run_tenant(tenant: TenantConfig) -> None:
    bot = Bot(
        token=tenant.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = _make_dispatcher(tenant)
    me = await bot.get_me()
    log.info("Configuring bot @%s (tenant #%d)", me.username, tenant.tenant_id)
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await bot.session.close()


async def main() -> None:
    tenants = load_tenants()
    if not tenants:
        log.error(
            "No bot tokens found. Set ARIA_BOT_1_TOKEN (multi-tenant) "
            "or ARIA_BOT_TOKEN (single-bot) and restart."
        )
        sys.exit(1)

    db_url = tenants[0].database_url
    await init_db(db_url)
    get_scheduler().start()
    log.info("Aria polling mode — %d bot(s)", len(tenants))

    await asyncio.gather(*[_run_tenant(t) for t in tenants])

    get_scheduler().shutdown(wait=False)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
