"""
Aria — multi-tenant salon bot platform.

Architecture:
  - ONE Dispatcher with all routers included ONCE
  - Each tenant bot runs its own polling task feeding into the shared dispatcher
  - Middleware resolves TenantConfig from bot.token on every update
  - New tenants detected every 10 seconds, no restart needed
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from aria.config import settings
from aria.db.repo import (
    init_db, close_pool, create_tenant, get_tenant_by_token, list_active_tenants,
)
from aria.handlers import admin, chat, start
from aria.handlers.setup import router as setup_router
from aria.middleware import TenantMiddleware
from aria.services.scheduler import get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")

_bots: dict[int, Bot] = {}    # tenant_id -> Bot
_tasks: dict[int, asyncio.Task] = {}  # tenant_id -> polling Task


# ── Dispatcher (created once, shared across all bots) ─────────────────────────

def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(TenantMiddleware())
    # Routers included ONCE — this is the only Dispatcher in the process
    dp.include_router(setup_router)
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(chat.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> None:
        log.exception(
            "Unhandled error for update %s: %s",
            event.update.update_id if event.update else "?",
            event.exception,
            exc_info=event.exception,
        )

    return dp


# ── Per-bot polling task ───────────────────────────────────────────────────────

async def _poll_bot(bot: Bot, dp: Dispatcher, tenant_id: int) -> None:
    try:
        me = await bot.get_me()
        log.info("Bot @%s polling started (tenant #%d)", me.username, tenant_id)
        await dp.start_polling(
            bot,
            drop_pending_updates=False,
            allowed_updates=dp.resolve_used_update_types(),
        )
    except Exception:
        log.exception("Bot polling failed for tenant #%d", tenant_id)
    finally:
        await bot.session.close()


# ── Initial tenant from env vars ──────────────────────────────────────────────

async def _ensure_initial_tenant() -> None:
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


# ── Tenant watcher ────────────────────────────────────────────────────────────

async def _watch_tenants(dp: Dispatcher) -> None:
    while True:
        await asyncio.sleep(10)
        try:
            rows = await list_active_tenants()
            active_ids = {r["id"] for r in rows}

            for row in rows:
                tid = row["id"]
                task = _tasks.get(tid)
                if task is None or task.done():
                    bot = Bot(
                        token=row["bot_token"],
                        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                    )
                    _bots[tid] = bot
                    _tasks[tid] = asyncio.create_task(_poll_bot(bot, dp, tid))
                    log.info("Started bot for tenant #%d (%s)", tid, row["salon_name"])

            for tid in list(_bots.keys()):
                if tid not in active_ids:
                    _tasks[tid].cancel()
                    try:
                        await _bots[tid].session.close()
                    except Exception:
                        pass
                    del _bots[tid]
                    del _tasks[tid]
                    log.info("Stopped bot for tenant #%d", tid)
        except Exception:
            log.exception("Tenant watcher error")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    await init_db(settings.DATABASE_URL)
    await _ensure_initial_tenant()
    get_scheduler().start()

    dp = _build_dispatcher()

    rows = await list_active_tenants()
    for row in rows:
        bot = Bot(
            token=row["bot_token"],
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        tid = row["id"]
        _bots[tid] = bot
        _tasks[tid] = asyncio.create_task(_poll_bot(bot, dp, tid))

    log.info("Aria platform running with %d bot(s)", len(_bots))
    await _watch_tenants(dp)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
