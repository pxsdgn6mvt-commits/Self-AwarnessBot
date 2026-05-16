"""Google Calendar integration — direct REST, no heavy SDK."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests as _requests

import aria.db.repo as repo

log = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/calendar"


def _client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET", "")


def _callback_uri() -> str:
    base = os.getenv("ARIA_PUBLIC_URL", "").rstrip("/")
    return f"{base}/gcal/callback"


def get_auth_url(tenant_id: int) -> str:
    params = {
        "client_id": _client_id(),
        "redirect_uri": _callback_uri(),
        "response_type": "code",
        "scope": _SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": str(tenant_id),
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)


def exchange_code_sync(code: str) -> Optional[dict]:
    resp = _requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "code": code,
            "redirect_uri": _callback_uri(),
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if resp.ok:
        return resp.json()
    log.error("GCal token exchange failed: %s %s", resp.status_code, resp.text)
    return None


def _refresh_sync(refresh_token: str) -> Optional[dict]:
    resp = _requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    if resp.ok:
        return resp.json()
    log.error("GCal token refresh failed: %s %s", resp.status_code, resp.text)
    return None


async def _valid_token(tenant_id: int) -> Optional[str]:
    """Return a valid access token, refreshing if it expires within 60 s."""
    row = await repo.get_gcal_tokens(tenant_id)
    if not row or not row["gcal_refresh_token"]:
        return None

    expiry = row["gcal_token_expiry"]
    if expiry and expiry.timestamp() > time.time() + 60:
        return row["gcal_access_token"]

    # Need refresh
    result = await asyncio.get_event_loop().run_in_executor(
        None, _refresh_sync, row["gcal_refresh_token"]
    )
    if not result:
        return None

    access_token = result["access_token"]
    expires_in = result.get("expires_in", 3600)
    expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    await repo.update_gcal_access_token(tenant_id, access_token, expiry_dt)
    return access_token


async def is_connected(tenant_id: int) -> bool:
    row = await repo.get_gcal_tokens(tenant_id)
    return bool(row and row["gcal_refresh_token"])


def _create_sync(access_token: str, calendar_id: str, event: dict) -> Optional[dict]:
    cal = urllib.parse.quote(calendar_id, safe="")
    resp = _requests.post(
        f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=event,
        timeout=15,
    )
    if resp.ok:
        return resp.json()
    log.error("GCal create event failed: %s %s", resp.status_code, resp.text)
    return None


def _delete_sync(access_token: str, calendar_id: str, event_id: str) -> None:
    cal = urllib.parse.quote(calendar_id, safe="")
    _requests.delete(
        f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events/{event_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )


async def create_event(
    tenant_id: int,
    client_name: str,
    service: str,
    scheduled_at: datetime,
    duration_minutes: int = 60,
    tz: str = "Europe/Moscow",
) -> Optional[tuple[str, str]]:
    """Create a GCal event. Returns (event_id, html_link) or None."""
    token = await _valid_token(tenant_id)
    if not token:
        return None

    row = await repo.get_gcal_tokens(tenant_id)
    calendar_id = (row["gcal_calendar_id"] if row else None) or "primary"

    # Make dt timezone-aware
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
        None, _create_sync, token, calendar_id, event_body
    )
    if result:
        return result.get("id", ""), result.get("htmlLink", "")
    return None


async def delete_event(tenant_id: int, event_id: str) -> None:
    token = await _valid_token(tenant_id)
    if not token:
        return
    row = await repo.get_gcal_tokens(tenant_id)
    calendar_id = (row["gcal_calendar_id"] if row else None) or "primary"
    await asyncio.get_event_loop().run_in_executor(
        None, _delete_sync, token, calendar_id, event_id
    )
