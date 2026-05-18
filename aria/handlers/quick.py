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
from aiogram.filters import Command, StateFilter
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
from aria.i18n import (
    T, DAY_FULL, DAY_SHORT, MON_GENITIVE, MON_SHORT, MON_FULL,
    all_variants, fmt_date, fmt_time_label, t,
)
from aria.services.booking import get_adapter, parse_datetime
from aria.tenant import TenantConfig

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)
router = Router()

# last schedule/upcoming message per chat (deleted before sending new one)
_last_info_msg: dict[int, int] = {}  # chat_id → message_id


# ── Persistent reply keyboard ─────────────────────────────────────────────────

def get_main_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("btn_today", lang)),    KeyboardButton(text=t("btn_tomorrow", lang))],
            [KeyboardButton(text=t("btn_new", lang)),      KeyboardButton(text=t("btn_upcoming", lang))],
            [KeyboardButton(text=t("btn_dashboard", lang)),KeyboardButton(text=t("btn_settings", lang))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

MAIN_KB = get_main_kb("ru")

# All persistent reply-keyboard texts across all languages — FSM handlers
# exclude these so buttons are never swallowed as data input.
MAIN_KB_TEXTS: frozenset[str] = frozenset(
    all_variants("btn_today") | all_variants("btn_tomorrow") |
    all_variants("btn_new") | all_variants("btn_upcoming") |
    all_variants("btn_dashboard") | all_variants("btn_settings") |
    {"📱 Меню", "📱 Управление", "📋 Список ботов", "➕ Добавить бота", "📣 Рассылка"}
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

def _cats_kb(cats: list, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=c["name"], callback_data=f"qb_cat:{c['id']}")] for c in cats]
    rows.append([InlineKeyboardButton(text=t("btn_cancel_act", lang), callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _items_for_booking_kb(items: list, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for it in items:
        label = it["name"]
        extras = []
        if it.get("price") is not None:
            extras.append(f"{int(it['price'])}€")
        if it.get("duration_minutes") is not None:
            extras.append(f"{it['duration_minutes']}{t('min_lbl', lang)}")
        if extras:
            label += " · " + " · ".join(extras)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"qb_svc:{it['name']}")])
    rows.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="qb_back_cats")])
    rows.append([InlineKeyboardButton(text=t("btn_cancel_act", lang), callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _date_kb(tenant: TenantConfig) -> InlineKeyboardMarkup:
    from zoneinfo import ZoneInfo
    lang = tenant.owner_lang or "ru"
    tz = ZoneInfo(tenant.timezone or "UTC")
    today = datetime.now(tz).date()
    rows = []
    for i in range(5):
        d = today + timedelta(days=i)
        prefix = {0: t("lbl_today", lang), 1: t("lbl_tomorrow", lang)}.get(i, "")
        date_part = fmt_date(d.day, d.month - 1, lang)
        label = f"{prefix} {date_part}".strip() if prefix else date_part
        rows.append([InlineKeyboardButton(text=label, callback_data=f"qb_date:{d.isoformat()}")])
    rows.append([InlineKeyboardButton(text=t("other_date", lang), callback_data="qb_date:custom")])
    rows.append([InlineKeyboardButton(text=t("btn_cancel_act", lang), callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _time_kb(tenant: TenantConfig, date_str: str) -> InlineKeyboardMarkup:
    from zoneinfo import ZoneInfo
    lang = tenant.owner_lang or "ru"
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
    rows.append([InlineKeyboardButton(text=t("other_time", lang), callback_data="qb_time:custom")])
    rows.append([InlineKeyboardButton(text=t("btn_cancel_act", lang), callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _schedule_text_and_kb(
    events: list[dict], date_label: str, date_str: str = "", lang: str = "ru"
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not events:
        return f"📅 {date_label}\n\n{t('no_bookings', lang)}", None

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
    rows.append([InlineKeyboardButton(text=t("add_booking", lang), callback_data="qb_start")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _booking_card_text(booking: dict, lang: str = "ru") -> str:
    paid   = booking.get("paid") or False
    notes  = booking.get("notes")
    status = booking.get("status", "confirmed")
    lines  = [
        f"📌 <b>{booking['client_name']}</b>",
        f"{t('service_label', lang)}: {booking['service']}",
    ]
    if status == "completed":
        lines.append(t("arrived_mark", lang))
    elif status == "no_show":
        lines.append(t("noshow_mark", lang))
    if paid:
        lines.append(t("paid_mark", lang))
    if notes:
        lines.append(f"📝 {notes}")
    return "\n".join(lines)


def _booking_card_kb(booking_id: int, paid: bool, date_str: str, status: str = "confirmed", lang: str = "ru") -> InlineKeyboardMarkup:
    pay_label = t("btn_paid_done", lang) if paid else t("btn_pay", lang)
    rows = []
    if status not in ("completed", "no_show"):
        rows.append([
            InlineKeyboardButton(text=t("btn_arrived", lang),  callback_data=f"bk_arrived:{booking_id}"),
            InlineKeyboardButton(text=t("btn_noshow", lang),   callback_data=f"bk_noshow:{booking_id}"),
        ])
    rows.append([
        InlineKeyboardButton(text=t("btn_reschedule", lang),   callback_data=f"bk_reschedule:{booking_id}"),
        InlineKeyboardButton(text=t("btn_cancel_bk", lang),    callback_data=f"del_booking:{booking_id}"),
    ])
    rows.append([
        InlineKeyboardButton(text=pay_label,                   callback_data=f"bk_paid:{booking_id}"),
        InlineKeyboardButton(text=t("btn_note", lang),         callback_data=f"bk_note:{booking_id}"),
    ])
    rows.append([InlineKeyboardButton(text=t("btn_back_day", lang), callback_data=f"bk_list|{date_str}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    lang = tenant.owner_lang or "ru"
    tz_str = tenant.timezone or "UTC"
    tz = ZoneInfo(tz_str)
    target = (datetime.now(tz) + timedelta(days=days_offset)).date()
    dt_from = datetime(target.year, target.month, target.day, 0,  0,  tzinfo=tz).astimezone(timezone.utc)
    dt_to   = datetime(target.year, target.month, target.day, 23, 59, tzinfo=tz).astimezone(timezone.utc)

    adapter = get_adapter(tenant)
    events  = await adapter.get_events(dt_from, dt_to)

    prefix = {0: t("lbl_today", lang), 1: t("lbl_tomorrow", lang)}.get(days_offset, "")
    date_part = fmt_date(target.day, target.month - 1, lang)
    date_label = f"{prefix} {date_part}".strip() if prefix else date_part
    text, kb = _schedule_text_and_kb(events, date_label, target.isoformat(), lang)

    await _delete_old_info(message.bot, message.chat.id)
    sent = await message.answer(text, reply_markup=kb)
    _last_info_msg[message.chat.id] = sent.message_id


@router.message(F.text.in_(all_variants("btn_today")), SetupDone(), StateFilter("*"))
async def quick_today(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.clear()
    await _show_schedule(message, tenant, 0)


@router.message(F.text.in_(all_variants("btn_tomorrow")), SetupDone(), StateFilter("*"))
async def quick_tomorrow(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.clear()
    await _show_schedule(message, tenant, 1)


@router.message(F.text.in_(all_variants("btn_upcoming")), SetupDone(), StateFilter("*"))
async def quick_upcoming(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.clear()
    lang = tenant.owner_lang or "ru"
    adapter = get_adapter(tenant)
    events  = await adapter.get_events(
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(days=14),
    )
    if not events:
        await _delete_old_info(message.bot, message.chat.id)
        sent = await message.answer(f"📋 {t('no_upcoming', lang)}")
        _last_info_msg[message.chat.id] = sent.message_id
        return

    lines = [f"📋 <b>{t('upcoming_title', lang)}</b>\n"]
    sel_btns: list[InlineKeyboardButton] = []
    prev_date = ""
    for e in events[:20]:
        bid       = e.get("id")
        date_str  = e.get("date", "")
        paid_mark = " ✅" if e.get("paid") else ""

        if date_str != prev_date:
            from datetime import date as _d
            try:
                d = _d.fromisoformat(date_str)
                day_hdr = f"{DAY_SHORT[lang][d.weekday()]} {fmt_date(d.day, d.month - 1, lang)}"
            except ValueError:
                day_hdr = date_str
            lines.append(f"\n📅 <b>{day_hdr}</b>")
            prev_date = date_str

        lines.append(f"• {e['time']} — {e['client']}, {e['service']}{paid_mark}")

        if isinstance(bid, int) and date_str:
            label = f"{e['time']} {e['client']}{paid_mark}"
            sel_btns.append(
                InlineKeyboardButton(text=label, callback_data=f"bk_card:{bid}|{date_str}")
            )

    rows = [sel_btns[i:i+2] for i in range(0, len(sel_btns), 2)]
    rows.append([InlineKeyboardButton(text=t("add_booking", lang), callback_data="qb_start")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await _delete_old_info(message.bot, message.chat.id)
    sent = await message.answer("\n".join(lines), reply_markup=kb, parse_mode="HTML")
    _last_info_msg[message.chat.id] = sent.message_id


# ── Cancel booking via inline button ─────────────────────────────────────────

@router.callback_query(F.data.startswith("del_booking:"), SetupDone())
async def cb_cancel_booking(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", lang), show_alert=True)
        return

    try:
        booking_id = int(callback.data.split(":")[1])
    except ValueError:
        await callback.answer(t("not_found_system", lang), show_alert=True)
        return
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] == "cancelled":
        await callback.answer(t("already_cancelled", lang), show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    await repo.update_booking_status(booking_id, "cancelled")
    adapter = get_adapter(tenant)
    await adapter.delete_event(booking_id, booking.get("calendar_event_id"))

    from aria.services.scheduler import cancel_booking_jobs
    cancel_booking_jobs(booking_id)

    await callback.answer(t("toast_cancelled", lang))
    back_btn = None
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("bk_list|"):
                    back_btn = btn
                    break
    new_kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn]]) if back_btn else None
    cancelled_line = {"ru": f"❌ <i>Запись #{booking_id} отменена</i>", "en": f"❌ <i>Booking #{booking_id} cancelled</i>", "fi": f"❌ <i>Varaus #{booking_id} peruutettu</i>"}.get(lang, f"❌ <i>#{booking_id}</i>")
    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n{cancelled_line}",
            reply_markup=new_kb,
        )
    except Exception:
        pass


# ── Dashboard helpers ─────────────────────────────────────────────────────────

def _income_block(
    tenant: TenantConfig, expected: float, received: float, paid_count: int = 0
) -> list[str]:
    lang = tenant.owner_lang or "ru"
    lines: list[str] = []
    if expected > 0:
        lines.append(f"{t('income_expected', lang)}: <b>{int(expected)}€</b>")
    if received > 0:
        lines.append(f"{t('income_paid', lang)}: <b>{int(received)}€</b>")
        if paid_count > 1:
            lines.append(f"   {t('avg_check', lang)}: <b>{received / paid_count:.0f}€</b>")
        if tenant.master_percent is not None:
            cut = received * tenant.master_percent / 100
            lines.append(f"   {t('master_share', lang)} ({int(tenant.master_percent)}%): <b>{cut:.0f}€</b>")
            if tenant.tax_percent is not None:
                net = cut * (1 - tenant.tax_percent / 100)
                lines.append(f"   {t('net_income', lang)} ({int(tenant.tax_percent)}%): <b>{net:.0f}€</b>")
    return lines


def _dashboard_kb(active: str, lang: str = "ru") -> InlineKeyboardMarkup:
    periods = [("day", t("dash_day", lang)), ("week", t("dash_week", lang)), ("month", t("dash_month", lang))]
    btns = [
        InlineKeyboardButton(
            text=f"{lbl} ✓" if p == active else lbl,
            callback_data=f"dash:{p}",
        )
        for p, lbl in periods
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        btns,
        [InlineKeyboardButton(text=t("dash_analytics", lang), callback_data="dash:analytics")],
    ])


async def _day_dashboard(tenant: TenantConfig) -> str:
    from zoneinfo import ZoneInfo
    lang = tenant.owner_lang or "ru"
    tz = ZoneInfo(tenant.timezone or "UTC")
    now_local = datetime.now(tz)
    date_str  = now_local.strftime("%Y-%m-%d")
    day_label = f"{DAY_FULL[lang][now_local.weekday()]}, {fmt_date(now_local.day, now_local.month - 1, lang)}"

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

    h_u = t("in_h", lang)
    m_u = t("in_min", lang)
    lines = [f"📅 <b>{day_label}</b>\n"]
    lines.append(f"{t('bookings_count', lang)}: <b>{stats['total']}</b>")

    if next_b:
        t_str = next_b["scheduled_at"].astimezone(tz).strftime("%H:%M")
        mins  = int((next_b["scheduled_at"].astimezone(tz) - now_local).total_seconds() / 60)
        if mins >= 60:
            h_d, m_d = divmod(mins, 60)
            diff = f"{h_d}{h_u} {m_d}{m_u}" if m_d else f"{h_d}{h_u}"
        else:
            diff = f"{mins} {m_u}"
        at_word = {"ru": "в", "en": "at", "fi": "klo"}.get(lang, "at")
        in_word = {"ru": f"через {diff}", "en": f"in {diff}", "fi": f"{diff} päästä"}.get(lang, f"in {diff}")
        lines.append(f"{t('next_client', lang)}: <b>{next_b['client_name']}</b> {at_word} {t_str} ({in_word})")
    else:
        lines.append(t("no_more_today", lang))

    lines += _income_block(tenant, float(stats["expected"]), float(stats["received"]), int(stats["paid_count"]))

    if free_slots:
        slots_str = "  ".join(free_slots[:6]) + (f" +{len(free_slots)-6}" if len(free_slots) > 6 else "")
        lines.append(f"\n{t('free_slots_lbl', lang)}: {slots_str}")
    else:
        lines.append(f"\n{t('no_free_slots', lang)}")

    return "\n".join(lines)


async def _week_dashboard(tenant: TenantConfig) -> str:
    from zoneinfo import ZoneInfo
    lang = tenant.owner_lang or "ru"
    tz = ZoneInfo(tenant.timezone or "UTC")
    now_local = datetime.now(tz)
    monday    = now_local.date() - timedelta(days=now_local.weekday())
    sunday    = monday + timedelta(days=6)
    dt_from   = datetime(monday.year, monday.month, monday.day,  0,  0, tzinfo=tz).astimezone(timezone.utc)
    dt_to     = datetime(sunday.year, sunday.month, sunday.day, 23, 59, tzinfo=tz).astimezone(timezone.utc)

    stats  = await repo.get_period_stats(tenant.id, dt_from, dt_to)
    by_day: dict[str, int] = {}
    try:
        events = await get_adapter(tenant).get_events(dt_from, dt_to)
        for e in events:
            d = e.get("date", "")
            by_day[d] = by_day.get(d, 0) + 1
    except Exception:
        log.exception("_week_dashboard: get_events failed for tenant %d", tenant.id)

    date_range = f"{monday.day}–{sunday.day} {MON_GENITIVE[lang][monday.month - 1]}"
    lines = [f"📆 <b>{t('dash_week', lang)} — {date_range}</b>\n"]
    lines.append(f"{t('bookings_count', lang)}: <b>{stats['total']}</b>")
    lines += _income_block(tenant, float(stats["expected"]), float(stats["received"]), int(stats["paid_count"]))

    day_parts = [f"{DAY_SHORT[lang][i]} {by_day.get((monday + timedelta(days=i)).isoformat(), 0)}"
                 for i in range(7)]
    lines.append("\n" + "  ·  ".join(day_parts))
    return "\n".join(lines)


async def _month_dashboard(tenant: TenantConfig) -> str:
    from zoneinfo import ZoneInfo
    lang = tenant.owner_lang or "ru"
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

    lines = [f"🗓 <b>{MON_FULL[lang][now_local.month - 1]} {now_local.year}</b>\n"]
    lines.append(f"{t('bookings_count', lang)}: <b>{total}</b>")
    if total > 0 and weeks > 0:
        lines.append(f"   ≈ {round(total / weeks)} {t('per_week', lang)}")
    lines += _income_block(tenant, float(stats["expected"]), float(stats["received"]), int(stats["paid_count"]))
    return "\n".join(lines)


async def _build_dashboard(tenant: TenantConfig, period: str) -> str:
    if period == "week":
        return await _week_dashboard(tenant)
    if period == "month":
        return await _month_dashboard(tenant)
    return await _day_dashboard(tenant)


async def _analytics_text(tenant: TenantConfig) -> str:
    from zoneinfo import ZoneInfo
    lang = tenant.owner_lang or "ru"
    now = datetime.now(ZoneInfo(tenant.timezone or "UTC"))
    lines = [f"📊 <b>{t('dash_analytics', lang)} — {MON_FULL[lang][now.month - 1]} {now.year}</b>\n"]

    services = await repo.get_service_stats(tenant.id, limit=5)
    if services:
        lines.append(f"<b>{t('top_services', lang)}</b>")
        for i, s in enumerate(services, 1):
            rev = int(s["revenue"])
            rev_str = f" · {rev}€" if rev > 0 else ""
            lines.append(f"{i}. {s['service']} — {s['visits']} {t('visits_short', lang)}{rev_str}")
    else:
        lines.append(t("no_data_svc", lang))

    lines.append("")

    clients = await repo.get_client_stats(tenant.id, limit=5)
    if clients:
        lines.append(f"<b>{t('top_clients', lang)}</b>")
        for i, c in enumerate(clients, 1):
            spent = int(c["total_spent"])
            spent_str = f" · {spent}€" if spent > 0 else ""
            status = repo.client_status_emoji(int(c["visits"]), int(c["no_show_count"]), int(c["cancelled_count"]))
            lines.append(f"{i}. {status} {c['client_name']} — {c['visits']} {t('visits_short', lang)}{spent_str}")
    else:
        lines.append(t("no_data_cli", lang))

    risky = await repo.get_risky_clients(tenant.id, limit=5)
    if risky:
        lines.append("")
        lines.append(f"<b>{t('risky_clients', lang)}</b>")
        for c in risky:
            parts = []
            if c["no_show_count"]:
                parts.append(f"{t('noshows_label', lang)}: {c['no_show_count']}")
            if c["cancelled_count"]:
                parts.append(f"{t('cancels_label', lang)}: {c['cancelled_count']}")
            lines.append(f"• {c['client_name']} — {', '.join(parts)}")

    return "\n".join(lines)


def _analytics_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("back_to_dash", lang), callback_data="dash:day")],
    ])


# ── Dashboard handlers ────────────────────────────────────────────────────────

@router.message(F.text.in_(all_variants("btn_dashboard")), SetupDone(), StateFilter("*"))
async def quick_dashboard(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.clear()
    lang = tenant.owner_lang or "ru"
    text = await _build_dashboard(tenant, "day")
    await _delete_old_info(message.bot, message.chat.id)
    sent = await message.answer(text, reply_markup=_dashboard_kb("day", lang), parse_mode="HTML")
    _last_info_msg[message.chat.id] = sent.message_id


@router.callback_query(F.data.startswith("dash:"), SetupDone())
async def cb_dashboard_period(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    period = callback.data[len("dash:"):]
    if period == "analytics":
        text = await _analytics_text(tenant)
        await callback.message.edit_text(text, reply_markup=_analytics_kb(lang), parse_mode="HTML")
        await callback.answer()
        return
    if period not in ("day", "week", "month"):
        await callback.answer()
        return
    try:
        text = await _build_dashboard(tenant, period)
        await callback.message.edit_text(text, reply_markup=_dashboard_kb(period, lang), parse_mode="HTML")
    except Exception:
        log.exception("cb_dashboard_period failed for tenant %d period=%s", tenant.id, period)
    await callback.answer()


# ── Booking card (Variant C: tap booking → card → back to list) ──────────────

@router.callback_query(F.data.startswith("bk_card:"), SetupDone())
async def cb_booking_card(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", lang), show_alert=True)
        return
    rest = callback.data[len("bk_card:"):]
    bid_str, date_str = rest.split("|", 1)
    booking = await repo.get_booking(int(bid_str))
    if not booking or booking["status"] == "cancelled":
        await callback.answer(t("already_cancelled", lang), show_alert=True)
        return
    paid   = booking.get("paid") or False
    status = booking.get("status", "confirmed")
    await callback.message.edit_text(
        _booking_card_text(dict(booking), lang),
        reply_markup=_booking_card_kb(booking["id"], paid, date_str, status, lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bk_list|"), SetupDone())
async def cb_back_to_list(callback: CallbackQuery, tenant: TenantConfig) -> None:
    from zoneinfo import ZoneInfo
    from datetime import date as _d
    lang = tenant.owner_lang or "ru"
    date_str = callback.data[len("bk_list|"):]
    tz = ZoneInfo(tenant.timezone or "UTC")
    target  = _d.fromisoformat(date_str)
    dt_from = datetime(target.year, target.month, target.day,  0,  0, tzinfo=tz).astimezone(timezone.utc)
    dt_to   = datetime(target.year, target.month, target.day, 23, 59, tzinfo=tz).astimezone(timezone.utc)
    events  = await get_adapter(tenant).get_events(dt_from, dt_to)
    today = datetime.now(tz).date()
    diff  = (target - today).days
    prefix = {0: t("lbl_today", lang), 1: t("lbl_tomorrow", lang)}.get(diff) or \
             DAY_SHORT[lang][target.weekday()]
    date_label = f"{prefix} {fmt_date(target.day, target.month - 1, lang)}"
    text, kb = _schedule_text_and_kb(events, date_label, date_str, lang)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Quick actions: paid / note / reschedule ───────────────────────────────────

@router.callback_query(F.data.startswith("bk_paid:"), SetupDone())
async def cb_booking_paid(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", lang), show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    booking = await repo.get_booking(booking_id)
    if not booking:
        await callback.answer(t("not_found", lang), show_alert=True)
        return
    new_paid = not (booking.get("paid") or False)
    await repo.set_booking_paid(booking_id, new_paid)
    await callback.answer(t("toast_paid", lang) if new_paid else t("toast_unpaid", lang))
    # find date_str from ◀️ back button and refresh card
    date_str = ""
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("bk_list|"):
                    date_str = btn.callback_data[len("bk_list|"):]
    booking = await repo.get_booking(booking_id)
    status  = booking.get("status", "confirmed") if booking else "confirmed"
    try:
        await callback.message.edit_text(
            _booking_card_text(dict(booking), lang),
            reply_markup=_booking_card_kb(booking_id, new_paid, date_str, status, lang),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("bk_arrived:"), SetupDone())
async def cb_booking_arrived(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", lang), show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    await repo.update_booking_status(booking_id, "completed")
    await callback.answer(t("toast_arrived", lang))
    booking  = await repo.get_booking(booking_id)
    date_str = ""
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("bk_list|"):
                    date_str = btn.callback_data[len("bk_list|"):]
    try:
        await callback.message.edit_text(
            _booking_card_text(dict(booking), lang),
            reply_markup=_booking_card_kb(booking_id, booking.get("paid") or False, date_str, "completed", lang),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("bk_noshow:"), SetupDone())
async def cb_booking_noshow(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", lang), show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    await repo.update_booking_status(booking_id, "no_show")
    await callback.answer(t("toast_noshow", lang))
    booking  = await repo.get_booking(booking_id)
    date_str = ""
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("bk_list|"):
                    date_str = btn.callback_data[len("bk_list|"):]
    try:
        await callback.message.edit_text(
            _booking_card_text(dict(booking), lang),
            reply_markup=_booking_card_kb(booking_id, booking.get("paid") or False, date_str, "no_show", lang),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("bk_note:"), SetupDone())
async def cb_booking_note_prompt(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", lang), show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    await state.set_state(QuickEdit.note)
    await state.update_data(booking_id=booking_id, msg_id=callback.message.message_id, lang=lang)
    await callback.answer()
    await callback.message.answer(t("enter_note", lang), parse_mode="HTML")


@router.message(QuickEdit.note, Command("skip"))
async def cb_note_skip(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.clear()
    await message.answer(t("cancelled_act", lang))


@router.message(QuickEdit.note, F.text.func(lambda x: not x.startswith("/")))
async def cb_note_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await repo.set_booking_note(data["booking_id"], message.text.strip())
    await state.clear()
    await message.answer(t("note_saved", lang))


@router.callback_query(F.data.startswith("bk_reschedule:"), SetupDone())
async def cb_booking_reschedule_prompt(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", lang), show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    await state.set_state(QuickEdit.reschedule)
    await state.update_data(booking_id=booking_id, tenant_id=tenant.id, lang=lang)
    await callback.answer()
    await callback.message.answer(t("enter_reschedule", lang), parse_mode="HTML")


@router.message(QuickEdit.reschedule, Command("skip"))
async def cb_reschedule_skip(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.clear()
    await message.answer(t("cancelled_act", lang))


@router.message(QuickEdit.reschedule, F.text.func(lambda x: not x.startswith("/")))
async def cb_reschedule_save(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    booking_id = data["booking_id"]
    new_dt = parse_datetime(message.text.strip(), tenant)
    if new_dt is None:
        await message.answer(t("bad_reschedule", lang), parse_mode="HTML")
        return
    await repo.update_booking_time(booking_id, new_dt)
    await state.clear()
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    formatted = fmt_date(new_dt.astimezone(tz).day, new_dt.astimezone(tz).month - 1, lang) + \
                " " + new_dt.astimezone(tz).strftime("%H:%M")
    await message.answer(f"✅ #{booking_id} → {formatted}")


# ── Guided booking wizard ─────────────────────────────────────────────────────

async def _start_booking(message_or_query, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    cats = await repo.get_categories(tenant.id)
    if cats:
        await state.set_state(QuickBook.category)
        text = f"{t('new_booking', lang)}\n\n{t('choose_cat', lang)}"
        kb   = _cats_kb(cats, lang)
    else:
        await state.set_state(QuickBook.service)
        text = f"{t('new_booking', lang)}\n\n{t('choose_svc', lang)}"
        names = [s.strip() for s in tenant.services.split(",") if s.strip()]
        rows  = [[InlineKeyboardButton(text=s, callback_data=f"qb_svc:{s}")] for s in names]
        rows.append([InlineKeyboardButton(text=t("btn_cancel_act", lang), callback_data="qb_cancel")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(message_or_query, Message):
        sent = await message_or_query.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        sent = await message_or_query.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await message_or_query.answer()
    await state.update_data(wizard_msg_id=sent.message_id, lang=lang)


@router.message(F.text.in_(all_variants("btn_new")), SetupDone(), StateFilter("*"))
async def quick_new(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return
    await state.clear()
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
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.clear()
    await callback.message.edit_text(t("cancelled_act", lang), reply_markup=None)
    await callback.answer()


# Step 0 — category chosen
@router.callback_query(QuickBook.category, F.data.startswith("qb_cat:"))
async def cb_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    cat_id = int(callback.data[len("qb_cat:"):])
    cats   = await repo.get_categories(tenant.id)
    cat    = next((c for c in cats if c["id"] == cat_id), None)
    cat_name = cat["name"] if cat else "?"
    items  = await repo.get_items(cat_id)
    await state.update_data(category=cat_name)
    await state.set_state(QuickBook.service)
    await callback.message.edit_text(
        f"{t('new_booking', lang)}\n"
        f"{t('cat_label', lang)}: <b>{cat_name}</b>\n\n"
        f"{t('choose_svc', lang)}",
        reply_markup=_items_for_booking_kb(items, lang),
    )
    await callback.answer()


@router.callback_query(QuickBook.service, F.data == "qb_back_cats")
async def cb_back_to_cats(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    cats = await repo.get_categories(tenant.id)
    await state.set_state(QuickBook.category)
    await callback.message.edit_text(
        f"{t('new_booking', lang)}\n\n{t('choose_cat', lang)}",
        reply_markup=_cats_kb(cats, lang),
    )
    await callback.answer()


# Step 1 — service chosen
@router.callback_query(QuickBook.service, F.data.startswith("qb_svc:"))
async def cb_service(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    service  = callback.data[len("qb_svc:"):]
    data     = await state.get_data()
    category = data.get("category", "")
    await state.update_data(service=service)
    await state.set_state(QuickBook.date)
    cat_line = f"{t('cat_label', lang)}: <b>{category}</b>\n" if category else ""
    await callback.message.edit_text(
        f"{t('new_booking', lang)}\n"
        f"{cat_line}{t('svc_label', lang)}: <b>{service}</b>\n\n"
        f"{t('choose_date', lang)}",
        reply_markup=_date_kb(tenant),
    )
    await callback.answer()


# Step 2 — date chosen
@router.callback_query(QuickBook.date, F.data.startswith("qb_date:"))
async def cb_date(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    value = callback.data[len("qb_date:"):]
    data  = await state.get_data()
    service = data.get("service", "")

    if value == "custom":
        await callback.message.edit_text(
            f"{t('new_booking', lang)}\n"
            f"{t('svc_label', lang)}: <b>{service}</b>\n\n"
            f"{t('bad_date', lang)}",
            reply_markup=None, parse_mode="HTML",
        )
        await callback.answer()
        return

    await state.update_data(date=value)
    await state.set_state(QuickBook.time)
    await callback.message.edit_text(
        f"{t('new_booking', lang)}\n"
        f"{t('svc_label', lang)}: <b>{service}</b>\n"
        f"{t('date_label', lang)}: <b>{value}</b>\n\n"
        f"{t('choose_time', lang)}",
        reply_markup=await _time_kb(tenant, value), parse_mode="HTML",
    )
    await callback.answer()


@router.message(QuickBook.date, ~F.text.in_(MAIN_KB_TEXTS))
async def text_date(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
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
                        f"{t('new_booking', lang)}\n"
                        f"{t('svc_label', lang)}: <b>{service}</b>\n\n"
                        f"{t('bad_date', lang)}"
                    ),
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass
        await message.answer(t("bad_date", lang), parse_mode="HTML")
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
                    f"{t('new_booking', lang)}\n"
                    f"{t('svc_label', lang)}: <b>{service}</b>\n"
                    f"{t('date_label', lang)}: <b>{date_str}</b>\n\n"
                    f"{t('choose_time', lang)}"
                ),
                reply_markup=time_kb,
                parse_mode="HTML",
            )
            return
        except Exception:
            pass
    await message.answer(
        f"{t('date_label', lang)}: <b>{date_str}</b>\n\n{t('choose_time', lang)}",
        reply_markup=time_kb, parse_mode="HTML",
    )


# Step 3 — time chosen
@router.callback_query(QuickBook.time, F.data.startswith("qb_time:"))
async def cb_time(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    lang  = tenant.owner_lang or "ru"
    value = callback.data[len("qb_time:"):]
    data  = await state.get_data()
    service  = data.get("service", "")
    date_str = data.get("date", "")

    if value == "custom":
        await callback.message.edit_text(
            f"{t('new_booking', lang)}\n"
            f"{t('svc_label', lang)}: <b>{service}</b>\n"
            f"{t('date_label', lang)}: <b>{date_str}</b>\n\n"
            f"{t('bad_time', lang)}",
            reply_markup=None,
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await state.update_data(time=value)
    await state.set_state(QuickBook.client)
    await callback.message.edit_text(
        f"{t('new_booking', lang)}\n"
        f"{t('svc_label', lang)}: <b>{service}</b>\n"
        f"{t('date_label', lang)}: <b>{date_str}</b>\n"
        f"{t('time_label', lang)}: <b>{value}</b>\n\n"
        f"{t('client_name_lbl', lang)}",
        reply_markup=None,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(QuickBook.time, ~F.text.in_(MAIN_KB_TEXTS))
async def text_time(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
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
                        f"{t('new_booking', lang)}\n"
                        f"{t('svc_label', lang)}: <b>{service}</b>\n"
                        f"{t('date_label', lang)}: <b>{date_str}</b>\n\n"
                        f"{t('bad_time', lang)}"
                    ),
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass
        await message.answer(t("bad_time", lang), parse_mode="HTML")
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
                    f"{t('new_booking', lang)}\n"
                    f"{t('svc_label', lang)}: <b>{service}</b>\n"
                    f"{t('date_label', lang)}: <b>{date_str}</b>\n"
                    f"{t('time_label', lang)}: <b>{raw}</b>\n\n"
                    f"{t('client_name_lbl', lang)}"
                ),
                parse_mode="HTML",
            )
            return
        except Exception:
            pass
    await message.answer(
        f"✅ {t('time_label', lang)}: <b>{raw}</b>\n\n{t('client_name_lbl', lang)}",
        parse_mode="HTML",
    )


# Step 4 — client name → create booking
@router.message(QuickBook.client, ~F.text.in_(MAIN_KB_TEXTS))
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
    lang = tenant.owner_lang or "ru"
    if dt is None:
        try:
            await message.delete()
        except Exception:
            pass
        result = t("booking_fail", lang)
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
                svc_extras.append(f"{svc_info['duration_minutes']}{t('min_lbl', lang)}")
            svc_line = service + (" · " + " · ".join(svc_extras) if svc_extras else "")

            if cal_id:
                gcal_note = " · Google Calendar 📅"
            elif tenant.google_cal_id:
                gcal_note = f"\n⚠️ {t('gcal_sync_failed', lang)}"
            else:
                gcal_note = ""
            result = (
                f"✅ <b>{client_name}</b> — <b>{svc_line}</b>\n"
                f"{date_str}, {time_str}{gcal_note}\n"
                f"#{bid}"
            )
        except Exception as exc:
            log.exception("QuickBook create_event failed")
            result = f"❌ {exc}"

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
                parse_mode="HTML",
            )
            return
        except Exception:
            pass

    await message.answer(result, reply_markup=get_main_kb(lang), parse_mode="HTML")
