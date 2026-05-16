"""Structured booking FSM — owner creates appointments for clients."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Union

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import aria.db.repo as repo
from aria.config import TenantConfig
from aria.services.gcal import add_to_calendar_url

log = logging.getLogger(__name__)
router = Router()


class BookingSG(StatesGroup):
    client_name = State()
    pick_date   = State()
    pick_time   = State()
    confirm     = State()


_MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_MONTHS_SHORT = ("янв", "фев", "мар", "апр", "май", "июн",
                 "июл", "авг", "сен", "окт", "ноя", "дек")
_DAYS_SHORT   = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _fmt_date(d: date) -> str:
    return f"{d.day} {_MONTHS_SHORT[d.month - 1]} ({_DAYS_SHORT[d.weekday()]})"


def _parse_date(text: str) -> date | None:
    text = text.strip().lower()
    today = date.today()

    if "послезавтра" in text:
        return today + timedelta(days=2)
    if "завтра" in text:
        return today + timedelta(days=1)
    if "сегодня" in text:
        return today

    # DD.MM or DD.MM.YYYY
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", text)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else today.year
        if yr < 100:
            yr += 2000
        try:
            d = date(yr, mon, day)
            return d if d >= today else date(yr + 1, mon, day)
        except ValueError:
            return None

    # DD monthname
    for name, mon in _MONTHS_RU.items():
        m2 = re.search(rf"\b(\d{{1,2}})\s+{name}\b", text)
        if m2:
            day = int(m2.group(1))
            yr = today.year
            try:
                d = date(yr, mon, day)
                return d if d >= today else date(yr + 1, mon, day)
            except ValueError:
                return None
    return None


def _date_kb() -> InlineKeyboardMarkup:
    today = date.today()
    rows = []
    for i in range(5):
        d = today + timedelta(days=i)
        prefix = "Сегодня, " if i == 0 else ("Завтра, " if i == 1 else "")
        rows.append([InlineKeyboardButton(
            text=f"{prefix}{_fmt_date(d)}",
            callback_data=f"book:d:{d.isoformat()}",
        )])
    rows.append([InlineKeyboardButton(text="📝 Другой день...", callback_data="book:d:other")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _time_kb(tenant: TenantConfig) -> InlineKeyboardMarkup:
    step = max(tenant.salon_slot_minutes, 30)
    slots: list[str] = []
    minutes = tenant.salon_open_hour * 60
    end = tenant.salon_close_hour * 60
    while minutes < end:
        h, m = divmod(minutes, 60)
        slots.append(f"{h:02d}:{m:02d}")
        minutes += step

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slot in slots:
        row.append(InlineKeyboardButton(text=slot, callback_data=f"book:t:{slot}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="← Назад к дате", callback_data="book:back:date")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Создать запись", callback_data="book:confirm"),
        InlineKeyboardButton(text="❌ Отмена",         callback_data="book:cancel"),
    ]])


async def start_booking(
    event: Union[Message, CallbackQuery],
    state: FSMContext,
    tenant: TenantConfig,
    service: str,
) -> None:
    """Entry point — called after a service is selected via inline keyboard."""
    await state.set_state(BookingSG.client_name)
    await state.update_data(service=service, tenant_id=tenant.tenant_id)
    msg = event.message if isinstance(event, CallbackQuery) else event
    await msg.answer(
        f"📋 <b>Новая запись</b>\n"
        f"💅 Услуга: <b>{service}</b>\n\n"
        f"👤 Введите имя клиента:",
        parse_mode="HTML",
    )


# ── Client name ───────────────────────────────────────────────────────────────

@router.message(BookingSG.client_name)
async def got_client_name(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Введите имя клиента:")
        return
    await state.update_data(client_name=name)
    await state.set_state(BookingSG.pick_date)
    await message.answer("📅 Выберите дату:", reply_markup=_date_kb())


# ── Date selection ────────────────────────────────────────────────────────────

@router.callback_query(BookingSG.pick_date, F.data.startswith("book:d:"))
async def got_date_button(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    raw = callback.data[len("book:d:"):]
    if raw == "other":
        await callback.message.edit_text(
            "📅 Введите дату:\n"
            "<i>Например: завтра · 23 мая · 23.05</i>",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    try:
        d = date.fromisoformat(raw)
    except ValueError:
        await callback.answer("Неверная дата.")
        return

    await state.update_data(chosen_date=raw)
    await state.set_state(BookingSG.pick_time)
    await callback.message.edit_text(
        f"⏰ <b>{_fmt_date(d)}</b> — выберите время:",
        parse_mode="HTML",
        reply_markup=_time_kb(tenant),
    )
    await callback.answer()


@router.message(BookingSG.pick_date)
async def got_date_text(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    d = _parse_date(message.text)
    if not d:
        await message.answer(
            "Не могу распознать дату. Попробуйте:\n"
            "• <i>завтра</i>\n• <i>23 мая</i>\n• <i>23.05</i>",
            parse_mode="HTML",
        )
        return
    await state.update_data(chosen_date=d.isoformat())
    await state.set_state(BookingSG.pick_time)
    await message.answer(
        f"⏰ <b>{_fmt_date(d)}</b> — выберите время:",
        parse_mode="HTML",
        reply_markup=_time_kb(tenant),
    )


# ── Time selection ────────────────────────────────────────────────────────────

@router.callback_query(BookingSG.pick_time, F.data == "book:back:date")
async def back_to_date(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BookingSG.pick_date)
    await callback.message.edit_text("📅 Выберите дату:", reply_markup=_date_kb())
    await callback.answer()


@router.callback_query(BookingSG.pick_time, F.data.startswith("book:t:"))
async def got_time(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    time_str = callback.data[len("book:t:"):]
    data = await state.get_data()
    d = date.fromisoformat(data["chosen_date"])
    dt_display = f"{_fmt_date(d)} в {time_str}"

    await state.update_data(chosen_time=time_str, dt_display=dt_display)
    await state.set_state(BookingSG.confirm)

    await callback.message.edit_text(
        f"📋 <b>Проверьте запись:</b>\n\n"
        f"👤 Клиент: <b>{data['client_name']}</b>\n"
        f"💅 Услуга: <b>{data['service']}</b>\n"
        f"📅 {dt_display}",
        parse_mode="HTML",
        reply_markup=_confirm_kb(),
    )
    await callback.answer()


# ── Confirm / Cancel ──────────────────────────────────────────────────────────

@router.callback_query(BookingSG.confirm, F.data == "book:confirm")
async def confirm_booking(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    data = await state.get_data()
    await state.clear()

    d = date.fromisoformat(data["chosen_date"])
    h, m = map(int, data["chosen_time"].split(":"))
    scheduled_at = datetime.combine(d, time(h, m))

    client_name = data["client_name"]
    service     = data["service"]

    await repo.create_booking(
        user_id=callback.from_user.id,
        client_name=client_name,
        service=service,
        scheduled_at=scheduled_at,
    )

    gcal_url = add_to_calendar_url(
        title=f"{service} — {client_name}",
        start=scheduled_at,
        duration_minutes=tenant.salon_slot_minutes,
        details=f"Клиент: {client_name}\nУслуга: {service}",
    )
    await callback.message.edit_text(
        f"✅ <b>Запись создана!</b>\n\n"
        f"👤 {client_name}\n"
        f"💅 {service}\n"
        f"📅 {data['dt_display']}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📅 Добавить в Google Calendar", url=gcal_url),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "book:cancel")
async def cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Запись отменена.")
    await callback.answer()
