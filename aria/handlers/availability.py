"""Availability management handlers for the owner-bot Settings panel."""

from __future__ import annotations

import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import aria.db.repo as repo
from aria.filters import SetupDone
from aria.handlers.quick import MAIN_KB_TEXTS
from aria.tenant import TenantConfig

router = Router()


class CloseDayFSM(StatesGroup):
    waiting_date = State()
    confirm      = State()


class ChangeHoursFSM(StatesGroup):
    waiting_date  = State()
    waiting_hours = State()
    confirm       = State()


class BlockSlotFSM(StatesGroup):
    waiting_date = State()
    waiting_time = State()
    confirm      = State()


# ── Keyboard helpers ──────────────────────────────────────────────────────────

def _avail_main_kb(master_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Закрыть день",           callback_data=f"cfg:avail_close:{master_id}")],
        [InlineKeyboardButton(text="🕐 Изменить часы",           callback_data=f"cfg:avail_hours:{master_id}")],
        [InlineKeyboardButton(text="⛔ Заблокировать слот",      callback_data=f"cfg:avail_slot:{master_id}")],
        [InlineKeyboardButton(text="📋 Существующие блокировки", callback_data=f"cfg:avail_list:{master_id}")],
        [InlineKeyboardButton(text="◀️ Назад к мастерам",        callback_data="cfg:masters")],
    ])


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да",     callback_data="cfg:avail_yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cfg:avail_no"),
    ]])


def _avail_row_text(row: object) -> str:
    date_str = row["date"].strftime("%d.%m.%Y")
    if row["time_from"] is None:
        return f"📅 {date_str} — 🔴 Закрыт весь день"
    tf = row["time_from"].strftime("%H:%M")
    tt = row["time_to"].strftime("%H:%M") if row["time_to"] else "?"
    if row["is_open"]:
        return f"📅 {date_str} — 🕐 {tf}–{tt}"
    return f"📅 {date_str} — ⛔ {tf}–{tt}"


def _list_kb(rows: list, master_id: int) -> InlineKeyboardMarkup:
    btn_rows = []
    for row in rows:
        btn_rows.append([InlineKeyboardButton(
            text=f"🗑 {row['date'].strftime('%d.%m')}",
            callback_data=f"cfg:avail_del:{row['id']}:{master_id}",
        )])
    btn_rows.append([InlineKeyboardButton(
        text="◀️ Назад", callback_data=f"cfg:avail:{master_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=btn_rows)


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_date(text: str) -> Optional[datetime.date]:
    text = text.strip()
    today = datetime.date.today()
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.datetime.strptime(text, fmt).date()
            if fmt == "%d.%m":
                d = d.replace(year=today.year)
                if d < today:
                    d = d.replace(year=today.year + 1)
            return d
        except ValueError:
            continue
    return None


def _parse_hours(text: str) -> Optional[tuple[datetime.time, datetime.time]]:
    text = text.strip().replace(" ", "")
    parts = text.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        def _t(s: str) -> datetime.time:
            if ":" in s:
                h, m = s.split(":", 1)
                return datetime.time(int(h), int(m))
            return datetime.time(int(s), 0)
        t_from, t_to = _t(parts[0]), _t(parts[1])
        return (t_from, t_to) if t_from < t_to else None
    except (ValueError, TypeError):
        return None


def _parse_time(text: str) -> Optional[datetime.time]:
    text = text.strip()
    try:
        if ":" in text:
            h, m = text.split(":", 1)
            return datetime.time(int(h), int(m))
        return datetime.time(int(text), 0)
    except (ValueError, TypeError):
        return None


# ── Main availability screen ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cfg:avail:"), SetupDone())
async def cb_avail_main(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    master = await repo.get_master_by_id(master_id)
    if not master or master["tenant_id"] != tenant.id:
        await callback.answer("Мастер не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        f"📅 <b>Расписание — {master['name']}</b>\n\nВыберите действие:",
        reply_markup=_avail_main_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── FSM: Close day ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cfg:avail_close:"), SetupDone())
async def cb_avail_close(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    await state.set_state(CloseDayFSM.waiting_date)
    await state.update_data(master_id=master_id, tenant_id=tenant.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "🔴 <b>Закрыть день</b>\n\nВведите дату (ДД.ММ.ГГГГ):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CloseDayFSM.waiting_date, F.text, ~F.text.in_(MAIN_KB_TEXTS))
async def fsm_close_date(message: Message, state: FSMContext) -> None:
    d = _parse_date(message.text)
    if d is None:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ (например: 25.05.2026):")
        return
    if d < datetime.date.today():
        await message.answer("Дата не может быть в прошлом. Введите другую дату:")
        return
    data = await state.get_data()
    master = await repo.get_master_by_id(data["master_id"])
    await state.update_data(date=d.isoformat())
    await state.set_state(CloseDayFSM.confirm)
    await message.answer(
        f"Закрыть <b>{d.strftime('%d.%m.%Y')}</b> для <b>{master['name']}</b>?",
        reply_markup=_confirm_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cfg:avail_yes", StateFilter(CloseDayFSM.confirm), SetupDone())
async def fsm_close_confirm(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    await state.clear()
    d = datetime.date.fromisoformat(data["date"])
    await repo.create_availability(
        tenant_id=data["tenant_id"],
        master_id=data["master_id"],
        date=d,
        is_open=False,
    )
    master_id = data["master_id"]
    master = await repo.get_master_by_id(master_id)
    await callback.message.edit_text(
        f"✅ {d.strftime('%d.%m.%Y')} закрыт для <b>{master['name']}</b>.",
        reply_markup=_avail_main_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── FSM: Change hours ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cfg:avail_hours:"), SetupDone())
async def cb_avail_hours(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    await state.set_state(ChangeHoursFSM.waiting_date)
    await state.update_data(master_id=master_id, tenant_id=tenant.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "🕐 <b>Изменить часы</b>\n\nВведите дату (ДД.ММ.ГГГГ):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ChangeHoursFSM.waiting_date, F.text, ~F.text.in_(MAIN_KB_TEXTS))
async def fsm_hours_date(message: Message, state: FSMContext) -> None:
    d = _parse_date(message.text)
    if d is None:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ:")
        return
    if d < datetime.date.today():
        await message.answer("Дата не может быть в прошлом. Введите другую дату:")
        return
    await state.update_data(date=d.isoformat())
    await state.set_state(ChangeHoursFSM.waiting_hours)
    await message.answer(
        f"Дата: <b>{d.strftime('%d.%m.%Y')}</b>\n\nВведите часы работы (например: <code>12-18</code>):",
        parse_mode="HTML",
    )


@router.message(ChangeHoursFSM.waiting_hours, F.text, ~F.text.in_(MAIN_KB_TEXTS))
async def fsm_hours_input(message: Message, state: FSMContext) -> None:
    result = _parse_hours(message.text)
    if result is None:
        await message.answer(
            "Неверный формат. Введите часы как <code>ЧЧ-ЧЧ</code> (например: <code>12-18</code>).\n"
            "Начало должно быть меньше конца.",
            parse_mode="HTML",
        )
        return
    t_from, t_to = result
    data = await state.get_data()
    master = await repo.get_master_by_id(data["master_id"])
    d = datetime.date.fromisoformat(data["date"])
    await state.update_data(
        time_from=t_from.strftime("%H:%M"),
        time_to=t_to.strftime("%H:%M"),
    )
    await state.set_state(ChangeHoursFSM.confirm)
    await message.answer(
        f"Установить <b>{d.strftime('%d.%m.%Y')}</b>: "
        f"<b>{t_from.strftime('%H:%M')}–{t_to.strftime('%H:%M')}</b> "
        f"для <b>{master['name']}</b>?",
        reply_markup=_confirm_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cfg:avail_yes", StateFilter(ChangeHoursFSM.confirm), SetupDone())
async def fsm_hours_confirm(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    await state.clear()
    d      = datetime.date.fromisoformat(data["date"])
    t_from = datetime.time.fromisoformat(data["time_from"])
    t_to   = datetime.time.fromisoformat(data["time_to"])
    await repo.create_availability(
        tenant_id=data["tenant_id"],
        master_id=data["master_id"],
        date=d,
        is_open=True,
        time_from=t_from,
        time_to=t_to,
    )
    master_id = data["master_id"]
    master = await repo.get_master_by_id(master_id)
    await callback.message.edit_text(
        f"✅ {d.strftime('%d.%m.%Y')}: {t_from.strftime('%H:%M')}–{t_to.strftime('%H:%M')} "
        f"установлен для <b>{master['name']}</b>.",
        reply_markup=_avail_main_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── FSM: Block slot ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cfg:avail_slot:"), SetupDone())
async def cb_avail_slot(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    await state.set_state(BlockSlotFSM.waiting_date)
    await state.update_data(master_id=master_id, tenant_id=tenant.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "⛔ <b>Заблокировать слот</b>\n\nВведите дату (ДД.ММ.ГГГГ):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(BlockSlotFSM.waiting_date, F.text, ~F.text.in_(MAIN_KB_TEXTS))
async def fsm_slot_date(message: Message, state: FSMContext) -> None:
    d = _parse_date(message.text)
    if d is None:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ:")
        return
    if d < datetime.date.today():
        await message.answer("Дата не может быть в прошлом. Введите другую дату:")
        return
    await state.update_data(date=d.isoformat())
    await state.set_state(BlockSlotFSM.waiting_time)
    await message.answer(
        f"Дата: <b>{d.strftime('%d.%m.%Y')}</b>\n\nВведите время слота (например: <code>14:00</code>):",
        parse_mode="HTML",
    )


@router.message(BlockSlotFSM.waiting_time, F.text, ~F.text.in_(MAIN_KB_TEXTS))
async def fsm_slot_time(message: Message, state: FSMContext) -> None:
    t = _parse_time(message.text)
    if t is None:
        await message.answer(
            "Неверный формат. Введите время как <code>ЧЧ:ММ</code> (например: <code>14:00</code>):",
            parse_mode="HTML",
        )
        return
    data = await state.get_data()
    slot_minutes = await repo.get_tenant_slot_minutes(data["tenant_id"])
    t_to_dt = datetime.datetime.combine(datetime.date.today(), t) + datetime.timedelta(minutes=slot_minutes)
    t_to    = t_to_dt.time()
    master  = await repo.get_master_by_id(data["master_id"])
    d       = datetime.date.fromisoformat(data["date"])
    await state.update_data(
        time_from=t.strftime("%H:%M"),
        time_to=t_to.strftime("%H:%M"),
    )
    await state.set_state(BlockSlotFSM.confirm)
    await message.answer(
        f"Заблокировать слот <b>{t.strftime('%H:%M')}–{t_to.strftime('%H:%M')}</b> "
        f"<b>{d.strftime('%d.%m.%Y')}</b> для <b>{master['name']}</b>?",
        reply_markup=_confirm_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cfg:avail_yes", StateFilter(BlockSlotFSM.confirm), SetupDone())
async def fsm_slot_confirm(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    await state.clear()
    d      = datetime.date.fromisoformat(data["date"])
    t_from = datetime.time.fromisoformat(data["time_from"])
    t_to   = datetime.time.fromisoformat(data["time_to"])
    await repo.create_availability(
        tenant_id=data["tenant_id"],
        master_id=data["master_id"],
        date=d,
        is_open=False,
        time_from=t_from,
        time_to=t_to,
    )
    master_id = data["master_id"]
    master = await repo.get_master_by_id(master_id)
    await callback.message.edit_text(
        f"✅ Слот {t_from.strftime('%H:%M')}–{t_to.strftime('%H:%M')} "
        f"{d.strftime('%d.%m.%Y')} заблокирован для <b>{master['name']}</b>.",
        reply_markup=_avail_main_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Cancel (shared across all confirm states) ─────────────────────────────────

@router.callback_query(
    F.data == "cfg:avail_no",
    StateFilter(CloseDayFSM.confirm, ChangeHoursFSM.confirm, BlockSlotFSM.confirm),
    SetupDone(),
)
async def fsm_avail_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    master_id = data.get("master_id")
    await state.clear()
    await callback.message.edit_text(
        "Отменено.",
        reply_markup=_avail_main_kb(master_id) if master_id else None,
    )
    await callback.answer()


# ── List existing blocks ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cfg:avail_list:"), SetupDone())
async def cb_avail_list(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    master = await repo.get_master_by_id(master_id)
    if not master or master["tenant_id"] != tenant.id:
        await callback.answer("Мастер не найден.", show_alert=True)
        return
    rows = await repo.get_availability(master_id)
    if not rows:
        text = f"📋 <b>Блокировки — {master['name']}</b>\n\nНет активных блокировок."
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"cfg:avail:{master_id}")
        ]])
    else:
        lines = [f"📋 <b>Блокировки — {master['name']}</b>\n"]
        lines.extend(_avail_row_text(r) for r in rows)
        text = "\n".join(lines)
        kb = _list_kb(rows, master_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ── Delete a block ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cfg:avail_del:"), SetupDone())
async def cb_avail_del(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    # callback_data: cfg:avail_del:{avail_id}:{master_id}
    parts     = callback.data.split(":")
    avail_id  = int(parts[2])
    master_id = int(parts[3])
    master = await repo.get_master_by_id(master_id)
    if not master or master["tenant_id"] != tenant.id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await repo.delete_availability(avail_id)
    rows = await repo.get_availability(master_id)
    if not rows:
        text = f"📋 <b>Блокировки — {master['name']}</b>\n\nНет активных блокировок."
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"cfg:avail:{master_id}")
        ]])
    else:
        lines = [f"📋 <b>Блокировки — {master['name']}</b>\n"]
        lines.extend(_avail_row_text(r) for r in rows)
        text = "\n".join(lines)
        kb = _list_kb(rows, master_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Блокировка удалена.")
