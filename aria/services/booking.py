"""
Booking adapters for Aria — multi-tenant.

LocalAdapter   – internal Postgres store (always available)
GoogleAdapter  – Google Calendar as source of truth

Each tenant gets its own adapter instance cached by tenant_id.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

import aria.db.repo as repo

if TYPE_CHECKING:
    from aria.tenant import TenantConfig

log = logging.getLogger(__name__)

_adapters: dict[int, "BookingAdapter"] = {}


def parse_datetime(date_str: str, time_str: str, tz_str: str = "UTC") -> Optional[datetime]:
    try:
        from zoneinfo import ZoneInfo
        d = date.fromisoformat(date_str)
        h, m = map(int, time_str.split(":"))
        tz = ZoneInfo(tz_str)
        local_dt = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
        return local_dt.astimezone(timezone.utc)
    except (ValueError, TypeError, Exception):
        return None


def _parse_gcal_dt(value: str) -> Optional[datetime]:
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        return datetime.fromisoformat(value + "T00:00:00+00:00")
    except ValueError:
        return None


def _slot_times(tenant: "TenantConfig", target_date: date) -> list[datetime]:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    slots: list[datetime] = []
    h, m = tenant.open_hour, 0
    while h < tenant.close_hour:
        local_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=tz)
        slots.append(local_dt.astimezone(timezone.utc))
        total = h * 60 + m + tenant.slot_minutes
        h, m = divmod(total, 60)
    return slots


def _is_working_day(tenant: "TenantConfig", d: date) -> bool:
    return d.isoweekday() in tenant.working_days_list


# ── Abstract adapter ──────────────────────────────────────────────────────────

class BookingAdapter(ABC):

    @abstractmethod
    async def get_events(self, date_from: datetime, date_to: datetime) -> list[dict]: ...

    @abstractmethod
    async def is_available(self, dt: datetime, service: str) -> bool: ...

    @abstractmethod
    async def get_alternatives(self, dt: datetime, service: str, count: int = 2) -> list[datetime]: ...

    @abstractmethod
    async def create_event(
        self, user_id: int, client_name: str, service: str, dt: datetime
    ) -> tuple[int, Optional[str]]: ...

    @abstractmethod
    async def update_event(
        self, booking_id: int, calendar_event_id: Optional[str], new_dt: datetime
    ) -> None: ...

    @abstractmethod
    async def delete_event(
        self, booking_id: int, calendar_event_id: Optional[str]
    ) -> None: ...


# ── Local adapter ─────────────────────────────────────────────────────────────

class LocalAdapter(BookingAdapter):
    def __init__(self, tenant: "TenantConfig") -> None:
        self._t = tenant

    async def get_events(self, date_from: datetime, date_to: datetime) -> list[dict]:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self._t.timezone or "UTC")
        rows = await repo.get_bookings_in_range(self._t.id, date_from, date_to)
        return [
            {
                "id": r["id"],
                "title": f"{r['service']} — {r['client_name']}",
                "client": r["client_name"],
                "service": r["service"],
                "date": r["scheduled_at"].astimezone(tz).strftime("%Y-%m-%d"),
                "time": r["scheduled_at"].astimezone(tz).strftime("%H:%M"),
                "status": r["status"],
            }
            for r in rows
        ]

    async def is_available(self, dt: datetime, service: str) -> bool:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self._t.timezone or "UTC")
        local_dt = dt.astimezone(tz)
        if not _is_working_day(self._t, local_dt.date()):
            return False
        if not (self._t.open_hour <= local_dt.hour < self._t.close_hour):
            return False
        booked = await repo.get_slots_on_date(self._t.id, dt.strftime("%Y-%m-%d"))
        return dt not in booked

    async def get_alternatives(self, dt: datetime, service: str, count: int = 2) -> list[datetime]:
        booked = set(await repo.get_slots_on_date(self._t.id, dt.strftime("%Y-%m-%d")))
        candidates: list[datetime] = []
        for off in range(0, 7):
            d = (dt + timedelta(days=off)).date()
            if not _is_working_day(self._t, d):
                continue
            for slot in _slot_times(self._t, d):
                if slot != dt and slot not in booked and slot > datetime.now(timezone.utc):
                    candidates.append(slot)
            if len(candidates) >= count:
                break
        return candidates[:count]

    async def create_event(self, user_id: int, client_name: str, service: str, dt: datetime) -> tuple[int, Optional[str]]:
        bid = await repo.create_booking(self._t.id, user_id, client_name, service, dt)
        return bid, None

    async def update_event(self, booking_id: int, calendar_event_id: Optional[str], new_dt: datetime) -> None:
        await repo.update_booking_time(booking_id, new_dt)

    async def delete_event(self, booking_id: int, calendar_event_id: Optional[str]) -> None:
        pass  # local adapter: status is updated in DB by caller, nothing else to do


# ── Google Calendar adapter ───────────────────────────────────────────────────

class GoogleAdapter(BookingAdapter):
    def __init__(self, tenant: "TenantConfig", creds_json: str) -> None:
        import json as _json
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        self._t = tenant
        creds_data = _json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_data, scopes=["https://www.googleapis.com/auth/calendar"]
        )
        self._svc = build("calendar", "v3", credentials=creds)
        self._cal = tenant.google_cal_id

    def _list_events_sync(self, tmin: str, tmax: str) -> list[dict]:
        return (
            self._svc.events()
            .list(calendarId=self._cal, timeMin=tmin, timeMax=tmax,
                  singleEvents=True, orderBy="startTime")
            .execute()
            .get("items", [])
        )

    def _freebusy_sync(self, tmin: str, tmax: str) -> list[dict]:
        body = {"timeMin": tmin, "timeMax": tmax, "items": [{"id": self._cal}]}
        return (
            self._svc.freebusy().query(body=body).execute()
            ["calendars"].get(self._cal, {}).get("busy", [])
        )

    def _insert_sync(self, event: dict) -> dict:
        return self._svc.events().insert(calendarId=self._cal, body=event).execute()

    def _patch_sync(self, event_id: str, body: dict) -> None:
        self._svc.events().patch(calendarId=self._cal, eventId=event_id, body=body).execute()

    def _delete_sync(self, event_id: str) -> None:
        self._svc.events().delete(calendarId=self._cal, eventId=event_id).execute()

    async def get_events(self, date_from: datetime, date_to: datetime) -> list[dict]:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self._t.timezone or "UTC")
        items = await asyncio.to_thread(self._list_events_sync, date_from.isoformat(), date_to.isoformat())
        events: list[dict] = []
        for item in items:
            raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
            dt = _parse_gcal_dt(raw)
            if dt is None:
                continue
            local_dt = dt.astimezone(tz)
            summary = item.get("summary", "")
            service, client = (summary.split(" — ", 1) if " — " in summary else ("", summary))
            events.append({
                "id": item.get("id"),
                "title": summary,
                "client": client.strip(),
                "service": service.strip(),
                "date": local_dt.strftime("%Y-%m-%d"),
                "time": local_dt.strftime("%H:%M"),
                "description": item.get("description", ""),
            })
        return events

    async def _busy_times(self, dt: datetime) -> set[datetime]:
        day_start = datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=timezone.utc)
        busy = await asyncio.to_thread(
            self._freebusy_sync, day_start.isoformat(), (day_start + timedelta(days=1)).isoformat()
        )
        result: set[datetime] = set()
        for b in busy:
            s = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
            result.add(s.replace(second=0, microsecond=0))
        return result

    async def is_available(self, dt: datetime, service: str) -> bool:
        if not _is_working_day(self._t, dt.date()):
            return False
        return dt not in await self._busy_times(dt)

    async def get_alternatives(self, dt: datetime, service: str, count: int = 2) -> list[datetime]:
        candidates: list[datetime] = []
        for off in range(0, 7):
            d = (dt + timedelta(days=off)).date()
            if not _is_working_day(self._t, d):
                continue
            ref = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            busy = await self._busy_times(ref)
            for slot in _slot_times(self._t, d):
                if slot != dt and slot not in busy and slot > datetime.now(timezone.utc):
                    candidates.append(slot)
            if len(candidates) >= count:
                break
        return candidates[:count]

    async def create_event(self, user_id: int, client_name: str, service: str, dt: datetime) -> tuple[int, Optional[str]]:
        end_dt = dt + timedelta(minutes=self._t.slot_minutes)
        tz_name = self._t.timezone or "UTC"
        body = {
            "summary": f"{service} — {client_name}",
            "description": f"Telegram user_id: {user_id}",
            "start": {"dateTime": dt.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz_name},
        }
        created = await asyncio.to_thread(self._insert_sync, body)
        cal_id = created.get("id")
        bid = await repo.create_booking(self._t.id, user_id, client_name, service, dt, cal_id)
        return bid, cal_id

    async def update_event(self, booking_id: int, calendar_event_id: Optional[str], new_dt: datetime) -> None:
        await repo.update_booking_time(booking_id, new_dt)
        if not calendar_event_id:
            return
        end_dt = new_dt + timedelta(minutes=self._t.slot_minutes)
        tz_name = self._t.timezone or "UTC"
        await asyncio.to_thread(self._patch_sync, calendar_event_id, {
            "start": {"dateTime": new_dt.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz_name},
        })

    async def delete_event(self, booking_id: int, calendar_event_id: Optional[str]) -> None:
        if not calendar_event_id:
            return
        try:
            await asyncio.to_thread(self._delete_sync, calendar_event_id)
        except Exception as exc:
            if "410" in str(exc) or "404" in str(exc):
                pass  # already deleted in GCal — that's fine
            else:
                raise


# ── Factory ───────────────────────────────────────────────────────────────────

def get_adapter(tenant: "TenantConfig") -> BookingAdapter:
    if tenant.id not in _adapters:
        cal_id = tenant.google_cal_id
        # Per-tenant credentials take priority; fall back to platform service account
        creds_json = tenant.google_cal_credentials
        if not creds_json:
            from aria.config import settings
            creds_json = settings.GOOGLE_CALENDAR_CREDENTIALS

        if creds_json and cal_id:
            try:
                _adapters[tenant.id] = GoogleAdapter(tenant, creds_json)
                log.info("Tenant %d: Google Calendar adapter (cal=%s)", tenant.id, cal_id)
            except Exception as exc:
                log.warning("Tenant %d: Google Calendar init failed (%s), using local", tenant.id, exc)
                _adapters[tenant.id] = LocalAdapter(tenant)
        else:
            if cal_id:
                log.warning("Tenant %d: google_cal_id set but no service account configured", tenant.id)
            _adapters[tenant.id] = LocalAdapter(tenant)
            log.info("Tenant %d: local Postgres adapter", tenant.id)
    return _adapters[tenant.id]


def invalidate_adapter(tenant_id: int) -> None:
    """Call when a tenant's Google Calendar config changes."""
    _adapters.pop(tenant_id, None)
