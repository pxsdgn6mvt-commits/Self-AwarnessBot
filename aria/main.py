"""
Aria — multi-tenant salon bot platform.

Runs in long-polling mode. Each active tenant gets its own polling loop.
A background watcher picks up new tenants and drops removed ones every 10 s.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from aiogram.types import ErrorEvent

from aria import runtime
from aria.config import settings
from aria.db.fsm_storage import PostgresFSMStorage
from aria.handlers.client_bot import client_router
from aria.db.repo import (
    close_pool, create_tenant, ensure_owner_master, get_tenant,
    get_tenant_by_token, init_db, list_active_tenants,
)
from aria.handlers import admin, chat, email_setup, menu, quick, start
from aria.handlers.masters import router as masters_router
from aria.handlers.setup import router as setup_router
from aria.middleware import TenantMiddleware
from aria.services.commands import set_commands
from aria.services.scheduler import get_scheduler, schedule_daily_reactivation, schedule_owner_reminders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")

_bots: dict[int, Bot] = {}
_tasks: dict[int, asyncio.Task] = {}


def _is_tenant_vip_row(row: dict) -> bool:
    from datetime import datetime, timezone
    if not row.get("is_vip"):
        return False
    vip_until = row.get("vip_until")
    return vip_until is None or vip_until > datetime.now(timezone.utc)


# ── Shared Dispatcher ─────────────────────────────────────────────────────────

def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=PostgresFSMStorage())
    dp.update.middleware(TenantMiddleware())
    dp.include_router(setup_router)
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(masters_router)
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
        if row and row.get("email_user") and row.get("email_host") and _is_tenant_vip_row(row):
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
            except TelegramConflictError:
                log.warning(
                    "Conflict on tenant #%d — another instance still running, waiting 30s",
                    tenant_id,
                )
                await asyncio.sleep(30)
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

                # Resurrect email job if it was lost (e.g. after scheduler restart)
                if row.get("email_user") and row.get("email_host") and _is_tenant_vip_row(row):
                    if not get_scheduler().get_job(f"email_{tid}"):
                        bot = _bots.get(tid)
                        if bot:
                            from aria.services.email_monitor import start_email_job
                            start_email_job(tid, bot)
                            log.info("Resurrected email job for tenant #%d", tid)

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

async def _ensure_owner_masters() -> None:
    rows = await list_active_tenants()
    for row in rows:
        try:
            await ensure_owner_master(row["id"], row["owner_name"])
        except Exception:
            log.exception("ensure_owner_master failed for tenant #%d", row["id"])


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

async def _run_web() -> None:
    port = int(os.getenv("PORT", "8080"))
    from aiohttp import web as aiohttp_web
    from aria.web import create_app
    runner = aiohttp_web.AppRunner(create_app())
    await runner.setup()
    site = aiohttp_web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("Mini App API listening on :%d", port)


async def main() -> None:
    if not settings.BOT_TOKEN:
        log.critical(
            "\n\n"
            "═══════════════════════════════════════════════════════\n"
            "  ARIA не может запуститься: токен бота не задан.\n"
            "\n"
            "  Добавь переменную в Railway → Variables:\n"
            "    ARIA_BOT_TOKEN = <токен от @BotFather>\n"
            "\n"
            "  Также нужны:\n"
            "    ANTHROPIC_API_KEY = <ключ Anthropic>\n"
            "    DATABASE_URL      = <postgres connection string>\n"
            "═══════════════════════════════════════════════════════\n"
        )
        return

    if not settings.ANTHROPIC_API_KEY:
        log.critical("ANTHROPIC_API_KEY не задан в Railway Variables — AI не будет работать")
        return

    await init_db(settings.DATABASE_URL)
    await _ensure_initial_tenant()
    await _ensure_owner_masters()
    get_scheduler().start()
    schedule_daily_reactivation(lambda: _bots)
    schedule_owner_reminders(lambda: _bots)

    dp = _build_dispatcher()

    # ── Client bot (platform-level, one for all tenants) ──────────────────
    _client_task: asyncio.Task | None = None
    if settings.CLIENT_BOT_TOKEN:
        client_bot = Bot(
            token=settings.CLIENT_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        client_dp = Dispatcher()
        client_dp.include_router(client_router)
        _client_task = asyncio.create_task(
            _poll_bot(client_bot, client_dp, tenant_id=0)
        )
        log.info("Client booking bot started")
    else:
        log.warning("CLIENT_BOT_TOKEN not set — client booking bot disabled")

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

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_stop() -> None:
        log.info("Shutdown signal received — stopping all polling tasks")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_stop)
        except NotImplementedError:
            pass

    web_task   = asyncio.create_task(_run_web())
    watch_task = asyncio.create_task(_watch_tenants(dp))
    await stop_event.wait()

    log.info("Cancelling %d polling tasks...", len(_tasks))
    web_task.cancel()
    watch_task.cancel()
    if _client_task:
        _client_task.cancel()
    for task in _tasks.values():
        task.cancel()
    all_tasks = [*_tasks.values(), watch_task, web_task]
    if _client_task:
        all_tasks.append(_client_task)
    await asyncio.gather(*all_tasks, return_exceptions=True)
    await close_pool()
    log.info("Aria shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
