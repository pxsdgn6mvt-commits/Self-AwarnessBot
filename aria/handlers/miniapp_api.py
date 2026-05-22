"""Mini App HTTP API — aiohttp web application.

POST /api/booking  — create a booking from the Mini App and trigger
                     a non-blocking GCal sync for the tenant (DECISION-010/011).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiohttp import web

import aria.db.repo as repo
import aria.services.gcal as gcal

log = logging.getLogger(__name__)

# Keep task references alive to prevent premature GC (fire-and-forget pattern).
_background_tasks: set[asyncio.Task] = set()


def _fire(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _post_booking(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    tenant_id_raw = data.get("tenant_id")
    client_name = str(data.get("client_name") or "").strip()
    service = str(data.get("service") or "").strip()
    scheduled_at_raw = data.get("scheduled_at")

    if not tenant_id_raw or not client_name or not service or not scheduled_at_raw:
        return web.json_response(
            {"error": "tenant_id, client_name, service, scheduled_at are required"},
            status=400,
        )

    try:
        tenant_id = int(tenant_id_raw)
    except (ValueError, TypeError):
        return web.json_response({"error": "tenant_id must be an integer"}, status=400)

    try:
        scheduled_at = datetime.fromisoformat(str(scheduled_at_raw))
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return web.json_response(
            {"error": "invalid scheduled_at, use ISO 8601 (e.g. 2026-05-25T14:00:00)"},
            status=400,
        )

    phone = str(data.get("phone") or "").strip()
    duration_minutes = int(data.get("duration_minutes") or 60)

    tenant_row = await repo.get_tenant(tenant_id)
    if tenant_row is None:
        return web.json_response({"error": "tenant not found"}, status=404)

    booking_id = await repo.create_booking(
        tenant_id=tenant_id,
        user_id=0,
        client_name=client_name,
        service=service,
        scheduled_at=scheduled_at,
    )

    if phone:
        await repo.set_booking_note(booking_id, f"Телефон: {phone}")

    credentials_json: Optional[str] = tenant_row["google_cal_credentials"]
    calendar_id: Optional[str] = tenant_row["google_cal_id"]
    tenant_tz: str = tenant_row.get("timezone") or "UTC"

    _fire(_sync_to_gcal(
        booking_id=booking_id,
        tenant_id=tenant_id,
        credentials_json=credentials_json,
        calendar_id=calendar_id,
        booking={
            "client_name": client_name,
            "phone": phone,
            "service": service,
            "scheduled_at": scheduled_at,
            "duration_minutes": duration_minutes,
            "timezone": tenant_tz,
        },
    ))

    return web.json_response({"ok": True, "booking_id": booking_id}, status=201)


async def _sync_to_gcal(
    booking_id: int,
    tenant_id: int,
    credentials_json: Optional[str],
    calendar_id: Optional[str],
    booking: dict,
) -> None:
    if not credentials_json or not calendar_id:
        log.warning(
            "Tenant %d: no GCal credentials or calendar_id — skipping sync for booking %d",
            tenant_id, booking_id,
        )
        return

    event_id = await gcal.create_booking_event(credentials_json, calendar_id, booking)
    if event_id:
        await repo.set_booking_gcal_event_id(booking_id, event_id)
        log.info("Tenant %d: GCal event %s linked to booking %d", tenant_id, event_id, booking_id)
    else:
        log.warning(
            "Tenant %d: GCal event creation failed for booking %d — gcal_event_id=NULL",
            tenant_id, booking_id,
        )


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/api/booking", _post_booking)
    return app
