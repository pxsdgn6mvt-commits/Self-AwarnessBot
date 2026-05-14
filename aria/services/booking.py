"""
Booking service for Aria.

Two adapters:
  LocalAdapter   – internal Postgres store (always available, fallback)
  GoogleAdapter  – Google Calendar as source of truth (enabled via env vars)

When Google Calendar is active:
  - get_events()   reads ALL events from the calendar (including those synced
                   from external booking services like Yclients, Booksy, etc.)
  - create_event() writes to Google Calendar AND mirrors to Postgres
  - update_event() updates both stores

Setup for Google Calendar:
  1. Create a Google Cloud project, enable the Calendar API
  2. Create a Service Account, download credentials JSON
  3. Share the salon calendar with the service account email (Editor role)
  4. Set GOOGLE_CALENDAR_CREDENTIALS=<json string> and GOOGLE_CALENDAR_ID=<id>
     as Railway environment variables
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from aria.config import settings
import aria.db.repo as repo

log = logging.getLogger(__name__)


# ── Slot helpers ──────────────────────────────────────────────────────────────

def _slot_times(target_date: date) -> list[datetime]:
    slots: list[datetime] = []
    current_hour = settings.SALON_OPEN_HOUR
    current_min = 0
    step = settings.SALON_SLOT_MINUTES
    while True:
        dt = datetime(
            target_date.year, target_date.month, target_date.day,
            current_hour, current_min, tzinfo=timezone.utc
        )
        if dt.hour >= settings.SALON_CLOSE_HOUR:
            break
        slots.append(dt)
        total = current_hour * 60 + current_min + step
        current_hour, current_min = divmod(total, 60)
    return slots


def _is_working_day(target_date: date) -> bool:
    return target_date.isoweekday() in settings.working_days


def parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse 'YYYY-MM-DD' + 'HH:MM' into UTC datetime. Returns None on failure."""
    try:
        d = date.fromisoformat(date_str)
        h, m = map(int, time_str.split(":"))
        return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _parse_gcal_dt(value: str) -> Optional[datetime]:
    """Parse a Google Calendar dateTime or date string to UTC datetime."""
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        return datetime.fromisoformat(value + "T00:00:00+00:00")
    except ValueError:
        return None


# ── Abstract adapter ──────────────────────────────────────────────────────────

class BookingAdapter(ABC):

    @abstractmethod
    async def get_events(self, date_from: datetime, date_to: datetime) -> list[dict]:
        """
        Return all events/bookings between date_from and date_to (UTC).
        Each dict has: title, client, service, date (YYYY-MM-DD), time (HH:MM),
        and optionally id, description.
        """
        ...

    @abstractmethod
    async def is_available(self, dt: datetime, service: str) -> bool: ...

    @abstractmethod
    async def get_alternatives(
        self, dt: datetime, service: str, count: int = 2
    ) -> list[datetime]: ...

    @abstractmethod
    async def create_event(
        self, user_id: int, client_name: str, service: str, dt: datetime
    ) -> tuple[int, Optional[str]]:
        """Returns (booking_db_id, calendar_event_id)."""
        ...

    @abstractmethod
    async def update_event(
        self, booking_id: int, calendar_event_id: Optional[str], new_dt: datetime
    ) -> None: ...


# ── Local adapter (Postgres only) ─────────────────────────────────────────────

class LocalAdapter(BookingAdapter):

    async def get_events(self, date_from: datetime, date_to: datetime) -> list[dict]:
        bookings = await repo.get_bookings_in_range(date_from, date_to)
        return [
            {
                "id": b["id"],
                "title": f"{b['service']} — {b['client_name']}",
                "client": b["client_name"],
                "service": b["service"],
                "date": b["scheduled_at"].strftime("%Y-%m-%d"),
                "time": b["scheduled_at"].strftime("%H:%M"),
                "status": b["status"],
            }
            for b in bookings
        ]

    async def is_available(self, dt: datetime, service: str) -> bool:
        if not _is_working_day(dt.date()):
            return False
        if not (settings.SALON_OPEN_HOUR <= dt.hour < settings.SALON_CLOSE_HOUR):
            return False
        booked = await repo.get_slots_on_date(dt.strftime("%Y-%m-%d"))
        return dt not in booked

    async def get_alternatives(
        self, dt: datetime, service: str, count: int = 2
    ) -> list[datetime]:
        booked = set(await repo.get_slots_on_date(dt.strftime("%Y-%m-%d")))
        candidates: list[datetime] = []
        for offset_days in range(0, 7):
            target_date = (dt + timedelta(days=offset_days)).date()
            if not _is_working_day(target_date):
                continue
            for slot in _slot_times(target_date):
                if slot == dt or slot in booked:
                    continue
                if slot > datetime.now(timezone.utc):
                    candidates.append(slot)
            if len(candidates) >= count:
                break
        return candidates[:count]

    async def create_event(
        self, user_id: int, client_name: str, service: str, dt: datetime
    ) -> tuple[int, Optional[str]]:
        booking_id = await repo.create_booking(user_id, client_name, service, dt)
        return booking_id, None

    async def update_event(
        self, booking_id: int, calendar_event_id: Optional[str], new_dt: datetime
    ) -> None:
        await repo.update_booking_time(booking_id, new_dt)


# ── Google Calendar adapter ───────────────────────────────────────────────────

class GoogleAdapter(BookingAdapter):
    """
    Uses a Google service account to read/write the salon owner's calendar.

    All blocking Google API calls are wrapped in asyncio.to_thread so they
    don't block the bot's event loop.
    """

    def __init__(self) -> None:
        import json as _json
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_json = _json.loads(settings.GOOGLE_CALENDAR_CREDENTIALS)  # type: ignore[arg-type]
        scopes = ["https://www.googleapis.com/auth/calendar"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_json, scopes=scopes
        )
        self._service = build("calendar", "v3", credentials=credentials)
        self._cal_id = settings.GOOGLE_CALENDAR_ID

    # ── Internal helpers (sync, called via to_thread) ─────────────────────

    def _list_events_sync(self, time_min: str, time_max: str) -> list[dict]:
        result = (
            self._service.events()
            .list(
                calendarId=self._cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return result.get("items", [])

    def _freebusy_sync(self, time_min: str, time_max: str) -> list[dict]:
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": self._cal_id}],
        }
        result = self._service.freebusy().query(body=body).execute()
        return result["calendars"].get(self._cal_id, {}).get("busy", [])

    def _insert_event_sync(self, event: dict) -> dict:
        return (
            self._service.events()
            .insert(calendarId=self._cal_id, body=event)
            .execute()
        )

    def _patch_event_sync(self, event_id: str, body: dict) -> None:
        self._service.events().patch(
            calendarId=self._cal_id, eventId=event_id, body=body
        ).execute()

    # ── Adapter interface ─────────────────────────────────────────────────

    async def get_events(self, date_from: datetime, date_to: datetime) -> list[dict]:
        items = await asyncio.to_thread(
            self._list_events_sync,
            date_from.isoformat(),
            date_to.isoformat(),
        )
        events: list[dict] = []
        for item in items:
            start_info = item.get("start", {})
            raw = start_info.get("dateTime") or start_info.get("date", "")
            dt = _parse_gcal_dt(raw)
            if dt is None:
                continue
            summary = item.get("summary", "")
            # Events created by this bot use "Service — Client Name" format
            if " — " in summary:
                service_part, client_part = summary.split(" — ", 1)
            else:
                service_part, client_part = "", summary
            events.append({
                "id": item.get("id"),
                "title": summary,
                "client": client_part.strip(),
                "service": service_part.strip(),
                "date": dt.strftime("%Y-%m-%d"),
                "time": dt.strftime("%H:%M"),
                "description": item.get("description", ""),
            })
        return events

    async def _busy_times(self, dt: datetime) -> set[datetime]:
        day_start = datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        busy = await asyncio.to_thread(
            self._freebusy_sync,
            day_start.isoformat(),
            day_end.isoformat(),
        )
        occupied: set[datetime] = set()
        for interval in busy:
            start = datetime.fromisoformat(interval["start"].replace("Z", "+00:00"))
            occupied.add(start.replace(second=0, microsecond=0))
        return occupied

    async def is_available(self, dt: datetime, service: str) -> bool:
        if not _is_working_day(dt.date()):
            return False
        busy = await self._busy_times(dt)
        return dt not in busy

    async def get_alternatives(
        self, dt: datetime, service: str, count: int = 2
    ) -> list[datetime]:
        candidates: list[datetime] = []
        for offset_days in range(0, 7):
            target_date = (dt + timedelta(days=offset_days)).date()
            if not _is_working_day(target_date):
                continue
            ref = datetime(
                target_date.year, target_date.month, target_date.day,
                tzinfo=timezone.utc
            )
            busy = await self._busy_times(ref)
            for slot in _slot_times(target_date):
                if slot == dt or slot in busy:
                    continue
                if slot > datetime.now(timezone.utc):
                    candidates.append(slot)
            if len(candidates) >= count:
                break
        return candidates[:count]

    async def create_event(
        self, user_id: int, client_name: str, service: str, dt: datetime
    ) -> tuple[int, Optional[str]]:
        end_dt = dt + timedelta(minutes=settings.SALON_SLOT_MINUTES)
        event_body = {
            "summary": f"{service} — {client_name}",
            "description": f"Telegram user_id: {user_id}",
            "start": {"dateTime": dt.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        }
        created = await asyncio.to_thread(self._insert_event_sync, event_body)
        cal_event_id = created.get("id")
        booking_id = await repo.create_booking(
            user_id, client_name, service, dt, cal_event_id
        )
        return booking_id, cal_event_id

    async def update_event(
        self, booking_id: int, calendar_event_id: Optional[str], new_dt: datetime
    ) -> None:
        await repo.update_booking_time(booking_id, new_dt)
        if not calendar_event_id:
            return
        end_dt = new_dt + timedelta(minutes=settings.SALON_SLOT_MINUTES)
        await asyncio.to_thread(
            self._patch_event_sync,
            calendar_event_id,
            {
                "start": {"dateTime": new_dt.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
            },
        )


# ── Factory ───────────────────────────────────────────────────────────────────

_adapter: Optional[BookingAdapter] = None


def get_adapter() -> BookingAdapter:
    global _adapter
    if _adapter is not None:
        return _adapter

    if settings.GOOGLE_CALENDAR_CREDENTIALS and settings.GOOGLE_CALENDAR_ID:
        try:
            _adapter = GoogleAdapter()
            log.info("Using Google Calendar adapter")
            return _adapter
        except Exception as exc:
            log.warning("Google Calendar init failed (%s), falling back to local", exc)

    _adapter = LocalAdapter()
    log.info("Using local Postgres booking adapter")
    return _adapter
