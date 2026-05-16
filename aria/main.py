"""
Aria — multi-tenant salon bot platform.

Runs in long-polling mode. Each active tenant gets its own polling loop.
A background watcher picks up new tenants and drops removed ones every 10 s.
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

from aria import runtime
from aria.config import settings
from aria.db.repo import (
    close_pool, create_tenant, get_tenant, get_tenant_by_token,
    init_db, list_active_tenants,
)
from aria.handlers import admin, chat, email_setup, menu, quick, start
from aria.handlers.setup import router as setup_router
from aria.middleware import TenantMiddleware
from aria.services.commands import set_commands
from aria.services.scheduler import get_scheduler, schedule_daily_reactivation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")

_bots: dict[int, Bot] = {}
_tasks: dict[int, asyncio.Task] = {}


# ── Shared Dispatcher ─────────────────────────────────────────────────────────

def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(TenantMiddleware())
    dp.include_router(setup_router)
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(quick.router)
    dp.include_router(email_setup.router)
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


# ── Bot lifecycle helpers ─────────────────────────────────────────────────────

async def _configure_bot(bot: Bot, dp: Dispatcher, tenant_id: int) -> None:
    try:
        me = await bot.get_me()
        log.info("Configuring bot @%s (tenant #%d)", me.username, tenant_id)
        row = await get_tenant(tenant_id)
        if row and row["setup_complete"]:
            await set_commands(bot, row["owner_tg_id"])
        else:
            await set_commands(bot)
        if row and row.get("email_user") and row.get("email_host"):
            from aria.services.email_monitor import start_email_job
            start_email_job(tenant_id, bot)
    except Exception:
        log.exception("Bot configuration failed for tenant #%d", tenant_id)


# ── Polling ───────────────────────────────────────────────────────────────────

async def _poll_bot(bot: Bot, dp: Dispatcher, tenant_id: int) -> None:
    allowed = dp.resolve_used_update_types()
    offset = 0
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass
    try:
        await _configure_bot(bot, dp, tenant_id)
        while True:
            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=30,
                    allowed_updates=allowed,
                )
                for update in updates:
                    try:
                        await dp.feed_update(bot, update)
                    except Exception:
                        log.exception(
                            "Error processing update %d (tenant #%d)",
                            update.update_id, tenant_id,
                        )
                    offset = update.update_id + 1
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("get_updates error tenant #%d, retry in 5s", tenant_id)
                await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("Bot polling failed for tenant #%d", tenant_id)
    finally:
        await bot.session.close()


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
                    runtime.bots[tid] = bot
                    _tasks[tid] = asyncio.create_task(_poll_bot(bot, dp, tid))
                    log.info("Started polling for tenant #%d (%s)", tid, row["salon_name"])

            for tid in list(_bots.keys()):
                if tid not in active_ids:
                    _tasks[tid].cancel()
                    try:
                        await _bots[tid].session.close()
                    except Exception:
                        pass
                    del _bots[tid]
                    runtime.bots.pop(tid, None)
                    del _tasks[tid]
                    log.info("Stopped polling for tenant #%d", tid)
        except Exception:
            log.exception("Tenant watcher error")


# ── Initial tenant seed ───────────────────────────────────────────────────────

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


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    await init_db(settings.DATABASE_URL)
    await _ensure_initial_tenant()
    get_scheduler().start()
    schedule_daily_reactivation(lambda: _bots)

    dp = _build_dispatcher()

    rows = await list_active_tenants()
    for row in rows:
        bot = Bot(
            token=row["bot_token"],
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        tid = row["id"]
        _bots[tid] = bot
        runtime.bots[tid] = bot
        _tasks[tid] = asyncio.create_task(_poll_bot(bot, dp, tid))

    log.info("Aria polling mode — %d bot(s)", len(_bots))
    await _watch_tenants(dp)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
