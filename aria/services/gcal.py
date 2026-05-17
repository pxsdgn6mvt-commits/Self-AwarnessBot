"""Google Calendar via Service Account — no OAuth browser flow, no redirect URIs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests as _requests

log = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/calendar"
_token_cache: dict = {"token": None, "expires_at": 0.0}


def is_configured() -> bool:
    return bool(os.getenv("GOOGLE_CALENDAR_CREDENTIALS"))


def add_to_calendar_url(
    title: str, start: datetime, duration_minutes: int, details: str = ""
) -> str:
    """Fallback pre-filled URL when service account not configured."""
    end = start + timedelta(minutes=duration_minutes)
    fmt = "%Y%m%dT%H%M%S"
    params: dict = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start.strftime(fmt)}/{end.strftime(fmt)}",
    }
    if details:
        params["details"] = details
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)


def _get_access_token() -> Optional[str]:
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    creds_json = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "")
    if not creds_json:
        return None
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as ga_req
        creds = service_account.Credentials.from_service_account_info(
            json.loads(creds_json), scopes=[_SCOPE]
        )
        creds.refresh(ga_req.Request())
        _token_cache["token"] = creds.token
        _token_cache["expires_at"] = now + 3500
        return creds.token
    except Exception as exc:
        log.error("GCal service account auth failed: %s", exc)
        return None


def _setup_calendar_sync(owner_email: str, salon_name: str) -> Optional[str]:
    token = _get_access_token()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = _requests.post(
        "https://www.googleapis.com/calendar/v3/calendars",
        headers=headers,
        json={"summary": f"Aria — {salon_name}"},
        timeout=15,
    )
    if not resp.ok:
        log.error("Failed to create GCal calendar: %s %s", resp.status_code, resp.text)
        return None

    calendar_id = resp.json()["id"]

    _requests.post(
        f"https://www.googleapis.com/calendar/v3/calendars"
        f"/{urllib.parse.quote(calendar_id, safe='')}/acl",
        headers=headers,
        json={"role": "writer", "scope": {"type": "user", "value": owner_email}},
        timeout=15,
    )
    return calendar_id


async def setup_calendar(owner_email: str, salon_name: str) -> Optional[str]:
    """Create a dedicated calendar and share with owner. Returns calendar_id."""
    return await asyncio.get_event_loop().run_in_executor(
        None, _setup_calendar_sync, owner_email, salon_name
    )


async def is_connected(tenant_id: int) -> bool:
    if not is_configured():
        return False
    import aria.db.repo as repo
    row = await repo.get_gcal_tokens(tenant_id)
    cal_id = row["gcal_calendar_id"] if row else None
    return bool(cal_id and cal_id != "primary")


def _create_sync(calendar_id: str, event: dict) -> Optional[dict]:
    token = _get_access_token()
    if not token:
        return None
    cal = urllib.parse.quote(calendar_id, safe="")
    resp = _requests.post(
        f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=event,
        timeout=15,
    )
    if resp.ok:
        return resp.json()
    log.error("GCal create event failed: %s %s", resp.status_code, resp.text)
    return None


def _delete_sync(calendar_id: str, event_id: str) -> None:
    token = _get_access_token()
    if not token:
        return
    cal = urllib.parse.quote(calendar_id, safe="")
    ev  = urllib.parse.quote(event_id, safe="")
    _requests.delete(
        f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events/{ev}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )


async def delete_event(tenant_id: int, event_id: str) -> None:
    import aria.db.repo as repo
    if not event_id:
        return
    row = await repo.get_gcal_tokens(tenant_id)
    calendar_id = (row["gcal_calendar_id"] if row else None) or "primary"
    if calendar_id == "primary":
        return
    await asyncio.get_event_loop().run_in_executor(
        None, _delete_sync, calendar_id, event_id
    )


async def create_event(
    tenant_id: int,
    client_name: str,
    service: str,
    scheduled_at: datetime,
    duration_minutes: int = 60,
    tz: str = "Europe/Moscow",
) -> Optional[tuple[str, str]]:
    import aria.db.repo as repo
    row = await repo.get_gcal_tokens(tenant_id)
    calendar_id = (row["gcal_calendar_id"] if row else None) or "primary"
    if calendar_id == "primary":
        return None

    if scheduled_at.tzinfo is None:
        try:
            import zoneinfo
            scheduled_at = scheduled_at.replace(tzinfo=zoneinfo.ZoneInfo(tz))
        except Exception:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

    end_at = scheduled_at + timedelta(minutes=duration_minutes)
    event_body = {
        "summary": f"{service} — {client_name}",
        "description": f"Клиент: {client_name}\nУслуга: {service}",
        "start": {"dateTime": scheduled_at.isoformat(), "timeZone": tz},
        "end": {"dateTime": end_at.isoformat(), "timeZone": tz},
    }
    result = await asyncio.get_event_loop().run_in_executor(
        None, _create_sync, calendar_id, event_body
    )
    if result:
        return result.get("id", ""), result.get("htmlLink", "")
    return None
