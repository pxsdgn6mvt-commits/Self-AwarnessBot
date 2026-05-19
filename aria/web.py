"""Async HTTP API for the Mini App — runs inside the bot process via aiohttp."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import date as _date, datetime, timezone
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from aiohttp import web

from aria.db.repo import _p

log = logging.getLogger(__name__)

_MINIAPP_ORIGIN = os.getenv("MINIAPP_ORIGIN", "*")


@web.middleware
async def _cors(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
        resp.headers["Access-Control-Allow-Origin"] = _MINIAPP_ORIGIN
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp
    resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = _MINIAPP_ORIGIN
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def _verify_init_data(init_data: str, bot_token: str) -> dict | None:
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    check_hash = params.pop("hash", None)
    if not check_hash:
        return None
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, check_hash):
        return None
    return json.loads(params.get("user", "{}"))


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def _api_services(request: web.Request) -> web.Response:
    try:
        tenant_id = int(request.rel_url.query["tenant_id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "tenant_id required"}, status=400)

    try:
        pool = _p()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT sc.id AS cat_id, sc.name AS cat_name,
                       si.id, si.name, si.price, si.duration_minutes
                FROM aria_service_items si
                JOIN aria_service_categories sc ON si.category_id = sc.id
                WHERE sc.tenant_id = $1
                ORDER BY sc.position, sc.id, si.position, si.id
                """,
                tenant_id,
            )
    except Exception as exc:
        log.exception("api_services error")
        return web.json_response({"error": str(exc)}, status=500)

    cats: dict[int, dict] = {}
    for r in rows:
        cid = r["cat_id"]
        if cid not in cats:
            cats[cid] = {"id": cid, "name": r["cat_name"], "items": []}
        cats[cid]["items"].append({
            "id": r["id"],
            "name": r["name"],
            "price": float(r["price"]) if r["price"] is not None else None,
            "duration_minutes": r["duration_minutes"],
        })
    return web.json_response(list(cats.values()))


async def _api_slots(request: web.Request) -> web.Response:
    try:
        tenant_id = int(request.rel_url.query["tenant_id"])
        target_date = _date.fromisoformat(request.rel_url.query["date"])
    except (KeyError, ValueError):
        return web.json_response({"error": "tenant_id and date required"}, status=400)

    try:
        pool = _p()
        async with pool.acquire() as conn:
            tenant_row = await conn.fetchrow("SELECT * FROM aria_tenants WHERE id=$1", tenant_id)
            if not tenant_row:
                return web.json_response({"error": "tenant not found"}, status=404)
            booked_rows = await conn.fetch(
                """
                SELECT scheduled_at FROM aria_bookings
                WHERE tenant_id=$1 AND scheduled_at::date=$2 AND status='confirmed'
                """,
                tenant_id, target_date,
            )
    except Exception as exc:
        log.exception("api_slots error")
        return web.json_response({"error": str(exc)}, status=500)

    working_days = [int(d) for d in (tenant_row["working_days"] or "1,2,3,4,5,6").split(",")]
    if target_date.isoweekday() not in working_days:
        return web.json_response([])

    tz = ZoneInfo(tenant_row["timezone"] or "UTC")
    open_h  = tenant_row["open_hour"]  or 10
    close_h = tenant_row["close_hour"] or 20
    step    = tenant_row["slot_minutes"] or 60
    now_utc = datetime.now(timezone.utc)
    booked  = {r["scheduled_at"] for r in booked_rows}

    slots = []
    h, m = open_h, 0
    while h < close_h:
        slot_utc = datetime(
            target_date.year, target_date.month, target_date.day,
            h, m, tzinfo=tz,
        ).astimezone(timezone.utc)
        if slot_utc > now_utc and slot_utc not in booked:
            slots.append(f"{h:02d}:{m:02d}")
        h, m = divmod(h * 60 + m + step, 60)

    return web.json_response(slots)


async def _api_create_booking(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    tenant_id   = body.get("tenant_id")
    init_data   = body.get("initData", "")
    client_name = (body.get("client_name") or "").strip()
    service     = (body.get("service") or "").strip()
    date_str    = body.get("date", "")
    time_str    = body.get("time", "")

    if not all([tenant_id, client_name, service, date_str, time_str]):
        return web.json_response({"error": "tenant_id, client_name, service, date, time required"}, status=400)

    try:
        pool = _p()
        async with pool.acquire() as conn:
            tenant_row = await conn.fetchrow("SELECT * FROM aria_tenants WHERE id=$1", tenant_id)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)

    if not tenant_row:
        return web.json_response({"error": "tenant not found"}, status=404)

    tg_user = _verify_init_data(init_data, tenant_row["bot_token"])
    if tg_user is None:
        return web.json_response({"error": "invalid initData"}, status=403)

    client_tg_id = tg_user.get("id")

    try:
        d = _date.fromisoformat(date_str)
        h, m = map(int, time_str.split(":"))
        tz = ZoneInfo(tenant_row["timezone"] or "UTC")
        dt_utc = datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(timezone.utc)
    except Exception:
        return web.json_response({"error": "invalid date or time"}, status=400)

    if dt_utc <= datetime.now(timezone.utc):
        return web.json_response({"error": "slot is in the past"}, status=400)

    try:
        pool = _p()
        async with pool.acquire() as conn:
            conflict = await conn.fetch(
                "SELECT id FROM aria_bookings WHERE tenant_id=$1 AND scheduled_at=$2 AND status='confirmed'",
                tenant_id, dt_utc,
            )
            if conflict:
                return web.json_response({"error": "slot already taken"}, status=409)
            row = await conn.fetchrow(
                """
                INSERT INTO aria_bookings
                    (tenant_id, user_id, client_name, service, scheduled_at, client_tg_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                tenant_id, client_tg_id or 0, client_name, service, dt_utc, client_tg_id,
            )
            booking_id = row["id"]
    except Exception as exc:
        log.exception("api_create_booking error")
        return web.json_response({"error": str(exc)}, status=500)

    owner_tg_id = tenant_row["owner_tg_id"]
    bot_token   = tenant_row["bot_token"]
    if owner_tg_id and bot_token:
        import urllib.request as _ur
        try:
            local = dt_utc.astimezone(ZoneInfo(tenant_row["timezone"] or "UTC"))
            payload = json.dumps({
                "chat_id": owner_tg_id,
                "text": (
                    f"📅 <b>Новая запись через Mini App</b>\n\n"
                    f"Клиент: {client_name}\n"
                    f"Услуга: {service}\n"
                    f"Дата:   {local.strftime('%d.%m.%Y')} в {local.strftime('%H:%M')}\n"
                    f"Запись: #{booking_id}"
                ),
                "parse_mode": "HTML",
            }).encode()
            req = _ur.Request(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            _ur.urlopen(req, timeout=5)
        except Exception as exc:
            log.warning("Owner TG notification failed: %s", exc)

    return web.json_response({"booking_id": booking_id, "confirmed": True}, status=201)


async def _api_my_bookings(request: web.Request) -> web.Response:
    try:
        tenant_id = int(request.rel_url.query["tenant_id"])
        user_id   = int(request.rel_url.query["user_id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "tenant_id and user_id required"}, status=400)

    try:
        pool = _p()
        async with pool.acquire() as conn:
            tenant_row = await conn.fetchrow("SELECT timezone FROM aria_tenants WHERE id=$1", tenant_id)
            tz_str = (tenant_row["timezone"] if tenant_row else None) or "UTC"
            rows = await conn.fetch(
                """
                SELECT id, client_name, service, scheduled_at, status, paid
                FROM aria_bookings
                WHERE tenant_id=$1 AND client_tg_id=$2
                  AND status IN ('confirmed', 'pending')
                ORDER BY scheduled_at ASC
                """,
                tenant_id, user_id,
            )
    except Exception as exc:
        log.exception("api_my_bookings error")
        return web.json_response({"error": str(exc)}, status=500)

    tz = ZoneInfo(tz_str)
    return web.json_response([
        {
            "id": r["id"],
            "client_name": r["client_name"],
            "service": r["service"],
            "date": r["scheduled_at"].astimezone(tz).strftime("%Y-%m-%d"),
            "time": r["scheduled_at"].astimezone(tz).strftime("%H:%M"),
            "status": r["status"],
            "paid": r["paid"],
        }
        for r in rows
    ])


def create_app() -> web.Application:
    app = web.Application(middlewares=[_cors])
    app.router.add_get("/health", _health)
    app.router.add_get("/api/services", _api_services)
    app.router.add_get("/api/slots", _api_slots)
    app.router.add_post("/api/bookings", _api_create_booking)
    app.router.add_get("/api/my-bookings", _api_my_bookings)
    return app
