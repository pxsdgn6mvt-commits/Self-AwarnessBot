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
        [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📅 Завтра")],
        [KeyboardButton(text="➕ Новая запись"), KeyboardButton(text="📋 Ближайшие")],
        [KeyboardButton(text="📧 Почта"), KeyboardButton(text="📱 Меню")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ── FSM ───────────────────────────────────────────────────────────────────────

class QuickBook(StatesGroup):
    service = State()
    date    = State()
    time    = State()
    client  = State()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _services_kb(tenant: TenantConfig) -> InlineKeyboardMarkup:
    items = [s.strip() for s in tenant.services.split(",") if s.strip()]
    rows = [[InlineKeyboardButton(text=s, callback_data=f"qb_svc:{s}")] for s in items]
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


def _time_kb(tenant: TenantConfig, date_str: str) -> InlineKeyboardMarkup:
    h, m = tenant.open_hour, 0
    buttons: list[InlineKeyboardButton] = []
    while h < tenant.close_hour:
        label = f"{h:02d}:{m:02d}"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"qb_time:{label}"))
        total = h * 60 + m + tenant.slot_minutes
        h, m = divmod(total, 60)
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text="📝 Другое время", callback_data="qb_time:custom")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="qb_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _schedule_text_and_kb(
    events: list[dict], date_label: str
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not events:
        return f"📅 {date_label}\n\nЗаписей нет.", None

    lines = [f"📅 {date_label}\n"]
    cancel_btns: list[InlineKeyboardButton] = []
    for e in events:
        bid = e.get("id")
        lines.append(f"• {e['time']} — {e['client']}, {e['service']}")
        if isinstance(bid, int):
            cancel_btns.append(
                InlineKeyboardButton(
                    text=f"❌ {e['client']} {e['time']}",
                    callback_data=f"del_booking:{bid}",
                )
            )

    rows: list[list[InlineKeyboardButton]] = [cancel_btns[i:i+2] for i in range(0, len(cancel_btns), 2)]
    rows.append([InlineKeyboardButton(text="➕ Добавить запись", callback_data="qb_start")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    return "\n".join(lines), kb


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
    text, kb = _schedule_text_and_kb(events, date_label)

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
    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n❌ <i>Запись #{booking_id} отменена</i>",
            reply_markup=None,
        )
    except Exception:
        pass


# ── Guided booking wizard ─────────────────────────────────────────────────────

async def _start_booking(message_or_query, state: FSMContext, tenant: TenantConfig) -> None:
    await state.set_state(QuickBook.service)
    text = "➕ <b>Новая запись</b>\n\nВыбери услугу:"
    kb   = _services_kb(tenant)
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


# Step 1 — service chosen
@router.callback_query(QuickBook.service, F.data.startswith("qb_svc:"))
async def cb_service(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    service = callback.data[len("qb_svc:"):]
    await state.update_data(service=service)
    await state.set_state(QuickBook.date)
    await callback.message.edit_text(
        f"➕ <b>Новая запись</b>\n"
        f"Услуга: <b>{service}</b>\n\n"
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
        reply_markup=_time_kb(tenant, value),
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
                reply_markup=_time_kb(tenant, date_str),
            )
            return
        except Exception:
            pass
    await message.answer(
        f"✅ Дата: <b>{date_str}</b>\n\nВыбери время:",
        reply_markup=_time_kb(tenant, date_str),
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

            gcal_note = " · Google Calendar 📅" if cal_id else ""
            result = (
                f"✅ <b>{client_name}</b> — <b>{service}</b>\n"
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
