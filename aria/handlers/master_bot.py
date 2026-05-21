"""Master bot handlers — /start and availability management for per-master bots."""

from __future__ import annotations

import datetime

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import aria.db.repo as repo
from aria.handlers.availability import (
    ChangeHoursFSM,
    BlockSlotFSM,
    CloseDayFSM,
    _avail_row_text,
    _confirm_kb,
    _list_kb,
    _parse_date,
    _parse_hours,
    _parse_time,
)

master_router = Router()


def _master_avail_kb(master_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Закрыть день",           callback_data=f"cfg:avail_close:{master_id}")],
        [InlineKeyboardButton(text="🕐 Изменить часы",           callback_data=f"cfg:avail_hours:{master_id}")],
        [InlineKeyboardButton(text="⛔ Заблокировать слот",      callback_data=f"cfg:avail_slot:{master_id}")],
        [InlineKeyboardButton(text="📋 Существующие блокировки", callback_data=f"cfg:avail_list:{master_id}")],
    ])


# ── /start ────────────────────────────────────────────────────────────────────

@master_router.message(Command("start"))
async def master_start(message: Message, master_id: int, master_name: str) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Моё расписание", callback_data=f"cfg:avail:{master_id}"),
    ]])
    await message.answer(
        f"Привет, <b>{master_name}</b>! 👋\n\nЗдесь вы управляете своим расписанием.",
        reply_markup=kb,
        parse_mode="HTML",
    )


# ── Main availability screen ──────────────────────────────────────────────────

@master_router.callback_query(F.data.startswith("cfg:avail:"))
async def cb_avail_main(callback: CallbackQuery, master_id: int, master_name: str) -> None:
    cb_master_id = int(callback.data.split(":")[-1])
    if cb_master_id != master_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text(
        f"📅 <b>Расписание — {master_name}</b>\n\nВыберите действие:",
        reply_markup=_master_avail_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── FSM: Close day ────────────────────────────────────────────────────────────

@master_router.callback_query(F.data.startswith("cfg:avail_close:"))
async def cb_avail_close(callback: CallbackQuery, state: FSMContext, master_id: int, tenant_id: int) -> None:
    cb_master_id = int(callback.data.split(":")[-1])
    if cb_master_id != master_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(CloseDayFSM.waiting_date)
    await state.update_data(master_id=master_id, tenant_id=tenant_id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "🔴 <b>Закрыть день</b>\n\nВведите дату (ДД.ММ.ГГГГ):",
        parse_mode="HTML",
    )
    await callback.answer()


@master_router.message(CloseDayFSM.waiting_date, F.text)
async def fsm_close_date(message: Message, state: FSMContext) -> None:
    d = _parse_date(message.text)
    if d is None:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ (например: 25.05.2026):")
        return
    if d < datetime.date.today():
        await message.answer("Дата не может быть в прошлом. Введите другую дату:")
        return
    await state.update_data(date=d.isoformat())
    await state.set_state(CloseDayFSM.confirm)
    data = await state.get_data()
    master = await repo.get_master_by_id(data["master_id"])
    await message.answer(
        f"Закрыть <b>{d.strftime('%d.%m.%Y')}</b> для <b>{master['name']}</b>?",
        reply_markup=_confirm_kb(),
        parse_mode="HTML",
    )


@master_router.callback_query(F.data == "cfg:avail_yes", StateFilter(CloseDayFSM.confirm))
async def fsm_close_confirm(callback: CallbackQuery, state: FSMContext) -> None:
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
        reply_markup=_master_avail_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── FSM: Change hours ─────────────────────────────────────────────────────────

@master_router.callback_query(F.data.startswith("cfg:avail_hours:"))
async def cb_avail_hours(callback: CallbackQuery, state: FSMContext, master_id: int, tenant_id: int) -> None:
    cb_master_id = int(callback.data.split(":")[-1])
    if cb_master_id != master_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(ChangeHoursFSM.waiting_date)
    await state.update_data(master_id=master_id, tenant_id=tenant_id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "🕐 <b>Изменить часы</b>\n\nВведите дату (ДД.ММ.ГГГГ):",
        parse_mode="HTML",
    )
    await callback.answer()


@master_router.message(ChangeHoursFSM.waiting_date, F.text)
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


@master_router.message(ChangeHoursFSM.waiting_hours, F.text)
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


@master_router.callback_query(F.data == "cfg:avail_yes", StateFilter(ChangeHoursFSM.confirm))
async def fsm_hours_confirm(callback: CallbackQuery, state: FSMContext) -> None:
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
        reply_markup=_master_avail_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── FSM: Block slot ───────────────────────────────────────────────────────────

@master_router.callback_query(F.data.startswith("cfg:avail_slot:"))
async def cb_avail_slot(callback: CallbackQuery, state: FSMContext, master_id: int, tenant_id: int) -> None:
    cb_master_id = int(callback.data.split(":")[-1])
    if cb_master_id != master_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(BlockSlotFSM.waiting_date)
    await state.update_data(master_id=master_id, tenant_id=tenant_id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "⛔ <b>Заблокировать слот</b>\n\nВведите дату (ДД.ММ.ГГГГ):",
        parse_mode="HTML",
    )
    await callback.answer()


@master_router.message(BlockSlotFSM.waiting_date, F.text)
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


@master_router.message(BlockSlotFSM.waiting_time, F.text)
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


@master_router.callback_query(F.data == "cfg:avail_yes", StateFilter(BlockSlotFSM.confirm))
async def fsm_slot_confirm(callback: CallbackQuery, state: FSMContext) -> None:
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
        reply_markup=_master_avail_kb(master_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Cancel ────────────────────────────────────────────────────────────────────

@master_router.callback_query(
    F.data == "cfg:avail_no",
    StateFilter(CloseDayFSM.confirm, ChangeHoursFSM.confirm, BlockSlotFSM.confirm),
)
async def fsm_avail_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    master_id = data.get("master_id")
    await state.clear()
    await callback.message.edit_text(
        "Отменено.",
        reply_markup=_master_avail_kb(master_id) if master_id else None,
    )
    await callback.answer()


# ── List existing blocks ──────────────────────────────────────────────────────

@master_router.callback_query(F.data.startswith("cfg:avail_list:"))
async def cb_avail_list(callback: CallbackQuery, master_id: int, master_name: str) -> None:
    cb_master_id = int(callback.data.split(":")[-1])
    if cb_master_id != master_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rows = await repo.get_availability(master_id)
    if not rows:
        text = f"📋 <b>Блокировки — {master_name}</b>\n\nНет активных блокировок."
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"cfg:avail:{master_id}")
        ]])
    else:
        lines = [f"📋 <b>Блокировки — {master_name}</b>\n"]
        lines.extend(_avail_row_text(r) for r in rows)
        text = "\n".join(lines)
        kb = _list_kb(rows, master_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ── Delete a block ────────────────────────────────────────────────────────────

@master_router.callback_query(F.data.startswith("cfg:avail_del:"))
async def cb_avail_del(callback: CallbackQuery, master_id: int, master_name: str) -> None:
    parts     = callback.data.split(":")
    avail_id  = int(parts[2])
    cb_master_id = int(parts[3])
    if cb_master_id != master_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await repo.delete_availability(avail_id)
    rows = await repo.get_availability(master_id)
    if not rows:
        text = f"📋 <b>Блокировки — {master_name}</b>\n\nНет активных блокировок."
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"cfg:avail:{master_id}")
        ]])
    else:
        lines = [f"📋 <b>Блокировки — {master_name}</b>\n"]
        lines.extend(_avail_row_text(r) for r in rows)
        text = "\n".join(lines)
        kb = _list_kb(rows, master_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Блокировка удалена.")
