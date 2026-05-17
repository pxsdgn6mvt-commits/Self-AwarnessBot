"""
Booking service for Aria.

Two adapters are available:
  LocalAdapter   – uses internal Postgres schedule (always available)
  GoogleAdapter  – syncs with Google Calendar (enabled via env vars)

The factory function `get_adapter()` returns the right one based on config.
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


# ── Slot helpers ───────────────────────────────────────────────────────────────

def _slot_times(target_date: date) -> list[datetime]:
    """Generate all possible slot datetimes for a given date."""
    slots: list[datetime] = []
    current_hour = settings.SALON_OPEN_HOUR
    current_min = 0
    slot_step = settings.SALON_SLOT_MINUTES

    while True:
        dt = datetime(
            target_date.year, target_date.month, target_date.day,
            current_hour, current_min, tzinfo=timezone.utc
        )
        if dt.hour >= settings.SALON_CLOSE_HOUR:
            break
        slots.append(dt)
        total_mins = current_hour * 60 + current_min + slot_step
        current_hour, current_min = divmod(total_mins, 60)

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


# ── Abstract adapter ───────────────────────────────────────────────────────────

class BookingAdapter(ABC):
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

    @abstractmethod
    async def delete_event(
        self, booking_id: Optional[int], calendar_event_id: Optional[str]
    ) -> None:
        """Cancel/delete an event. booking_id=None for GCal-only external events."""
        ...

    @abstractmethod
    async def get_events(self, date_from: date, date_to: date) -> list[dict]:
        """Return events in [date_from, date_to] as list of dicts with keys:
        id (int db id or str gcal id), gcal_event_id, service, date, time, client_name.
        """
        ...


# ── Local adapter (Postgres only) ─────────────────────────────────────────────

class LocalAdapter(BookingAdapter):
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
                if slot == dt:
                    continue
                if slot not in booked and slot > datetime.now(timezone.utc):
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

    async def delete_event(
        self, booking_id: Optional[int], calendar_event_id: Optional[str]
    ) -> None:
        if booking_id is not None:
            await repo.update_booking_status(booking_id, "cancelled")

    async def get_events(self, date_from: date, date_to: date) -> list[dict]:
        rows = await repo.get_bookings_in_range(date_from, date_to)
        return [
            {
                "id": row["id"],
                "gcal_event_id": row.get("calendar_event_id"),
                "service": row["service"],
                "date": row["scheduled_at"].strftime("%Y-%m-%d"),
                "time": row["scheduled_at"].strftime("%H:%M"),
                "client_name": row.get("client_name", ""),
            }
            for row in rows
        ]


# ── Google Calendar adapter ───────────────────────────────────────────────────

class GoogleAdapter(BookingAdapter):
    """
    Requires:
        GOOGLE_CALENDAR_CREDENTIALS  – service-account JSON (as string)
        GOOGLE_CALENDAR_ID           – target calendar id
    """

    def __init__(self) -> None:
        import json
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_json = json.loads(settings.GOOGLE_CALENDAR_CREDENTIALS)  # type: ignore[arg-type]
        scopes = ["https://www.googleapis.com/auth/calendar"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_json, scopes=scopes
        )
        self._service = build("calendar", "v3", credentials=credentials)
        self._calendar_id = settings.GOOGLE_CALENDAR_ID

    def _busy_times(self, dt: datetime) -> set[datetime]:
        """Query free/busy for the given date."""
        day_start = datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        body = {
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "items": [{"id": self._calendar_id}],
        }
        result = self._service.freebusy().query(body=body).execute()
        busy = result["calendars"].get(self._calendar_id, {}).get("busy", [])
        occupied: set[datetime] = set()
        for interval in busy:
            start = datetime.fromisoformat(interval["start"].replace("Z", "+00:00"))
            occupied.add(start.replace(second=0, microsecond=0))
        return occupied

    async def is_available(self, dt: datetime, service: str) -> bool:
        if not _is_working_day(dt.date()):
            return False
        busy = self._busy_times(dt)
        return dt not in busy

    async def get_alternatives(
        self, dt: datetime, service: str, count: int = 2
    ) -> list[datetime]:
        candidates: list[datetime] = []
        for offset_days in range(0, 7):
            target_date = (dt + timedelta(days=offset_days)).date()
            if not _is_working_day(target_date):
                continue
            busy = self._busy_times(
                datetime(target_date.year, target_date.month, target_date.day,
                         tzinfo=timezone.utc)
            )
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
        event = {
            "summary": f"{service} — {client_name}",
            "description": f"Telegram user_id: {user_id}",
            "start": {"dateTime": dt.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        }
        created = (
            self._service.events()
            .insert(calendarId=self._calendar_id, body=event)
            .execute()
        )
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
        self._service.events().patch(
            calendarId=self._calendar_id,
            eventId=calendar_event_id,
            body={
                "start": {"dateTime": new_dt.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
            },
        ).execute()

    async def delete_event(
        self, booking_id: Optional[int], calendar_event_id: Optional[str]
    ) -> None:
        if booking_id is not None:
            await repo.update_booking_status(booking_id, "cancelled")
        if not calendar_event_id:
            return

        def _del_sync() -> None:
            self._service.events().delete(
                calendarId=self._calendar_id, eventId=calendar_event_id
            ).execute()

        try:
            await asyncio.to_thread(_del_sync)
        except Exception as exc:
            if "404" in str(exc) or "410" in str(exc):
                pass  # already deleted — fine
            else:
                raise

    async def get_events(self, date_from: date, date_to: date) -> list[dict]:
        time_min = datetime(date_from.year, date_from.month, date_from.day,
                            tzinfo=timezone.utc).isoformat()
        time_max = (datetime(date_to.year, date_to.month, date_to.day,
                             tzinfo=timezone.utc) + timedelta(days=1)).isoformat()

        def _list_sync() -> list:
            result = self._service.events().list(
                calendarId=self._calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return result.get("items", [])

        gcal_items = await asyncio.to_thread(_list_sync)
        gcal_ids = [e["id"] for e in gcal_items]
        cal_to_db = await repo.get_bookings_by_gcal_ids(gcal_ids)

        events: list[dict] = []
        for e in gcal_items:
            gcal_id = e["id"]
            start_info = e.get("start", {})
            raw_start = start_info.get("dateTime") or start_info.get("date", "")
            try:
                dt = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            events.append({
                "id": cal_to_db.get(gcal_id, gcal_id),  # int if in DB, else str gcal id
                "gcal_event_id": gcal_id,
                "service": e.get("summary", ""),
                "date": dt.strftime("%Y-%m-%d"),
                "time": dt.strftime("%H:%M"),
                "client_name": "",
            })
        return events


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
