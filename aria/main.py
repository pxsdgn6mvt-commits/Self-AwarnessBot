"""
Aria — multi-tenant salon bot platform.

One Railway deployment runs all salon bots concurrently.
New bots are detected automatically (checked every 60s).

Usage:
    python -m aria.main
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from aria.config import settings
from aria.db.repo import init_db, close_pool, create_tenant, get_tenant_by_token, list_active_tenants
from aria.handlers import admin, chat, start
from aria.handlers.setup import router as setup_router
from aria.middleware import TenantMiddleware
from aria.services.scheduler import get_scheduler
from aria.tenant import TenantConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")

_running: dict[int, asyncio.Task] = {}


async def _ensure_initial_tenant() -> None:
    """Create the initial tenant from env vars if it doesn't exist yet."""
    existing = await get_tenant_by_token(settings.BOT_TOKEN)
    if existing is None:
        tid = await create_tenant(
            bot_token=settings.BOT_TOKEN,
            owner_tg_id=settings.OWNER_TELEGRAM_ID,
            salon_name=settings.SALON_NAME,
            owner_name=settings.OWNER_NAME,
            services=settings.SALON_SERVICES,
            hours=settings.SALON_HOURS,
            open_hour=settings.SALON_OPEN_HOUR,
            close_hour=settings.SALON_CLOSE_HOUR,
            slot_minutes=settings.SALON_SLOT_MINUTES,
            working_days=settings.SALON_WORKING_DAYS,
            google_cal_credentials=settings.GOOGLE_CALENDAR_CREDENTIALS,
            google_cal_id=settings.GOOGLE_CALENDAR_ID,
            setup_complete=True,
        )
        log.info("Created initial tenant #%d (%s)", tid, settings.SALON_NAME)


def _make_dispatcher(tenant: TenantConfig) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(TenantMiddleware(tenant.id))
    # Order: setup wizard first (intercepts /start when not configured)
    # then admin commands, then normal start/help, then catch-all chat
    dp.include_router(setup_router)
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(chat.router)
    return dp


async def _run_tenant(tenant: TenantConfig) -> None:
    bot = Bot(
        token=tenant.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = _make_dispatcher(tenant)
    me = await bot.get_me()
    log.info("Bot @%s started (tenant #%d: %s)", me.username, tenant.id, tenant.salon_name)
    try:
        await dp.start_polling(bot, drop_pending_updates=False,
                               allowed_updates=dp.resolve_used_update_types())
    except Exception:
        log.exception("Bot for tenant #%d crashed", tenant.id)
    finally:
        await bot.session.close()


async def _watch_tenants() -> None:
    """Poll for new or deactivated tenants every 10 seconds."""
    while True:
        await asyncio.sleep(10)
        try:
            rows = await list_active_tenants()
            active_ids = {r["id"] for r in rows}

            for row in rows:
                tid = row["id"]
                if tid not in _running or _running[tid].done():
                    tenant = TenantConfig.from_record(dict(row))
                    _running[tid] = asyncio.create_task(_run_tenant(tenant))
                    log.info("Started bot for new tenant #%d", tid)

            for tid in list(_running.keys()):
                if tid not in active_ids:
                    _running[tid].cancel()
                    del _running[tid]
                    log.info("Stopped bot for deactivated tenant #%d", tid)
        except Exception:
            log.exception("Tenant watcher error")


async def main() -> None:
    await init_db(settings.DATABASE_URL)
    await _ensure_initial_tenant()

    get_scheduler().start()

    rows = await list_active_tenants()
    for row in rows:
        tenant = TenantConfig.from_record(dict(row))
        task = asyncio.create_task(_run_tenant(tenant))
        _running[tenant.id] = task

    log.info("Aria platform started with %d bot(s)", len(_running))

    # Watch forever for new tenants
    await _watch_tenants()


async def _shutdown() -> None:
    get_scheduler().shutdown(wait=False)
    await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
