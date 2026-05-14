"""
AI service for Aria — Claude Haiku with prompt caching and tool use.

The agentic loop:
  1. Send user message + conversation history to Claude
  2. If Claude requests tool calls → execute them → feed results back
  3. Repeat until Claude returns a plain text response
  4. Save updated history and return the final text
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

MAX_HISTORY = 30   # messages to keep in conversation (older are trimmed)
MAX_TOOL_ROUNDS = 5  # prevent infinite agentic loops


# ── System prompt (cached) ────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    booking_link_line = (
        f"Booking link: {settings.BOOKING_LINK}" if settings.BOOKING_LINK else ""
    )
    return f"""# IDENTITY
You are Aria, the AI receptionist for {settings.SALON_NAME}. You are warm, \
precise, and quietly efficient — like a front desk manager at a luxury \
spa who never loses her composure. You represent the brand in every message.

# LANGUAGE
Detect the client's language automatically and respond in it.
Supported: English, Finnish, Russian, German, French, Spanish, \
Italian, Dutch, Swedish, Norwegian, Danish, Polish. If unsure, use English.

# CORE RESPONSIBILITIES
1. Booking: Collect client name, desired service, and preferred date/time. \
Confirm availability. If slot is taken, immediately offer exactly 2 alternatives \
— never just say "that's unavailable."
2. Reminders: After every confirmed booking, ask: "Shall I send you a reminder \
the day before?" If yes, confirm: "Done — I'll message you [date] at 9am."
3. Rescheduling: Accept changes gracefully. Confirm the new time, update \
the reminder automatically.
4. No-show recovery: If a client missed an appointment, message within 2 hours: \
"We missed you today, [name]. Life happens — want me to find you a new slot this week?"
5. Waitlist: If fully booked, offer the waitlist: "I'll add you to our priority \
list and message you the moment a slot opens."

# TONE RULES
- Never robotic. Never overly formal. Think: attentive, calm, professional.
- Use the client's name once per conversation — not in every message.
- Short sentences. No unnecessary filler. Every message has a clear next step.
- Never say: "I'm just an AI," "I cannot," "Unfortunately," or "Please be advised."

# ESCALATION
If a client has a complaint, a question you cannot answer, or seems upset — respond: \
"I want to make sure this is handled perfectly for you. I'm flagging this for \
{settings.OWNER_NAME} right now — you'll hear back within {settings.ESCALATION_HOURS} \
hours." Then call notify_owner immediately.

# UPSELL WINDOW
After confirming a booking, add ONE natural upsell: "By the way — a lot of clients \
pair [booked service] with [complementary service]. Want me to add 20 minutes for that?" \
Never push more than once.

# CONTEXT
Salon name: {settings.SALON_NAME}
Owner/manager name: {settings.OWNER_NAME}
Services offered: {settings.SALON_SERVICES}
Working hours: {settings.SALON_HOURS}
{booking_link_line}
Today's date (UTC): {{TODAY}}

# TOOL USE
Always use the provided tools to take real actions. Never describe taking \
an action without calling the corresponding tool."""


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "check_availability",
        "description": (
            "Check whether a specific date/time slot is available for booking. "
            "Returns {available: bool}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM (24-hour)"},
                "service": {"type": "string"},
            },
            "required": ["date", "time", "service"],
        },
    },
    {
        "name": "get_alternatives",
        "description": (
            "Get exactly 2 alternative available slots near the requested date/time. "
            "Always call this when a requested slot is unavailable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD (reference date)"},
                "time": {"type": "string", "description": "HH:MM (reference time)"},
                "service": {"type": "string"},
            },
            "required": ["date", "time", "service"],
        },
    },
    {
        "name": "create_booking",
        "description": "Confirm and persist a booking for the client.",
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
        "description": "Move an existing confirmed booking to a new date/time.",
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
        "name": "schedule_reminder",
        "description": (
            "Schedule a reminder message to be sent to the client at 9am "
            "the day before their appointment. Call this after the client says yes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "integer"},
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "add_to_waitlist",
        "description": "Add the client to the priority waitlist for a service.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string"},
                "service": {"type": "string"},
            },
            "required": ["client_name", "service"],
        },
    },
    {
        "name": "get_upcoming_booking",
        "description": "Retrieve the client's next confirmed appointment.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "notify_owner",
        "description": (
            "Send an urgent notification to the salon owner. "
            "Use for complaints, escalations, or anything requiring human attention."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "urgency": {
                    "type": "string",
                    "enum": ["normal", "urgent"],
                    "description": "Use 'urgent' for complaints and upset clients.",
                },
            },
            "required": ["message"],
        },
    },
]


# ── Tool executor ─────────────────────────────────────────────────────────────

class ToolContext:
    """Carries runtime state needed by tool handlers."""

    def __init__(self, user_id: int, bot: Any, owner_id: int) -> None:
        self.user_id = user_id
        self.bot = bot
        self.owner_id = owner_id
        # Filled in after create_booking so schedule_reminder knows the id
        self.last_booking_id: Optional[int] = None


async def _exec_tool(name: str, args: dict, ctx: ToolContext) -> str:
    adapter = get_adapter()

    if name == "check_availability":
        dt = parse_datetime(args["date"], args["time"])
        if dt is None:
            return json.dumps({"error": "invalid date/time format"})
        available = await adapter.is_available(dt, args["service"])
        return json.dumps({"available": available})

    if name == "get_alternatives":
        dt = parse_datetime(args["date"], args["time"])
        if dt is None:
            return json.dumps({"error": "invalid date/time format"})
        alts = await adapter.get_alternatives(dt, args["service"])
        return json.dumps({
            "alternatives": [
                {"date": a.strftime("%Y-%m-%d"), "time": a.strftime("%H:%M")}
                for a in alts
            ]
        })

    if name == "create_booking":
        dt = parse_datetime(args["date"], args["time"])
        if dt is None:
            return json.dumps({"error": "invalid date/time format"})
        booking_id, cal_id = await adapter.create_event(
            ctx.user_id, args["client_name"], args["service"], dt
        )
        ctx.last_booking_id = booking_id
        return json.dumps({
            "booking_id": booking_id,
            "confirmed_date": args["date"],
            "confirmed_time": args["time"],
            "service": args["service"],
        })

    if name == "reschedule_booking":
        new_dt = parse_datetime(args["new_date"], args["new_time"])
        if new_dt is None:
            return json.dumps({"error": "invalid date/time format"})
        booking = await repo.get_booking(args["booking_id"])
        if not booking:
            return json.dumps({"error": "booking not found"})
        await adapter.update_event(
            args["booking_id"], booking.get("calendar_event_id"), new_dt
        )
        return json.dumps({"rescheduled": True, "new_date": args["new_date"],
                           "new_time": args["new_time"]})

    if name == "schedule_reminder":
        booking_id = args.get("booking_id") or ctx.last_booking_id
        if booking_id is None:
            return json.dumps({"error": "no booking_id provided"})
        booking = await repo.get_booking(booking_id)
        if not booking:
            return json.dumps({"error": "booking not found"})
        from aria.services.scheduler import schedule_reminder_job
        schedule_reminder_job(booking_id, booking["scheduled_at"], ctx.user_id, ctx.bot)
        return json.dumps({"reminder_scheduled": True, "booking_id": booking_id})

    if name == "add_to_waitlist":
        wl_id = await repo.add_to_waitlist(
            ctx.user_id, args["client_name"], args["service"]
        )
        return json.dumps({"waitlist_id": wl_id, "added": True})

    if name == "get_upcoming_booking":
        booking = await repo.get_upcoming_booking(ctx.user_id)
        if not booking:
            return json.dumps({"booking": None})
        return json.dumps({
            "booking": {
                "id": booking["id"],
                "service": booking["service"],
                "date": booking["scheduled_at"].strftime("%Y-%m-%d"),
                "time": booking["scheduled_at"].strftime("%H:%M"),
                "client_name": booking["client_name"],
                "status": booking["status"],
            }
        })

    if name == "notify_owner":
        if ctx.owner_id:
            try:
                urgency = args.get("urgency", "normal")
                prefix = "URGENT — " if urgency == "urgent" else ""
                await ctx.bot.send_message(
                    chat_id=ctx.owner_id,
                    text=f"{prefix}Aria alert (user {ctx.user_id}):\n{args['message']}",
                )
            except Exception as exc:
                log.warning("Failed to notify owner: %s", exc)
        return json.dumps({"notified": True})

    return json.dumps({"error": f"unknown tool: {name}"})


# ── Main AI call ──────────────────────────────────────────────────────────────

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def chat(user_id: int, user_text: str, bot: Any) -> str:
    """
    Main entry point: send user_text through the agentic loop and return
    Aria's final reply as a string.
    """
    client = _get_client()
    ctx = ToolContext(user_id=user_id, bot=bot, owner_id=settings.OWNER_TELEGRAM_ID)

    # Load history
    history = await repo.load_history(user_id)
    history.append({"role": "user", "content": user_text})

    # Trim to last MAX_HISTORY messages
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    system_prompt = _build_system_prompt().replace(
        "{TODAY}", datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    # Agentic loop
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

        # Collect assistant content block(s)
        assistant_content: list[dict] = []
        text_reply = ""
        tool_calls: list[dict] = []

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
            # No more tool calls — we have the final answer
            break

        # Execute tools and collect results
        tool_results: list[dict] = []
        for tc in tool_calls:
            try:
                result = await _exec_tool(tc.name, tc.input, ctx)
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
        # Fallback if loop exhausted without a text reply
        text_reply = "Let me check on that and get back to you shortly."

    await repo.save_history(user_id, history)
    return text_reply
