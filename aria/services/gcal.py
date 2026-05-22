"""Google Calendar helpers for Mini App booking sync."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)


async def create_booking_event(
    credentials_json: str,
    calendar_id: str,
    booking: dict,
) -> Optional[str]:
    """Create a GCal event for a Mini App booking.

    Returns the GCal event ID on success, or None if credentials are missing
    or the API call fails. All exceptions are caught and logged.
    """
    if not credentials_json or not calendar_id:
        return None
    try:
        return await asyncio.to_thread(_insert_event_sync, credentials_json, calendar_id, booking)
    except Exception as exc:
        log.warning("GCal create_booking_event failed: %s", exc)
        return None


def _insert_event_sync(credentials_json: str, calendar_id: str, booking: dict) -> str:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from zoneinfo import ZoneInfo

    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    svc = build("calendar", "v3", credentials=creds)

    client_name: str = booking.get("client_name", "")
    service: str = booking.get("service", "")
    phone: str = booking.get("phone", "")
    scheduled_at: datetime = booking["scheduled_at"]
    duration_minutes: int = int(booking.get("duration_minutes") or 60)
    tz_name: str = booking.get("timezone") or "UTC"

    tz = ZoneInfo(tz_name)
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    local_dt = scheduled_at.astimezone(tz)
    end_dt = local_dt + timedelta(minutes=duration_minutes)

    description_lines = []
    if phone:
        description_lines.append(f"Телефон: {phone}")
    description_lines.append("Запись через Mini App")

    body = {
        "summary": f"{client_name} — {service}",
        "description": "\n".join(description_lines),
        "start": {"dateTime": local_dt.isoformat(), "timeZone": tz_name},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": tz_name},
    }

    created = svc.events().insert(calendarId=calendar_id, body=body).execute()
    return created["id"]
