"""AI service for Aria — Claude with tool use, per-tenant config."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TYPE_CHECKING

import anthropic

import aria.db.repo as repo
from aria.services.booking import get_adapter, parse_datetime

if TYPE_CHECKING:
    from aria.tenant import TenantConfig

log = logging.getLogger(__name__)

MAX_HISTORY = 40
MAX_TOOL_ROUNDS = 5

_clients: dict[str, anthropic.AsyncAnthropic] = {}


def _get_client(api_key: str) -> anthropic.AsyncAnthropic:
    if api_key not in _clients:
        _clients[api_key] = anthropic.AsyncAnthropic(api_key=api_key)
    return _clients[api_key]


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(tenant: "TenantConfig") -> str:
    from aria.config import settings
    has_creds = bool(tenant.google_cal_credentials or settings.GOOGLE_CALENDAR_CREDENTIALS)
    if has_creds and tenant.google_cal_id:
        calendar_line = f"Calendar: Google Calendar (ID: {tenant.google_cal_id}) — synced"
    else:
        calendar_line = "Calendar: local storage only (Google Calendar NOT connected)"

    return f"""You are Aria, the personal AI receptionist for {tenant.owner_name} at {tenant.salon_name}.

Your job is to help {tenant.owner_name} manage her appointment schedule. She is the salon owner — treat her as your boss.

WHAT YOU DO:
- Show the schedule for today, tomorrow, any specific date, or a date range
- Add new bookings that clients arranged via Instagram, WhatsApp, phone, or booking service
- Reschedule and cancel appointments
- Check whether a specific slot is free

LANGUAGE RULE — CRITICAL:
Respond ALWAYS in the exact same language {tenant.owner_name} uses in her message.
Russian message → Russian reply. English message → English reply. NEVER switch languages.

STYLE:
- Short and direct. She is busy.
- For schedules: bullet list with time and client name.
- Confirm every action: "Готово — Катя записана на 16 мая в 14:00".
- If something is unclear, ask one short question.
- NEVER say a booking was saved to Google Calendar unless the tool result contains "google_calendar": true.
- If tool result contains "error": "calendar_not_found" — tell the owner to share the calendar with the service account (check bot setup step).
- If tool result contains "error": "calendar_api_disabled" — tell the owner the Google Calendar API needs to be enabled in Google Cloud Console.

SALON INFO:
Salon: {tenant.salon_name}
Services: {tenant.services}
Working hours: {tenant.hours}
{calendar_line}
Timezone: {tenant.timezone}
Today: {{TODAY}}"""


# ── Tools ─────────────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "get_schedule",
        "description": "Get appointments for a date or date range. Use 'today'/'tomorrow' as shortcuts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD, 'today', or 'tomorrow'"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD — start of range"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD — end of range"},
            },
            "required": [],
        },
    },
    {
        "name": "check_availability",
        "description": "Check whether a specific date/time slot is free.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
                "service": {"type": "string"},
            },
            "required": ["date", "time", "service"],
        },
    },
    {
        "name": "add_booking",
        "description": "Add a new appointment (client booked via Instagram, WhatsApp, phone, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string"},
                "service": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
            },
            "required": ["client_name", "service", "date", "time"],
        },
    },
    {
        "name": "reschedule_booking",
        "description": "Move an existing booking to a new date/time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "integer"},
                "new_date": {"type": "string", "description": "YYYY-MM-DD"},
                "new_time": {"type": "string", "description": "HH:MM"},
            },
            "required": ["booking_id", "new_date", "new_time"],
        },
    },
    {
        "name": "cancel_booking",
        "description": "Cancel an appointment by booking ID.",
        "input_schema": {
            "type": "object",
            "properties": {"booking_id": {"type": "integer"}},
            "required": ["booking_id"],
        },
    },
    {
        "name": "get_upcoming",
        "description": "Get the next N upcoming appointments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many to return (default 10)"},
            },
            "required": [],
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_date(value: str, tz_str: str = "UTC") -> str:
    from zoneinfo import ZoneInfo
    v = value.lower()
    if v in ("today", "tomorrow"):
        from datetime import datetime as _dt
        now_local = _dt.now(ZoneInfo(tz_str))
        if v == "tomorrow":
            now_local = now_local + timedelta(days=1)
        return now_local.date().isoformat()
    return value


# ── Tool executor ─────────────────────────────────────────────────────────────

async def _exec_tool(name: str, args: dict, tenant: "TenantConfig", owner_id: int) -> str:
    adapter = get_adapter(tenant)

    tz_str = tenant.timezone or "UTC"

    if name == "get_schedule":
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_str)
        if args.get("date_from") and args.get("date_to"):
            from_str = _resolve_date(args["date_from"], tz_str)
            to_str   = _resolve_date(args["date_to"],   tz_str)
            dt_from = datetime.strptime(from_str, "%Y-%m-%d").replace(hour=0, minute=0, tzinfo=tz).astimezone(timezone.utc)
            dt_to   = datetime.strptime(to_str,   "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=tz).astimezone(timezone.utc)
        else:
            target  = _resolve_date(args.get("date") or "today", tz_str)
            dt_from = datetime.strptime(target, "%Y-%m-%d").replace(hour=0,  minute=0,  tzinfo=tz).astimezone(timezone.utc)
            dt_to   = datetime.strptime(target, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=tz).astimezone(timezone.utc)
        events = await adapter.get_events(dt_from, dt_to)
        return json.dumps({"date_from": _resolve_date(args.get("date_from") or args.get("date") or "today", tz_str),
                           "date_to":   _resolve_date(args.get("date_to")   or args.get("date") or "today", tz_str),
                           "count": len(events), "bookings": events})

    if name == "check_availability":
        dt = parse_datetime(args["date"], args["time"], tz_str)
        if dt is None:
            return json.dumps({"error": "invalid date/time"})
        return json.dumps({"available": await adapter.is_available(dt, args["service"]),
                           "date": args["date"], "time": args["time"]})

    if name == "add_booking":
        dt = parse_datetime(args["date"], args["time"], tz_str)
        if dt is None:
            return json.dumps({"error": "invalid date/time"})
        bid, cal_id = await adapter.create_event(owner_id, args["client_name"], args["service"], dt)
        return json.dumps({"booking_id": bid, "client": args["client_name"],
                           "service": args["service"], "date": args["date"],
                           "time": args["time"], "confirmed": True,
                           "google_calendar": cal_id is not None})

    if name == "reschedule_booking":
        new_dt = parse_datetime(args["new_date"], args["new_time"], tz_str)
        if new_dt is None:
            return json.dumps({"error": "invalid date/time"})
        booking = await repo.get_booking(args["booking_id"])
        if not booking:
            return json.dumps({"error": "booking not found"})
        await adapter.update_event(args["booking_id"], booking.get("calendar_event_id"), new_dt)
        return json.dumps({"rescheduled": True, "booking_id": args["booking_id"],
                           "new_date": args["new_date"], "new_time": args["new_time"]})

    if name == "cancel_booking":
        booking = await repo.get_booking(args["booking_id"])
        if not booking:
            return json.dumps({"error": "booking not found"})
        await repo.update_booking_status(args["booking_id"], "cancelled")
        await adapter.delete_event(args["booking_id"], booking.get("calendar_event_id"))
        return json.dumps({"cancelled": True, "booking_id": args["booking_id"]})

    if name == "get_upcoming":
        limit = int(args.get("limit") or 10)
        events = await adapter.get_events(
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=90),
        )
        return json.dumps({"bookings": events[:limit]})

    return json.dumps({"error": f"unknown tool: {name}"})


# ── Main entry point ──────────────────────────────────────────────────────────

async def chat(user_id: int, user_text: str, bot: Any, tenant: "TenantConfig") -> str:
    client = _get_client(tenant.effective_api_key)

    history = await repo.load_history(tenant.id, user_id)
    history.append({"role": "user", "content": user_text})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    from zoneinfo import ZoneInfo
    tenant_tz = ZoneInfo(tenant.timezone or "UTC")
    system_prompt = _build_system_prompt(tenant).replace(
        "{TODAY}", datetime.now(tenant_tz).strftime("%Y-%m-%d %A")
    )

    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=[{"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=history,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )

        assistant_content: list[dict] = []
        text_reply = ""
        tool_calls: list = []

        for block in response.content:
            if block.type == "text":
                text_reply = block.text
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_calls.append(block)
                assistant_content.append({"type": "tool_use", "id": block.id,
                                          "name": block.name, "input": block.input})

        history.append({"role": "assistant", "content": assistant_content})

        if not tool_calls:
            break

        tool_results: list[dict] = []
        for tc in tool_calls:
            try:
                result = await _exec_tool(tc.name, tc.input, tenant, owner_id=user_id)
            except Exception as exc:
                log.exception("Tool %s failed", tc.name)
                if "404" in str(exc) or "Not Found" in str(exc):
                    result = json.dumps({"error": "calendar_not_found",
                                         "hint": "Service account has no access to this calendar. Share the calendar with the service account email (Editor role)."})
                elif "403" in str(exc) or "disabled" in str(exc):
                    result = json.dumps({"error": "calendar_api_disabled",
                                         "hint": "Google Calendar API is not enabled in the project."})
                else:
                    result = json.dumps({"error": str(exc)})
            tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})
        history.append({"role": "user", "content": tool_results})
    else:
        text_reply = "Дай мне секунду, что-то пошло не так."

    await repo.save_history(tenant.id, user_id, history)
    return text_reply
