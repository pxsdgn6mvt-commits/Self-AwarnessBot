"""
Aria — multi-tenant salon bot platform.

Runs in long-polling mode. Each active tenant gets its own polling loop.
A background watcher picks up new tenants and drops removed ones every 10 s.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import urllib.parse
from datetime import datetime

from aiohttp import web as aio_web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from aiogram.types import ErrorEvent

from aria import runtime
from aria.config import settings
from aria.db.fsm_storage import PostgresFSMStorage
from aria.db import repo
from aria.db.repo import (
    close_pool, create_tenant, get_tenant, get_tenant_by_token,
    init_db, list_active_tenants,
)
from aria.services.notifications import notify_owner
from aria.handlers import admin, chat, email_setup, menu, quick, start
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


# ── Mini App API (aiohttp) ────────────────────────────────────────────────────

def _validate_init_data(init_data: str, bot_token: str) -> bool:
    try:
        parsed = dict(x.split("=", 1) for x in init_data.split("&"))
        data_check = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items()) if k != "hash"
        )
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parsed.get("hash", ""))
    except Exception:
        return False


def _parse_user_id(init_data: str) -> int:
    try:
        parsed = dict(x.split("=", 1) for x in init_data.split("&"))
        user_obj = json.loads(urllib.parse.unquote(parsed.get("user", "{}")))
        return int(user_obj.get("id", 0))
    except Exception:
        return 0


@aio_web.middleware
async def _cors_middleware(request: aio_web.Request, handler):
    if request.method == "OPTIONS":
        resp = aio_web.Response()
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Init-Data"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


async def _handle_categories(request: aio_web.Request) -> aio_web.Response:
    bot_token = request.match_info["bot_token"]
    pool = request.app["pool"]
    rows = await pool.fetch(
        "SELECT id, name FROM aria_service_categories "
        "WHERE tenant_id=(SELECT id FROM aria_tenants WHERE bot_token=$1) "
        "AND is_active = TRUE ORDER BY position, id",
        bot_token,
    )
    return aio_web.json_response([dict(r) for r in rows])


async def _handle_services(request: aio_web.Request) -> aio_web.Response:
    category_id = int(request.match_info["category_id"])
    pool = request.app["pool"]
    rows = await pool.fetch(
        "SELECT id, name, price, duration_minutes FROM aria_service_items "
        "WHERE category_id=$1 AND is_active = TRUE ORDER BY position, id",
        category_id,
    )
    return aio_web.json_response([dict(r) for r in rows])


async def _handle_slots(request: aio_web.Request) -> aio_web.Response:
    date_str = request.match_info["date"]
    # TD-002: conflict checking not implemented yet — returns fixed 09:00-18:00 hourly slots
    slots = [f"{h:02d}:00" for h in range(9, 19)]
    return aio_web.json_response({"date": date_str, "slots": slots})


async def _handle_booking(request: aio_web.Request) -> aio_web.Response:
    bot_token = request.match_info["bot_token"]
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    if not _validate_init_data(init_data, bot_token):
        return aio_web.json_response({"error": "unauthorized"}, status=401)

    pool = request.app["pool"]
    bots: dict[int, Bot] = request.app["bots"]

    body = await request.json()

    tenant_row = await pool.fetchrow(
        "SELECT id, owner_tg_id FROM aria_tenants WHERE bot_token=$1",
        bot_token,
    )
    if not tenant_row:
        return aio_web.json_response({"error": "tenant not found"}, status=404)

    user_id = _parse_user_id(init_data) or body.get("user_id", 0)

    try:
        scheduled_at = datetime.fromisoformat(body["scheduled_at"])
    except (KeyError, ValueError) as exc:
        return aio_web.json_response({"error": f"invalid scheduled_at: {exc}"}, status=400)

    booking_id = await repo.create_booking(
        tenant_id=tenant_row["id"],
        user_id=user_id,
        client_name=body["client_name"],
        service=body["service"],
        scheduled_at=scheduled_at,
    )

    bot = bots.get(tenant_row["id"])
    if bot and tenant_row["owner_tg_id"]:
        await notify_owner(bot, tenant_row["owner_tg_id"], {
            "client_name": body["client_name"],
            "client_phone": body.get("client_phone"),
            "service": body["service"],
            "scheduled_at": body["scheduled_at"],
        })

    return aio_web.json_response({"ok": True, "booking_id": booking_id})


def _make_api_app(pool, bots: dict) -> aio_web.Application:
    app = aio_web.Application(middlewares=[_cors_middleware])
    app["pool"] = pool
    app["bots"] = bots
    app.router.add_get("/api/{bot_token}/categories", _handle_categories)
    app.router.add_get("/api/{bot_token}/services/{category_id}", _handle_services)
    app.router.add_get("/api/{bot_token}/slots/{date}", _handle_slots)
    app.router.add_post("/api/{bot_token}/booking", _handle_booking)
    app.router.add_route("OPTIONS", "/api/{bot_token}/booking", _handle_booking)
    return app


# ── Entry point ───────────────────────────────────────────────────────────────

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
    pool = await repo.get_pool(settings.DATABASE_URL)
    await _ensure_initial_tenant()
    get_scheduler().start()
    schedule_daily_reactivation(lambda: _bots)
    schedule_owner_reminders(lambda: _bots)

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

    api_port = int(os.getenv("PORT_API", 8081))
    api_app = _make_api_app(pool, _bots)
    runner = aio_web.AppRunner(api_app)
    await runner.setup()
    site = aio_web.TCPSite(runner, "0.0.0.0", api_port)
    await site.start()
    log.info("Mini App API listening on port %d", api_port)

    watch_task = asyncio.create_task(_watch_tenants(dp))
    await stop_event.wait()

    log.info("Cancelling %d polling tasks...", len(_tasks))
    watch_task.cancel()
    for task in _tasks.values():
        task.cancel()
    await asyncio.gather(*_tasks.values(), watch_task, return_exceptions=True)
    await runner.cleanup()
    await close_pool()
    log.info("Aria shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
