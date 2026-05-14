"""
AI service for Aria — personal receptionist assistant for the salon owner.

The owner talks to Aria in natural language to:
  - View today's / this week's / any date's schedule
  - Add bookings that came in via Instagram, WhatsApp, or phone
  - Reschedule or cancel appointments
  - Check slot availability

Google Calendar is used as the source of truth when credentials are configured;
otherwise the internal PostgreSQL store is used.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import anthropic

from aria.config import settings
import aria.db.repo as repo
from aria.services.booking import get_adapter, parse_datetime

log = logging.getLogger(__name__)

MAX_HISTORY = 40
MAX_TOOL_ROUNDS = 5


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return f"""You are Aria, the personal AI receptionist for {settings.OWNER_NAME} at {settings.SALON_NAME}.

Your job is to help {settings.OWNER_NAME} manage her appointment schedule. She is the salon owner — treat her as your boss.

WHAT YOU DO:
- Show the schedule for today, tomorrow, any specific date, or the coming week
- Add new bookings that clients arranged via Instagram, WhatsApp, phone, or booking service
- Reschedule and cancel appointments
- Check whether a specific slot is free
- Remind {settings.OWNER_NAME} of upcoming clients when asked

LANGUAGE RULE — CRITICAL:
Respond ALWAYS in the exact same language {settings.OWNER_NAME} uses in her message.
If she writes in Russian → respond in Russian.
If she writes in English → respond in English.
NEVER switch to a different language. NEVER default to English.

STYLE:
- Short and direct. She is busy.
- For schedules: use a clear bullet list with time and client name.
- Confirm every action immediately ("Готово — Катя записана на 16 мая в 14:00").
- If something is unclear, ask one short clarifying question.
- Never say "unfortunately", "I'm just an AI", or apologise unnecessarily.

SALON INFO:
Salon: {settings.SALON_NAME}
Services: {settings.SALON_SERVICES}
Working hours: {settings.SALON_HOURS}
Today (UTC): {{TODAY}}

TOOL USE:
Always call the appropriate tool to read or write real data. Never invent or guess schedule information."""


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "get_schedule",
        "description": (
            "Get the appointment schedule for a specific date or date range. "
            "Use date='today' or date='tomorrow' for convenience, or provide YYYY-MM-DD. "
            "For a range provide both date_from and date_to."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "YYYY-MM-DD, 'today', or 'tomorrow'",
                },
                "date_from": {
                    "type": "string",
                    "description": "YYYY-MM-DD — start of range (optional)",
                },
                "date_to": {
                    "type": "string",
                    "description": "YYYY-MM-DD — end of range (optional)",
                },
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
        "description": (
            "Add a new appointment. Use when the owner tells you a client booked "
            "via Instagram, WhatsApp, phone call, or any other channel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string"},
                "service": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
                "phone": {
                    "type": "string",
                    "description": "Client phone number (optional)",
                },
                "note": {
                    "type": "string",
                    "description": "Any extra notes (optional)",
                },
            },
            "required": ["client_name", "service", "date", "time"],
        },
    },
    {
        "name": "reschedule_booking",
        "description": "Move an existing booking to a new date and/or time.",
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
            "properties": {
                "booking_id": {"type": "integer"},
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "get_upcoming",
        "description": "Get the next N upcoming appointments (default 10).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "How many appointments to return (default 10)",
                },
            },
            "required": [],
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_date(value: str) -> str:
    """Convert 'today'/'tomorrow' to YYYY-MM-DD."""
    from datetime import date, timedelta
    if value.lower() == "today":
        return date.today().isoformat()
    if value.lower() == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    return value



# ── Tool executor ─────────────────────────────────────────────────────────────

async def _exec_tool(name: str, args: dict, owner_id: int) -> str:
    adapter = get_adapter()

    if name == "get_schedule":
        if args.get("date_from") and args.get("date_to"):
            date_from_str = _resolve_date(args["date_from"])
            date_to_str = _resolve_date(args["date_to"])
            dt_from = datetime.strptime(date_from_str, "%Y-%m-%d").replace(
                hour=0, minute=0, tzinfo=timezone.utc
            )
            dt_to = datetime.strptime(date_to_str, "%Y-%m-%d").replace(
                hour=23, minute=59, tzinfo=timezone.utc
            )
        else:
            target = _resolve_date(args.get("date") or "today")
            dt_from = datetime.strptime(target, "%Y-%m-%d").replace(
                hour=0, minute=0, tzinfo=timezone.utc
            )
            dt_to = dt_from.replace(hour=23, minute=59)

        events = await adapter.get_events(dt_from, dt_to)
        return json.dumps({
            "date_from": dt_from.strftime("%Y-%m-%d"),
            "date_to": dt_to.strftime("%Y-%m-%d"),
            "count": len(events),
            "bookings": events,
        })

    if name == "check_availability":
        dt = parse_datetime(args["date"], args["time"])
        if dt is None:
            return json.dumps({"error": "invalid date/time"})
        available = await adapter.is_available(dt, args["service"])
        return json.dumps({"available": available, "date": args["date"], "time": args["time"]})

    if name == "add_booking":
        dt = parse_datetime(args["date"], args["time"])
        if dt is None:
            return json.dumps({"error": "invalid date/time"})
        booking_id, cal_id = await adapter.create_event(
            owner_id, args["client_name"], args["service"], dt
        )
        return json.dumps({
            "booking_id": booking_id,
            "client": args["client_name"],
            "service": args["service"],
            "date": args["date"],
            "time": args["time"],
            "confirmed": True,
        })

    if name == "reschedule_booking":
        new_dt = parse_datetime(args["new_date"], args["new_time"])
        if new_dt is None:
            return json.dumps({"error": "invalid date/time"})
        booking = await repo.get_booking(args["booking_id"])
        if not booking:
            return json.dumps({"error": "booking not found"})
        await adapter.update_event(
            args["booking_id"], booking.get("calendar_event_id"), new_dt
        )
        return json.dumps({
            "rescheduled": True,
            "booking_id": args["booking_id"],
            "new_date": args["new_date"],
            "new_time": args["new_time"],
        })

    if name == "cancel_booking":
        booking = await repo.get_booking(args["booking_id"])
        if not booking:
            return json.dumps({"error": "booking not found"})
        await repo.update_booking_status(args["booking_id"], "cancelled")
        return json.dumps({"cancelled": True, "booking_id": args["booking_id"]})

    if name == "get_upcoming":
        limit = int(args.get("limit") or 10)
        from datetime import timedelta
        dt_from = datetime.now(timezone.utc)
        dt_to = dt_from + timedelta(days=90)
        events = await adapter.get_events(dt_from, dt_to)
        return json.dumps({"bookings": events[:limit]})

    return json.dumps({"error": f"unknown tool: {name}"})


# ── Anthropic client ──────────────────────────────────────────────────────────

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ── Main entry point ──────────────────────────────────────────────────────────

async def chat(user_id: int, user_text: str, bot: Any) -> str:
    client = _get_client()

    history = await repo.load_history(user_id)
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    system_prompt = _build_system_prompt().replace(
        "{TODAY}", datetime.now(timezone.utc).strftime("%Y-%m-%d %A")
    )

    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
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
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        history.append({"role": "assistant", "content": assistant_content})

        if not tool_calls:
            break

        tool_results: list[dict] = []
        for tc in tool_calls:
            try:
                result = await _exec_tool(tc.name, tc.input, owner_id=user_id)
            except Exception as exc:
                log.exception("Tool %s failed", tc.name)
                result = json.dumps({"error": str(exc)})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        history.append({"role": "user", "content": tool_results})

    else:
        text_reply = "Дай мне секунду, что-то пошло не так."

    await repo.save_history(user_id, history)
    return text_reply
