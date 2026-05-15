"""
Aria — multi-tenant salon bot platform.

Webhook mode  (production / Railway):
  Set WEBHOOK_BASE_URL=https://your-service.up.railway.app in Railway env vars.
  Each bot registers its webhook at {WEBHOOK_BASE_URL}/webhook/{tenant_id}.
  aiohttp listens on $PORT and forwards updates to the shared Dispatcher.
  No polling → no TelegramConflictError on rolling redeploys.

Polling mode  (local dev / fallback):
  Leave WEBHOOK_BASE_URL unset.  Classic long-polling, one task per bot.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent, Update
from aiohttp import web

from aria.config import settings
from aria.db.fsm_storage import PostgresFSMStorage
from aria.db.repo import (
    close_pool, create_tenant, get_tenant, get_tenant_by_token,
    init_db, list_active_tenants,
)
from aria.handlers import admin, chat, email_setup, quick, start
from aria.handlers.setup import router as setup_router
from aria.middleware import TenantMiddleware
from aria.services.commands import set_commands
from aria.services.scheduler import get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")

_bots: dict[int, Bot] = {}
_tasks: dict[int, asyncio.Task] = {}   # used in polling mode only


# ── Shared Dispatcher ─────────────────────────────────────────────────────────

def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=PostgresFSMStorage())
    dp.update.middleware(TenantMiddleware())
    dp.include_router(setup_router)
    dp.include_router(admin.router)
    dp.include_router(start.router)
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
    """Set bot commands and start any background jobs (email polling, etc.)."""
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


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK MODE
# ══════════════════════════════════════════════════════════════════════════════

def _make_web_app(dp: Dispatcher) -> web.Application:
    app = web.Application()

    async def webhook(request: web.Request) -> web.Response:
        try:
            tid = int(request.match_info["tenant_id"])
        except (KeyError, ValueError):
            return web.Response(status=400)

        bot = _bots.get(tid)
        if bot is None:
            return web.Response(status=404)

        # Verify optional secret token
        if settings.WEBHOOK_SECRET:
            if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.WEBHOOK_SECRET:
                return web.Response(status=403)

        data = await request.json()
        update = Update.model_validate(data)
        asyncio.create_task(dp.feed_update(bot, update))
        return web.Response()

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_post("/webhook/{tenant_id}", webhook)
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    return app


async def _register_webhook(bot: Bot, dp: Dispatcher, tenant_id: int) -> bool:
    url = f"{settings.WEBHOOK_BASE_URL}/webhook/{tenant_id}"
    allowed = list(dp.resolve_used_update_types())
    kwargs: dict = dict(
        url=url,
        drop_pending_updates=True,
        allowed_updates=allowed,
    )
    if settings.WEBHOOK_SECRET:
        kwargs["secret_token"] = settings.WEBHOOK_SECRET
    try:
        await bot.set_webhook(**kwargs)
        log.info("Webhook registered: %s", url)
        return True
    except Exception as exc:
        log.error("Failed to register webhook for tenant #%d at %s: %s", tenant_id, url, exc)
        return False


async def _watch_tenants_webhook(dp: Dispatcher) -> None:
    while True:
        await asyncio.sleep(10)
        try:
            rows = await list_active_tenants()
            active_ids = {r["id"] for r in rows}

            for row in rows:
                tid = row["id"]
                if tid not in _bots:
                    bot = Bot(
                        token=row["bot_token"],
                        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                    )
                    _bots[tid] = bot
                    await _configure_bot(bot, dp, tid)
                    ok = await _register_webhook(bot, dp, tid)
                    if ok:
                        log.info("Added tenant #%d (%s) via webhook", tid, row["salon_name"])
                    else:
                        log.warning("Tenant #%d (%s) added but webhook registration failed — retrying in 10s", tid, row["salon_name"])

            for tid in list(_bots.keys()):
                if tid not in active_ids:
                    bot = _bots.pop(tid)
                    try:
                        await bot.delete_webhook()
                        await bot.session.close()
                    except Exception:
                        pass
                    log.info("Removed tenant #%d", tid)
        except Exception:
            log.exception("Tenant watcher error (webhook)")


async def _run_webhook(dp: Dispatcher) -> None:
    # Start HTTP server FIRST so Railway health check passes immediately
    app = _make_web_app(dp)
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("Aria webhook HTTP server listening on port %d", port)

    # Register webhooks for all active bots
    rows = await list_active_tenants()
    for row in rows:
        bot = Bot(
            token=row["bot_token"],
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        tid = row["id"]
        _bots[tid] = bot
        await _configure_bot(bot, dp, tid)
        await _register_webhook(bot, dp, tid)

    log.info("Aria webhook mode ready — %d bot(s) on %s", len(_bots), settings.WEBHOOK_BASE_URL)
    await _watch_tenants_webhook(dp)


# ══════════════════════════════════════════════════════════════════════════════
# POLLING MODE  (fallback for local dev / when WEBHOOK_BASE_URL is not set)
# ══════════════════════════════════════════════════════════════════════════════

async def _poll_bot(bot: Bot, dp: Dispatcher, tenant_id: int) -> None:
    allowed = dp.resolve_used_update_types()
    offset = 0
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


async def _watch_tenants_poll(dp: Dispatcher) -> None:
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
                    log.info("Started polling for tenant #%d (%s)", tid, row["salon_name"])

            for tid in list(_bots.keys()):
                if tid not in active_ids:
                    _tasks[tid].cancel()
                    try:
                        await _bots[tid].session.close()
                    except Exception:
                        pass
                    del _bots[tid]
                    del _tasks[tid]
                    log.info("Stopped polling for tenant #%d", tid)
        except Exception:
            log.exception("Tenant watcher error (polling)")


async def _run_polling(dp: Dispatcher) -> None:
    rows = await list_active_tenants()
    for row in rows:
        bot = Bot(
            token=row["bot_token"],
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        tid = row["id"]
        _bots[tid] = bot
        _tasks[tid] = asyncio.create_task(_poll_bot(bot, dp, tid))

    log.info("Aria polling mode — %d bot(s)", len(_bots))
    await _watch_tenants_poll(dp)


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

    dp = _build_dispatcher()

    if settings.WEBHOOK_BASE_URL:
        log.info("Starting in WEBHOOK mode: %s", settings.WEBHOOK_BASE_URL)
        await _run_webhook(dp)
    else:
        log.info("Starting in POLLING mode (set WEBHOOK_BASE_URL for production)")
        await _run_polling(dp)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
