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

MAX_HISTORY     = 40
MAX_HISTORY_VIP = 100
MAX_TOOL_ROUNDS = 5

_clients: dict[str, anthropic.AsyncAnthropic] = {}


def _get_client(api_key: str) -> anthropic.AsyncAnthropic:
    if api_key not in _clients:
        _clients[api_key] = anthropic.AsyncAnthropic(api_key=api_key)
    return _clients[api_key]


# ── System prompt ─────────────────────────────────────────────────────────────

_STYLE_LINES = {
    "formal": "Стиль: официально, уважительно, на Вы.",
    "terse":  "Стиль: предельно кратко — только суть, без лишних слов.",
    "casual": "Стиль: тепло, дружелюбно, на ты.",
}


def _build_system_prompt(
    tenant: "TenantConfig",
    style: str = "casual",
    vip_context: Optional[dict] = None,
) -> str:
    from aria.config import settings
    has_creds = bool(tenant.google_cal_credentials or settings.GOOGLE_CALENDAR_CREDENTIALS)
    if has_creds and tenant.google_cal_id and tenant.is_vip_active:
        calendar_line = f"Календарь: Google Calendar (ID: {tenant.google_cal_id}) — синхронизирован"
    else:
        calendar_line = "Календарь: локальное хранение (Google Calendar не подключён)"

    style_line = _STYLE_LINES.get(style, _STYLE_LINES["casual"])

    base = f"""Ты — Aria, персональный AI-администратор {tenant.owner_name} в {tenant.salon_name}.

РОЛЬ:
Помогаешь {tenant.owner_name} управлять записями клиентов. Она твой руководитель.

ЧТО УМЕЕШЬ:
— Показывать расписание на любую дату или диапазон
— Вносить записи (клиенты пишут в Instagram, WhatsApp, звонят — ты фиксируешь)
— Переносить и отменять записи
— Проверять свободные слоты

{style_line}

КАК ОТВЕЧАЕШЬ:
— Коротко и по делу — она занята
— Расписание: маркированный список, время и имя клиента
— Каждое действие подтверждаешь: «Готово — Катя записана на 16 мая в 14:00»
— Если непонятно — один уточняющий вопрос, не больше
— Не начинай с «Конечно!», «Отлично!», «Как я могу помочь?»

ЗАПИСЬ КЛИЕНТА (строго обязательно):
— Из первого сообщения сразу извлеки всё доступное: имя клиента, услугу, дату, время
— Имя клиента часто стоит в начале: «Запиши Вику…» → client_name = «Вика»
— Уточняй только то, чего реально не хватает для add_booking — по одному вопросу
— Как только все 4 поля известны — немедленно вызывай add_booking, не переспрашивай
— Если клиент назван местоимением («её», «его», «её») — ищи имя в предыдущих сообщениях диалога

ПРАВИЛА ИНСТРУМЕНТОВ (строго обязательны):
— Если инструмент вернул поле "error" — это означает ПРОВАЛ. Запись НЕ создана. Сообщи об ошибке.
— НИКОГДА не говори «запись создана» или «готово», если в ответе инструмента есть "error".
— НИКОГДА не говори что запись в Google Calendar если в ответе инструмента нет "google_calendar": true.
— Если "error": "calendar_not_found" — скажи поделиться календарём с сервисным аккаунтом и дать права «Вносить изменения».
— Если "error": "calendar_api_disabled" — скажи включить Google Calendar API в Google Cloud Console.
— Если "google_calendar": false — запись сохранена ТОЛЬКО в боте, без Google Calendar (так и скажи).

ЯЗЫК:
Отвечай ВСЕГДА на том же языке, на котором пишет {tenant.owner_name}.
Русский → русский. Английский → английский.

ДАННЫЕ САЛОНА:
Салон: {tenant.salon_name}
Услуги: {tenant.services}
Часы работы: {tenant.hours}
{calendar_line}
Часовой пояс: {tenant.timezone}
Сегодня: {{TODAY}}"""

    if vip_context:
        sections: list[str] = []

        services = vip_context.get("services", [])
        if services:
            lines = []
            current_cat = None
            for s in services:
                if s["category"] != current_cat:
                    current_cat = s["category"]
                    lines.append(f"\n{current_cat}:")
                price_str = f"{int(s['price'])}₽" if s.get("price") else ""
                dur_str = f"{s['duration_minutes']} мин" if s.get("duration_minutes") else ""
                meta = ", ".join(filter(None, [price_str, dur_str]))
                lines.append(f"  — {s['name']}" + (f" ({meta})" if meta else ""))
            sections.append("КАТАЛОГ УСЛУГ:" + "".join(lines))

        notes = vip_context.get("client_notes", [])
        if notes:
            note_lines = "\n".join(f"  — {n}" for n in notes)
            sections.append(f"ЗАМЕТКИ О КЛИЕНТАХ:\n{note_lines}")

        if sections:
            vip_block = "\n\nVIP КОНТЕКСТ:\n" + "\n\n".join(sections)
            vip_block += (
                "\n\nДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ (VIP):\n"
                "— Знай постоянных клиентов по именам и предпочтениям\n"
                "— При записи учитывай историю и предпочтения конкретного клиента\n"
                "— Предлагай подходящие услуги исходя из каталога и заметок\n"
                "— Если клиент упоминался в заметках — используй эти знания"
            )
            base += vip_block

    return base


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


def _trim_history(history: list[dict], max_len: int) -> list[dict]:
    """Trim history to max_len, always starting at a clean user-text message.

    Never cuts between a tool_use assistant turn and its tool_result user turn,
    which would cause an Anthropic API validation error.
    """
    if len(history) <= max_len:
        return history
    trimmed = history[-max_len:]
    # Walk forward until we find a user message that is plain text (not tool_result)
    for i, msg in enumerate(trimmed):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return trimmed[i:]
        if isinstance(content, list) and all(
            b.get("type") != "tool_result" for b in content
        ):
            return trimmed[i:]
    # Fallback: keep only the very last user message
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "user":
            content = history[i].get("content", "")
            if isinstance(content, str):
                return [history[i]]
    return []


# ── Tool executor ─────────────────────────────────────────────────────────────

async def _exec_tool(
    name: str, args: dict, tenant: "TenantConfig", owner_id: int, bot: Any
) -> str:
    adapter = get_adapter(tenant)
    tz_str  = tenant.timezone or "UTC"

    if name == "get_schedule":
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_str)
        if args.get("date_from") and args.get("date_to"):
            from_str = _resolve_date(args["date_from"], tz_str)
            to_str   = _resolve_date(args["date_to"],   tz_str)
            dt_from  = datetime.strptime(from_str, "%Y-%m-%d").replace(hour=0,  minute=0,  tzinfo=tz).astimezone(timezone.utc)
            dt_to    = datetime.strptime(to_str,   "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=tz).astimezone(timezone.utc)
        else:
            target  = _resolve_date(args.get("date") or "today", tz_str)
            dt_from = datetime.strptime(target, "%Y-%m-%d").replace(hour=0,  minute=0,  tzinfo=tz).astimezone(timezone.utc)
            dt_to   = datetime.strptime(target, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=tz).astimezone(timezone.utc)
        events = await adapter.get_events(dt_from, dt_to)
        return json.dumps({
            "date_from": _resolve_date(args.get("date_from") or args.get("date") or "today", tz_str),
            "date_to":   _resolve_date(args.get("date_to")   or args.get("date") or "today", tz_str),
            "count": len(events), "bookings": events,
        })

    if name == "check_availability":
        dt = parse_datetime(args["date"], args["time"], tz_str)
        if dt is None:
            return json.dumps({"error": "invalid date/time"})
        return json.dumps({
            "available": await adapter.is_available(dt, args["service"]),
            "date": args["date"], "time": args["time"],
        })

    if name == "add_booking":
        dt = parse_datetime(args["date"], args["time"], tz_str)
        if dt is None:
            return json.dumps({"error": "invalid_datetime",
                               "message": "Could not parse date/time. Ask user to confirm the date and time."})
        try:
            bid, cal_id = await adapter.create_event(
                owner_id, args["client_name"], args["service"], dt
            )
        except Exception as exc:
            log.exception("add_booking: create_event failed")
            return json.dumps({"error": "booking_not_created",
                               "message": f"Failed to save booking: {exc}"})
        # Schedule reminder (day before at 09:00 local) and no-show check (2h after)
        from aria.services.scheduler import schedule_reminder_job, schedule_noshow_job
        schedule_reminder_job(bid, dt, owner_id, bot, tenant)
        schedule_noshow_job(bid, dt, owner_id, bot, tenant)
        gcal_ok = cal_id is not None
        return json.dumps({
            "booking_id": bid, "client": args["client_name"],
            "service": args["service"], "date": args["date"],
            "time": args["time"], "confirmed": True,
            "google_calendar": gcal_ok,
            "storage": "google_calendar" if gcal_ok else "local_only",
        })

    if name == "reschedule_booking":
        new_dt = parse_datetime(args["new_date"], args["new_time"], tz_str)
        if new_dt is None:
            return json.dumps({"error": "invalid date/time"})
        booking = await repo.get_booking(args["booking_id"])
        if not booking:
            return json.dumps({"error": "booking not found"})
        await adapter.update_event(args["booking_id"], booking.get("calendar_event_id"), new_dt)
        # Reschedule reminder and no-show jobs with new time
        from aria.services.scheduler import schedule_reminder_job, schedule_noshow_job
        schedule_reminder_job(args["booking_id"], new_dt, owner_id, bot, tenant)
        schedule_noshow_job(args["booking_id"], new_dt, owner_id, bot, tenant)
        return json.dumps({
            "rescheduled": True, "booking_id": args["booking_id"],
            "new_date": args["new_date"], "new_time": args["new_time"],
        })

    if name == "cancel_booking":
        raw = args.get("booking_id", "")
        booking = None
        bid: Optional[int] = None
        try:
            bid = int(raw)
            booking = await repo.get_booking(bid)
        except (ValueError, TypeError):
            pass

        if booking:
            await repo.update_booking_status(bid, "cancelled")
            try:
                await adapter.delete_event(bid, booking.get("calendar_event_id"))
            except Exception as exc:
                log.warning("GCal delete skipped for booking %d: %s", bid, exc)
            from aria.services.scheduler import cancel_booking_jobs
            cancel_booking_jobs(bid)
            return json.dumps({"cancelled": True, "booking_id": bid})

        # booking_id is a GCal string event ID (not in DB)
        gcal_id = str(raw)
        try:
            await adapter.delete_event(None, gcal_id)
            return json.dumps({"cancelled": True, "gcal_event_id": gcal_id})
        except Exception as exc:
            log.warning("Direct GCal delete failed for %s: %s", gcal_id, exc)
            return json.dumps({"error": f"not found in DB and GCal delete failed: {exc}"})

    if name == "get_upcoming":
        limit = int(args.get("limit") or 10)
        events = await adapter.get_events(
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=90),
        )
        return json.dumps({"bookings": events[:limit]})

    return json.dumps({"error": f"unknown tool: {name}"})


# ── Main entry point ──────────────────────────────────────────────────────────

async def chat(
    user_id: int, user_text: str, bot: Any, tenant: "TenantConfig", style: str = "casual"
) -> str:
    client = _get_client(tenant.effective_api_key)

    is_vip = tenant.is_vip_active
    max_history = MAX_HISTORY_VIP if is_vip else MAX_HISTORY

    history = await repo.load_history(tenant.id, user_id)
    history.append({"role": "user", "content": user_text})
    history = _trim_history(history, max_history)

    vip_context: Optional[dict] = None
    if is_vip:
        try:
            vip_context = await repo.get_vip_context(tenant.id)
        except Exception:
            pass

    from zoneinfo import ZoneInfo
    tenant_tz = ZoneInfo(tenant.timezone or "UTC")
    system_prompt = _build_system_prompt(tenant, style=style, vip_context=vip_context).replace(
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
                result = await _exec_tool(tc.name, tc.input, tenant,
                                          owner_id=user_id, bot=bot)
            except Exception as exc:
                log.exception("Tool %s failed", tc.name)
                err_str = str(exc)
                if tc.name == "add_booking":
                    # Must be unambiguous: booking was NOT created
                    result = json.dumps({"error": "booking_not_created",
                                         "message": f"Booking failed: {err_str}"})
                elif "404" in err_str or "Not Found" in err_str or "could not find" in err_str.lower():
                    result = json.dumps({"error": "calendar_not_found",
                                         "hint": "Share the calendar with the service account (Editor role)."})
                elif "403" in err_str or "disabled" in err_str:
                    result = json.dumps({"error": "calendar_api_disabled",
                                         "hint": "Enable Google Calendar API in Google Cloud Console."})
                else:
                    result = json.dumps({"error": err_str})
            tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})
        history.append({"role": "user", "content": tool_results})
    else:
        text_reply = "Что-то пошло не так, попробуй ещё раз."

    await repo.save_history(tenant.id, user_id, history)
    return text_reply
