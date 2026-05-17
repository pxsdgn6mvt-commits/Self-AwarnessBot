"""
Quick-action handlers — reply keyboard shortcuts and guided booking wizard.

Reply keyboard (always visible):
  📅 Сегодня | 📅 Завтра | ➕ Новая запись | 📋 Ближайшие

Guided booking FSM:
  service → date → time → client name → confirm → creates booking
  All steps update a single wizard message in-place; user text messages are deleted.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import aria.db.repo as repo
from aria.filters import SetupDone
from aria.services.booking import get_adapter, parse_datetime
from aria.tenant import TenantConfig

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)
router = Router()

# last schedule/upcoming message per chat (deleted before sending new one)
_last_info_msg: dict[int, int] = {}  # chat_id → message_id


# ── Persistent reply keyboard ─────────────────────────────────────────────────

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Сегодня"),      KeyboardButton(text="📅 Завтра")],
        [KeyboardButton(text="➕ Новая запись"),  KeyboardButton(text="📋 Ближайшие")],
        [KeyboardButton(text="📊 Дашборд"),       KeyboardButton(text="⚙️ Настройки")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ── FSM ───────────────────────────────────────────────────────────────────────

class QuickBook(StatesGroup):
    category = State()
    service  = State()
    date     = State()
    time     = State()
    client   = State()


class QuickEdit(StatesGroup):
    note       = State()
    reschedule = State()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cats_kb(cats: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=c["name"], callback_data=f"qb_cat:{c['id']}")] for c in cats]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _items_for_booking_kb(items: list) -> InlineKeyboardMarkup:
    rows = []
    for it in items:
        label = it["name"]
        extras = []
        if it.get("price") is not None:
            extras.append(f"{int(it['price'])}€")
        if it.get("duration_minutes") is not None:
            extras.append(f"{it['duration_minutes']}мин")
        if extras:
            label += " · " + " · ".join(extras)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"qb_svc:{it['name']}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="qb_back_cats")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _date_kb(tenant: TenantConfig) -> InlineKeyboardMarkup:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    today = datetime.now(tz).date()
    rows = []
    for i in range(5):
        d = today + timedelta(days=i)
        label = {0: "Сегодня", 1: "Завтра"}.get(i, "") or ""
        label = f"{label} {d.strftime('%-d %b')}".strip()
        rows.append([InlineKeyboardButton(text=label, callback_data=f"qb_date:{d.isoformat()}")])
    rows.append([InlineKeyboardButton(text="📝 Другая дата", callback_data="qb_date:custom")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _time_kb(tenant: TenantConfig, date_str: str) -> InlineKeyboardMarkup:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    booked_dts = await repo.get_slots_on_date(tenant.id, date_str)
    booked = {dt.astimezone(tz).strftime("%H:%M") for dt in booked_dts}
    h, m = tenant.open_hour, 0
    buttons: list[InlineKeyboardButton] = []
    while h < tenant.close_hour:
        label = f"{h:02d}:{m:02d}"
        if label not in booked:
            buttons.append(InlineKeyboardButton(text=label, callback_data=f"qb_time:{label}"))
        total = h * 60 + m + tenant.slot_minutes
        h, m = divmod(total, 60)
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text="📝 Другое время", callback_data="qb_time:custom")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _schedule_text_and_kb(
    events: list[dict], date_label: str, date_str: str = ""
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not events:
        return f"📅 {date_label}\n\nЗаписей нет.", None

    lines = [f"📅 <b>{date_label}</b>\n"]
    sel_btns: list[InlineKeyboardButton] = []
    for e in events:
        bid = e.get("id")
        paid = e.get("paid", False)
        notes = e.get("notes")
        paid_mark = " ✅" if paid else ""
        line = f"• {e['time']} — {e['client']}, {e['service']}{paid_mark}"
        if notes:
            line += f"\n  📝 {notes}"
        lines.append(line)
        if isinstance(bid, int) and date_str:
            label = f"{e['time']} {e['client']}{paid_mark}"
            sel_btns.append(
                InlineKeyboardButton(text=label, callback_data=f"bk_card:{bid}|{date_str}")
            )

    rows = [sel_btns[i:i+2] for i in range(0, len(sel_btns), 2)]
    rows.append([InlineKeyboardButton(text="➕ Добавить запись", callback_data="qb_start")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _booking_card_text(booking: dict) -> str:
    paid  = booking.get("paid") or False
    notes = booking.get("notes")
    lines = [
        f"📌 <b>{booking['client_name']}</b>",
        f"Услуга: {booking['service']}",
    ]
    if paid:
        lines.append("💰 Оплачено ✅")
    if notes:
        lines.append(f"📝 {notes}")
    return "\n".join(lines)


def _booking_card_kb(booking_id: int, paid: bool, date_str: str) -> InlineKeyboardMarkup:
    pay_label = "✅ Оплачено" if paid else "💰 Оплата"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Перенести", callback_data=f"bk_reschedule:{booking_id}"),
            InlineKeyboardButton(text="❌ Отменить",  callback_data=f"del_booking:{booking_id}"),
        ],
        [
            InlineKeyboardButton(text=pay_label,      callback_data=f"bk_paid:{booking_id}"),
            InlineKeyboardButton(text="📝 Заметка",   callback_data=f"bk_note:{booking_id}"),
        ],
        [InlineKeyboardButton(text="◀️ К списку дня", callback_data=f"bk_list|{date_str}")],
    ])


async def _delete_old_info(bot: Bot, chat_id: int) -> None:
    old_id = _last_info_msg.pop(chat_id, None)
    if old_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except Exception:
            pass


# ── Schedule shortcuts ────────────────────────────────────────────────────────

async def _show_schedule(message: Message, tenant: TenantConfig, days_offset: int = 0) -> None:
    from zoneinfo import ZoneInfo
    tz_str = tenant.timezone or "UTC"
    tz = ZoneInfo(tz_str)
    target = (datetime.now(tz) + timedelta(days=days_offset)).date()
    dt_from = datetime(target.year, target.month, target.day, 0,  0,  tzinfo=tz).astimezone(timezone.utc)
    dt_to   = datetime(target.year, target.month, target.day, 23, 59, tzinfo=tz).astimezone(timezone.utc)

    adapter = get_adapter(tenant)
    events  = await adapter.get_events(dt_from, dt_to)

    labels = {0: "Сегодня", 1: "Завтра"}
    date_label = f"{labels.get(days_offset, '')} {target.strftime('%-d %B')}".strip()
    text, kb = _schedule_text_and_kb(events, date_label, target.isoformat())

    await _delete_old_info(message.bot, message.chat.id)
    sent = await message.answer(text, reply_markup=kb)
    _last_info_msg[message.chat.id] = sent.message_id


@router.message(F.text == "📅 Сегодня", SetupDone())
async def quick_today(message: Message, tenant: TenantConfig) -> None:
    await _show_schedule(message, tenant, 0)


@router.message(F.text == "📅 Завтра", SetupDone())
async def quick_tomorrow(message: Message, tenant: TenantConfig) -> None:
    await _show_schedule(message, tenant, 1)


@router.message(F.text == "📋 Ближайшие", SetupDone())
async def quick_upcoming(message: Message, tenant: TenantConfig) -> None:
    adapter = get_adapter(tenant)
    events  = await adapter.get_events(
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(days=30),
    )
    if not events:
        await _delete_old_info(message.bot, message.chat.id)
        sent = await message.answer("📋 Ближайших записей нет.")
        _last_info_msg[message.chat.id] = sent.message_id
        return

    lines = ["📋 <b>Ближайшие записи</b>\n"]
    cancel_btns: list[InlineKeyboardButton] = []
    for e in events[:15]:
        bid = e.get("id")
        lines.append(f"• {e['date']} {e['time']} — {e['client']}, {e['service']}")
        if isinstance(bid, int):
            cancel_btns.append(
                InlineKeyboardButton(
                    text=f"❌ {e['client']} {e['date']}",
                    callback_data=f"del_booking:{bid}",
                )
            )

    rows = [cancel_btns[i:i+2] for i in range(0, len(cancel_btns), 2)]
    rows.append([InlineKeyboardButton(text="➕ Добавить запись", callback_data="qb_start")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await _delete_old_info(message.bot, message.chat.id)
    sent = await message.answer("\n".join(lines), reply_markup=kb)
    _last_info_msg[message.chat.id] = sent.message_id


# ── Cancel booking via inline button ─────────────────────────────────────────

@router.callback_query(F.data.startswith("del_booking:"), SetupDone())
async def cb_cancel_booking(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    try:
        booking_id = int(callback.data.split(":")[1])
    except ValueError:
        await callback.answer("Запись не найдена в системе.", show_alert=True)
        return
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] == "cancelled":
        await callback.answer("Запись уже отменена или не найдена.", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    await repo.update_booking_status(booking_id, "cancelled")
    adapter = get_adapter(tenant)
    await adapter.delete_event(booking_id, booking.get("calendar_event_id"))

    from aria.services.scheduler import cancel_booking_jobs
    cancel_booking_jobs(booking_id)

    await callback.answer("✅ Запись отменена")
    # keep ◀️ К списку дня button if we're in card view
    back_btn = None
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("bk_list|"):
                    back_btn = btn
                    break
    new_kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn]]) if back_btn else None
    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n❌ <i>Запись #{booking_id} отменена</i>",
            reply_markup=new_kb,
        )
    except Exception:
        pass


# ── Dashboard helpers ─────────────────────────────────────────────────────────

_MON_RU   = ["января","февраля","марта","апреля","мая","июня",
              "июля","августа","сентября","октября","ноября","декабря"]
_DAY_SHORT = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
_DAY_FULL  = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]


def _income_block(tenant: TenantConfig, expected: float, received: float) -> list[str]:
    lines: list[str] = []
    if expected > 0:
        lines.append(f"💰 Ожидается: <b>{int(expected)}€</b>")
    if received > 0:
        lines.append(f"✅ Оплачено: <b>{int(received)}€</b>")
        if tenant.master_percent is not None:
            cut = received * tenant.master_percent / 100
            lines.append(f"   👤 Доля ({int(tenant.master_percent)}%): <b>{cut:.0f}€</b>")
            if tenant.tax_percent is not None:
                net = cut * (1 - tenant.tax_percent / 100)
                lines.append(f"   🧾 Чистыми ({int(tenant.tax_percent)}%): <b>{net:.0f}€</b>")
    return lines


def _dashboard_kb(active: str) -> InlineKeyboardMarkup:
    periods = [("day", "📅 День"), ("week", "📆 Неделя"), ("month", "🗓 Месяц")]
    btns = [
        InlineKeyboardButton(
            text=f"{lbl} ✓" if p == active else lbl,
            callback_data=f"dash:{p}",
        )
        for p, lbl in periods
    ]
    return InlineKeyboardMarkup(inline_keyboard=[btns])


async def _day_dashboard(tenant: TenantConfig) -> str:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    now_local = datetime.now(tz)
    date_str  = now_local.strftime("%Y-%m-%d")
    day_label = f"{_DAY_FULL[now_local.weekday()]}, {now_local.day} {_MON_RU[now_local.month - 1]}"

    stats          = await repo.get_today_stats(tenant.id, date_str)
    bookings_today = await repo.get_bookings_for_date(tenant.id, date_str)
    next_b = next((b for b in bookings_today if b["scheduled_at"].astimezone(tz) > now_local), None)

    booked_slots = {dt.astimezone(tz).strftime("%H:%M")
                    for dt in await repo.get_slots_on_date(tenant.id, date_str)}
    free_slots: list[str] = []
    h, m = tenant.open_hour, 0
    while h < tenant.close_hour:
        slot = f"{h:02d}:{m:02d}"
        if slot not in booked_slots:
            free_slots.append(slot)
        tot = h * 60 + m + tenant.slot_minutes
        h, m = divmod(tot, 60)

    lines = [f"📅 <b>{day_label}</b>\n"]
    lines.append(f"📋 Записей: <b>{stats['total']}</b>")

    if next_b:
        t_str = next_b["scheduled_at"].astimezone(tz).strftime("%H:%M")
        mins  = int((next_b["scheduled_at"].astimezone(tz) - now_local).total_seconds() / 60)
        if mins >= 60:
            h_d, m_d = divmod(mins, 60)
            diff = f"{h_d}ч {m_d}мин" if m_d else f"{h_d}ч"
        else:
            diff = f"{mins} мин"
        lines.append(f"⏰ Следующий: <b>{next_b['client_name']}</b> в {t_str} (через {diff})")
    else:
        lines.append("⏰ Записей до конца дня нет")

    lines += _income_block(tenant, float(stats["expected"]), float(stats["received"]))

    if free_slots:
        slots_str = "  ".join(free_slots[:6]) + (f" +{len(free_slots)-6}" if len(free_slots) > 6 else "")
        lines.append(f"\n🕐 Свободно: {slots_str}")
    else:
        lines.append("\n🔴 Свободных окон нет")

    return "\n".join(lines)


async def _week_dashboard(tenant: TenantConfig) -> str:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    now_local = datetime.now(tz)
    monday    = now_local.date() - timedelta(days=now_local.weekday())
    sunday    = monday + timedelta(days=6)
    dt_from   = datetime(monday.year, monday.month, monday.day,  0,  0, tzinfo=tz).astimezone(timezone.utc)
    dt_to     = datetime(sunday.year, sunday.month, sunday.day, 23, 59, tzinfo=tz).astimezone(timezone.utc)

    stats  = await repo.get_period_stats(tenant.id, dt_from, dt_to)
    events = await get_adapter(tenant).get_events(dt_from, dt_to)
    by_day: dict[str, int] = {}
    for e in events:
        d = e.get("date", "")
        by_day[d] = by_day.get(d, 0) + 1

    date_range = f"{monday.day}–{sunday.day} {_MON_RU[monday.month - 1]}"
    lines = [f"📆 <b>Неделя — {date_range}</b>\n"]
    lines.append(f"📋 Записей: <b>{stats['total']}</b>")
    lines += _income_block(tenant, float(stats["expected"]), float(stats["received"]))

    day_parts = [f"{_DAY_SHORT[i]} {by_day.get((monday + timedelta(days=i)).isoformat(), 0)}"
                 for i in range(7)]
    lines.append("\n" + "  ·  ".join(day_parts))
    return "\n".join(lines)


async def _month_dashboard(tenant: TenantConfig) -> str:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    now_local  = datetime.now(tz)
    first      = now_local.date().replace(day=1)
    if first.month == 12:
        last = first.replace(year=first.year + 1, month=1) - timedelta(days=1)
    else:
        last = first.replace(month=first.month + 1) - timedelta(days=1)
    dt_from = datetime(first.year, first.month, first.day,  0,  0, tzinfo=tz).astimezone(timezone.utc)
    dt_to   = datetime(last.year,  last.month,  last.day,  23, 59, tzinfo=tz).astimezone(timezone.utc)

    stats = await repo.get_period_stats(tenant.id, dt_from, dt_to)
    total  = int(stats["total"])
    weeks  = round(last.day / 7, 1)

    _MON_FULL = ["Январь","Февраль","Март","Апрель","Май","Июнь",
                 "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
    lines = [f"🗓 <b>{_MON_FULL[now_local.month - 1]} {now_local.year}</b>\n"]
    lines.append(f"📋 Записей: <b>{total}</b>")
    if total > 0 and weeks > 0:
        lines.append(f"   ≈ {round(total / weeks)} в неделю")
    lines += _income_block(tenant, float(stats["expected"]), float(stats["received"]))
    return "\n".join(lines)


async def _build_dashboard(tenant: TenantConfig, period: str) -> str:
    if period == "week":
        return await _week_dashboard(tenant)
    if period == "month":
        return await _month_dashboard(tenant)
    return await _day_dashboard(tenant)


# ── Dashboard handlers ────────────────────────────────────────────────────────

@router.message(F.text == "📊 Дашборд", SetupDone())
async def quick_dashboard(message: Message, tenant: TenantConfig) -> None:
    text = await _build_dashboard(tenant, "day")
    await _delete_old_info(message.bot, message.chat.id)
    sent = await message.answer(text, reply_markup=_dashboard_kb("day"), parse_mode="HTML")
    _last_info_msg[message.chat.id] = sent.message_id


@router.callback_query(F.data.startswith("dash:"), SetupDone())
async def cb_dashboard_period(callback: CallbackQuery, tenant: TenantConfig) -> None:
    period = callback.data[len("dash:"):]
    if period not in ("day", "week", "month"):
        await callback.answer()
        return
    text = await _build_dashboard(tenant, period)
    await callback.message.edit_text(text, reply_markup=_dashboard_kb(period), parse_mode="HTML")
    await callback.answer()


# ── Booking card (Variant C: tap booking → card → back to list) ──────────────

@router.callback_query(F.data.startswith("bk_card:"), SetupDone())
async def cb_booking_card(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rest = callback.data[len("bk_card:"):]
    bid_str, date_str = rest.split("|", 1)
    booking = await repo.get_booking(int(bid_str))
    if not booking or booking["status"] == "cancelled":
        await callback.answer("Запись не найдена или уже отменена.", show_alert=True)
        return
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    dt_local = booking["scheduled_at"].astimezone(tz)
    paid = booking.get("paid") or False
    notes = booking.get("notes")
    lines = [
        f"📌 <b>{dt_local.strftime('%H:%M')} — {booking['client_name']}</b>",
        f"Услуга: {booking['service']}",
    ]
    if paid:
        lines.append("💰 Оплачено ✅")
    if notes:
        lines.append(f"📝 {notes}")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_booking_card_kb(booking["id"], paid, date_str),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bk_list|"), SetupDone())
async def cb_back_to_list(callback: CallbackQuery, tenant: TenantConfig) -> None:
    from zoneinfo import ZoneInfo
    from datetime import date as _d
    date_str = callback.data[len("bk_list|"):]
    tz = ZoneInfo(tenant.timezone or "UTC")
    target  = _d.fromisoformat(date_str)
    dt_from = datetime(target.year, target.month, target.day,  0,  0, tzinfo=tz).astimezone(timezone.utc)
    dt_to   = datetime(target.year, target.month, target.day, 23, 59, tzinfo=tz).astimezone(timezone.utc)
    events  = await get_adapter(tenant).get_events(dt_from, dt_to)
    today = datetime.now(tz).date()
    diff  = (target - today).days
    _MON = ["января","февраля","марта","апреля","мая","июня",
            "июля","августа","сентября","октября","ноября","декабря"]
    prefix = {0: "Сегодня", 1: "Завтра"}.get(diff) or \
             ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"][target.weekday()]
    date_label = f"{prefix} {target.day} {_MON[target.month - 1]}"
    text, kb = _schedule_text_and_kb(events, date_label, date_str)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Quick actions: paid / note / reschedule ───────────────────────────────────

@router.callback_query(F.data.startswith("bk_paid:"), SetupDone())
async def cb_booking_paid(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    booking = await repo.get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    new_paid = not (booking.get("paid") or False)
    await repo.set_booking_paid(booking_id, new_paid)
    await callback.answer("✅ Оплачено" if new_paid else "↩️ Оплата отменена")
    # find date_str from ◀️ back button and refresh card
    date_str = ""
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("bk_list|"):
                    date_str = btn.callback_data[len("bk_list|"):]
    booking = await repo.get_booking(booking_id)
    try:
        await callback.message.edit_text(
            _booking_card_text(dict(booking)),
            reply_markup=_booking_card_kb(booking_id, new_paid, date_str),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("bk_note:"), SetupDone())
async def cb_booking_note_prompt(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    await state.set_state(QuickEdit.note)
    await state.update_data(booking_id=booking_id, msg_id=callback.message.message_id)
    await callback.answer()
    await callback.message.answer(
        "📝 Введи заметку для этой записи\n(или /skip чтобы отменить):"
    )


@router.message(QuickEdit.note, Command("skip"))
async def cb_note_skip(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


@router.message(QuickEdit.note, F.text.func(lambda x: not x.startswith("/")))
async def cb_note_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await repo.set_booking_note(data["booking_id"], message.text.strip())
    await state.clear()
    await message.answer("📝 Заметка сохранена.")


@router.callback_query(F.data.startswith("bk_reschedule:"), SetupDone())
async def cb_booking_reschedule_prompt(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    await state.set_state(QuickEdit.reschedule)
    await state.update_data(booking_id=booking_id, tenant_id=tenant.id)
    await callback.answer()
    await callback.message.answer(
        "✏️ Введи новую дату и время записи\n"
        "Например: <code>20 мая 14:00</code>\n"
        "Или /skip чтобы отменить.",
        parse_mode="HTML",
    )


@router.message(QuickEdit.reschedule, Command("skip"))
async def cb_reschedule_skip(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


@router.message(QuickEdit.reschedule, F.text.func(lambda x: not x.startswith("/")))
async def cb_reschedule_save(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    booking_id = data["booking_id"]
    new_dt = parse_datetime(message.text.strip(), tenant)
    if new_dt is None:
        await message.answer(
            "Не удалось распознать дату. Попробуй ещё раз, например: <code>20 мая 14:00</code>\n"
            "Или /skip чтобы отменить.",
            parse_mode="HTML",
        )
        return
    await repo.update_booking_time(booking_id, new_dt)
    await state.clear()
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    formatted = new_dt.astimezone(tz).strftime("%-d %B %H:%M")
    await message.answer(f"✅ Запись #{booking_id} перенесена на {formatted}.")


# ── Guided booking wizard ─────────────────────────────────────────────────────

async def _start_booking(message_or_query, state: FSMContext, tenant: TenantConfig) -> None:
    cats = await repo.get_categories(tenant.id)
    if cats:
        await state.set_state(QuickBook.category)
        text = "➕ <b>Новая запись</b>\n\nВыбери категорию:"
        kb   = _cats_kb(cats)
    else:
        await state.set_state(QuickBook.service)
        text = "➕ <b>Новая запись</b>\n\nВыбери услугу:"
        names = [s.strip() for s in tenant.services.split(",") if s.strip()]
        rows  = [[InlineKeyboardButton(text=s, callback_data=f"qb_svc:{s}")] for s in names]
        rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="qb_cancel")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(message_or_query, Message):
        sent = await message_or_query.answer(text, reply_markup=kb)
    else:
        sent = await message_or_query.message.answer(text, reply_markup=kb)
        await message_or_query.answer()
    await state.update_data(wizard_msg_id=sent.message_id)


@router.message(F.text == "➕ Новая запись", SetupDone())
async def quick_new(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return
    await _start_booking(message, state, tenant)


@router.callback_query(F.data == "qb_start", SetupDone())
async def cb_qb_start(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_booking(callback, state, tenant)


@router.callback_query(F.data == "qb_cancel")
async def cb_qb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отменено.", reply_markup=None)
    await callback.answer()


# Step 0 — category chosen
@router.callback_query(QuickBook.category, F.data.startswith("qb_cat:"))
async def cb_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    cat_id = int(callback.data[len("qb_cat:"):])
    cats   = await repo.get_categories(tenant.id)
    cat    = next((c for c in cats if c["id"] == cat_id), None)
    cat_name = cat["name"] if cat else "?"
    items  = await repo.get_items(cat_id)
    await state.update_data(category=cat_name)
    await state.set_state(QuickBook.service)
    await callback.message.edit_text(
        f"➕ <b>Новая запись</b>\n"
        f"Категория: <b>{cat_name}</b>\n\n"
        f"Выбери услугу:",
        reply_markup=_items_for_booking_kb(items),
    )
    await callback.answer()


@router.callback_query(QuickBook.service, F.data == "qb_back_cats")
async def cb_back_to_cats(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    cats = await repo.get_categories(tenant.id)
    await state.set_state(QuickBook.category)
    await callback.message.edit_text(
        "➕ <b>Новая запись</b>\n\nВыбери категорию:",
        reply_markup=_cats_kb(cats),
    )
    await callback.answer()


# Step 1 — service chosen
@router.callback_query(QuickBook.service, F.data.startswith("qb_svc:"))
async def cb_service(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    service  = callback.data[len("qb_svc:"):]
    data     = await state.get_data()
    category = data.get("category", "")
    await state.update_data(service=service)
    await state.set_state(QuickBook.date)
    cat_line = f"Категория: <b>{category}</b>\n" if category else ""
    await callback.message.edit_text(
        f"➕ <b>Новая запись</b>\n"
        f"{cat_line}Услуга: <b>{service}</b>\n\n"
        f"Выбери дату:",
        reply_markup=_date_kb(tenant),
    )
    await callback.answer()


# Step 2 — date chosen
@router.callback_query(QuickBook.date, F.data.startswith("qb_date:"))
async def cb_date(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    value = callback.data[len("qb_date:"):]
    data  = await state.get_data()
    service = data.get("service", "")

    if value == "custom":
        await callback.message.edit_text(
            f"➕ <b>Новая запись</b>\n"
            f"Услуга: <b>{service}</b>\n\n"
            f"Введи дату (например <code>20.05</code> или <code>2026-05-20</code>):",
            reply_markup=None,
        )
        await callback.answer()
        return

    await state.update_data(date=value)
    await state.set_state(QuickBook.time)
    await callback.message.edit_text(
        f"➕ <b>Новая запись</b>\n"
        f"Услуга: <b>{service}</b>\n"
        f"Дата: <b>{value}</b>\n\n"
        f"Выбери время:",
        reply_markup=await _time_kb(tenant, value),
    )
    await callback.answer()


@router.message(QuickBook.date)
async def text_date(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    raw = message.text.strip()
    date_str: str | None = None
    for fmt in ("%d.%m", "%d.%m.%Y", "%Y-%m-%d", "%d/%m", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if fmt in ("%d.%m", "%d/%m"):
                parsed = parsed.replace(year=datetime.now().year)
            date_str = parsed.date().isoformat()
            break
        except ValueError:
            continue

    data = await state.get_data()
    service = data.get("service", "")
    wizard_msg_id = data.get("wizard_msg_id")

    if date_str is None:
        try:
            await message.delete()
        except Exception:
            pass
        if wizard_msg_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=wizard_msg_id,
                    text=(
                        f"➕ <b>Новая запись</b>\n"
                        f"Услуга: <b>{service}</b>\n\n"
                        f"Не понял дату. Попробуй <code>20.05</code>:"
                    ),
                )
                return
            except Exception:
                pass
        await message.answer("Не понял дату. Попробуй <code>20.05</code>:")
        return

    await state.update_data(date=date_str)
    await state.set_state(QuickBook.time)

    try:
        await message.delete()
    except Exception:
        pass

    time_kb = await _time_kb(tenant, date_str)
    if wizard_msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=wizard_msg_id,
                text=(
                    f"➕ <b>Новая запись</b>\n"
                    f"Услуга: <b>{service}</b>\n"
                    f"Дата: <b>{date_str}</b>\n\n"
                    f"Выбери время:"
                ),
                reply_markup=time_kb,
            )
            return
        except Exception:
            pass
    await message.answer(
        f"✅ Дата: <b>{date_str}</b>\n\nВыбери время:",
        reply_markup=time_kb,
    )


# Step 3 — time chosen
@router.callback_query(QuickBook.time, F.data.startswith("qb_time:"))
async def cb_time(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data[len("qb_time:"):]
    data  = await state.get_data()
    service  = data.get("service", "")
    date_str = data.get("date", "")

    if value == "custom":
        await callback.message.edit_text(
            f"➕ <b>Новая запись</b>\n"
            f"Услуга: <b>{service}</b>\n"
            f"Дата: <b>{date_str}</b>\n\n"
            f"Введи время (например <code>14:30</code>):",
            reply_markup=None,
        )
        await callback.answer()
        return

    await state.update_data(time=value)
    await state.set_state(QuickBook.client)
    await callback.message.edit_text(
        f"➕ <b>Новая запись</b>\n"
        f"Услуга: <b>{service}</b>\n"
        f"Дата: <b>{date_str}</b>\n"
        f"Время: <b>{value}</b>\n\n"
        f"Имя клиента:",
        reply_markup=None,
    )
    await callback.answer()


@router.message(QuickBook.time)
async def text_time(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    data = await state.get_data()
    service  = data.get("service", "")
    date_str = data.get("date", "")
    wizard_msg_id = data.get("wizard_msg_id")

    if ":" not in raw or len(raw) > 5:
        try:
            await message.delete()
        except Exception:
            pass
        if wizard_msg_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=wizard_msg_id,
                    text=(
                        f"➕ <b>Новая запись</b>\n"
                        f"Услуга: <b>{service}</b>\n"
                        f"Дата: <b>{date_str}</b>\n\n"
                        f"Формат <code>ЧЧ:ММ</code>, например <code>14:30</code>:"
                    ),
                )
                return
            except Exception:
                pass
        await message.answer("Формат <code>ЧЧ:ММ</code>, например <code>14:30</code>:")
        return

    await state.update_data(time=raw)
    await state.set_state(QuickBook.client)

    try:
        await message.delete()
    except Exception:
        pass

    if wizard_msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=wizard_msg_id,
                text=(
                    f"➕ <b>Новая запись</b>\n"
                    f"Услуга: <b>{service}</b>\n"
                    f"Дата: <b>{date_str}</b>\n"
                    f"Время: <b>{raw}</b>\n\n"
                    f"Имя клиента:"
                ),
            )
            return
        except Exception:
            pass
    await message.answer(f"✅ Время: <b>{raw}</b>\n\nИмя клиента:")


# Step 4 — client name → create booking
@router.message(QuickBook.client)
async def text_client(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    client_name = message.text.strip()
    data = await state.get_data()
    wizard_msg_id = data.get("wizard_msg_id")
    await state.clear()

    service  = data["service"]
    date_str = data["date"]
    time_str = data["time"]
    tz_str   = tenant.timezone or "UTC"

    dt = parse_datetime(date_str, time_str, tz_str)
    if dt is None:
        try:
            await message.delete()
        except Exception:
            pass
        result = "❌ Не удалось разобрать дату/время. Попробуй ещё раз."
    else:
        try:
            adapter = get_adapter(tenant)
            bid, cal_id = await adapter.create_event(
                message.from_user.id, client_name, service, dt
            )
            from aria.services.scheduler import schedule_reminder_job, schedule_noshow_job
            schedule_reminder_job(bid, dt, message.from_user.id, message.bot, tenant)
            schedule_noshow_job(bid, dt, message.from_user.id, message.bot, tenant)

            svc_info = await repo.get_service_info(tenant.id, service)
            svc_extras = []
            if svc_info and svc_info["price"] is not None:
                svc_extras.append(f"{int(svc_info['price'])}€")
            if svc_info and svc_info["duration_minutes"] is not None:
                svc_extras.append(f"{svc_info['duration_minutes']}мин")
            svc_line = service + (" · " + " · ".join(svc_extras) if svc_extras else "")

            gcal_note = " · Google Calendar 📅" if cal_id else ""
            result = (
                f"✅ <b>{client_name}</b> — <b>{svc_line}</b>\n"
                f"{date_str}, {time_str}{gcal_note}\n"
                f"Запись #{bid}"
            )
        except Exception as exc:
            log.exception("QuickBook create_event failed")
            result = f"❌ Ошибка: {exc}"

    try:
        await message.delete()
    except Exception:
        pass

    if wizard_msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=wizard_msg_id,
                text=result,
                reply_markup=None,
            )
            return
        except Exception:
            pass

    await message.answer(result, reply_markup=MAIN_KB)
