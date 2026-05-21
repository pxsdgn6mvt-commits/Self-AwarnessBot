"""Client-side booking FSM for non-owner Telegram users."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import aria.db.repo as repo
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()

_PHONE_RE = re.compile(r"^\+?[\d\s\-]{7,15}$")

_WEEKDAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_MONTH_RU = [
    "", "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]


class ClientBooking(StatesGroup):
    choosing_category = State()
    choosing_service  = State()
    choosing_date     = State()
    choosing_time     = State()
    entering_name     = State()
    entering_phone    = State()
    confirming        = State()


def _categories_kb(categories: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c["name"], callback_data=f"cb_cat:{c['id']}")]
        for c in categories
    ])


def _services_kb(items: list) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        label = item["name"]
        if item.get("price") is not None:
            label += f" — {float(item['price']):.0f}₽"
        if item.get("duration_minutes"):
            label += f" ({item['duration_minutes']} мин)"
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"cb_svc:{item['id']}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _dates_kb(tenant: TenantConfig) -> InlineKeyboardMarkup:
    working = set(tenant.working_days_list)
    today = date.today()
    buttons = []
    day = today + timedelta(days=1)
    count = 0
    while count < 7:
        if day.isoweekday() in working:
            label = f"{_WEEKDAY_RU[day.weekday()]} {day.day} {_MONTH_RU[day.month]}"
            buttons.append([InlineKeyboardButton(
                text=label,
                callback_data=f"cb_date:{day.isoformat()}",
            )])
            count += 1
        day += timedelta(days=1)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _times_kb(tenant: TenantConfig) -> InlineKeyboardMarkup:
    step = tenant.slot_minutes or 60
    total_minutes = tenant.open_hour * 60
    close_minutes = tenant.close_hour * 60
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    while total_minutes < close_minutes:
        hh, mm = divmod(total_minutes, 60)
        label = f"{hh:02d}:{mm:02d}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"cb_time:{label}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
        total_minutes += step
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.callback_query(ClientBooking.choosing_category, F.data.startswith("cb_cat:"))
async def cb_choose_category(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    category_id = int(callback.data.split(":")[1])
    items = await repo.get_items(category_id)
    if not items:
        await callback.answer("В этой категории нет доступных услуг.", show_alert=True)
        return
    items_info = {str(item["id"]): item["name"] for item in items}
    await state.update_data(category_id=category_id, items_info=items_info)
    await state.set_state(ClientBooking.choosing_service)
    await callback.message.edit_text("Выберите услугу:", reply_markup=_services_kb(items))
    await callback.answer()


@router.callback_query(ClientBooking.choosing_service, F.data.startswith("cb_svc:"))
async def cb_choose_service(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    service_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    service_name = data.get("items_info", {}).get(str(service_id), f"Услуга #{service_id}")
    await state.update_data(service_id=service_id, service_name=service_name)
    await state.set_state(ClientBooking.choosing_date)
    await callback.message.edit_text(
        f"Услуга: <b>{service_name}</b>\n\nВыберите дату:",
        reply_markup=_dates_kb(tenant),
    )
    await callback.answer()


@router.callback_query(ClientBooking.choosing_date, F.data.startswith("cb_date:"))
async def cb_choose_date(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    date_str = callback.data.split(":", 1)[1]
    await state.update_data(date_str=date_str)
    await state.set_state(ClientBooking.choosing_time)
    await callback.message.edit_text(
        f"Дата: <b>{date_str}</b>\n\nВыберите время:",
        reply_markup=_times_kb(tenant),
    )
    await callback.answer()


@router.callback_query(ClientBooking.choosing_time, F.data.startswith("cb_time:"))
async def cb_choose_time(callback: CallbackQuery, state: FSMContext) -> None:
    time_str = callback.data.split(":", 1)[1]
    await state.update_data(time_str=time_str)
    await state.set_state(ClientBooking.entering_name)
    await callback.message.edit_text(f"Время: <b>{time_str}</b>\n\nВведите ваше имя:")
    await callback.answer()


@router.message(ClientBooking.entering_name, F.text)
async def enter_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя должно содержать не менее 2 символов. Попробуйте ещё раз:")
        return
    await state.update_data(client_name=name)
    await state.set_state(ClientBooking.entering_phone)
    await message.answer(
        "Введите номер телефона или нажмите кнопку ниже:",
        reply_markup=_phone_kb(),
    )


@router.message(ClientBooking.entering_phone, F.contact)
async def enter_phone_contact(message: Message, state: FSMContext) -> None:
    await _proceed_to_confirm(message, state, message.contact.phone_number)


@router.message(ClientBooking.entering_phone, F.text)
async def enter_phone_text(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if not _PHONE_RE.match(phone):
        await message.answer(
            "Некорректный номер. Введите в формате +7XXXXXXXXXX или нажмите кнопку ниже:"
        )
        return
    await _proceed_to_confirm(message, state, phone)


async def _proceed_to_confirm(message: Message, state: FSMContext, phone: str) -> None:
    await state.update_data(client_phone=phone)
    data = await state.get_data()
    summary = (
        f"<b>Проверьте запись:</b>\n\n"
        f"💇 Услуга: {data['service_name']}\n"
        f"📅 Дата: {data['date_str']}\n"
        f"🕐 Время: {data['time_str']}\n"
        f"👤 Имя: {data['client_name']}\n"
        f"📱 Телефон: {phone}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="cb_confirm"),
        InlineKeyboardButton(text="❌ Отменить",    callback_data="cb_cancel"),
    ]])
    await state.set_state(ClientBooking.confirming)
    await message.answer(summary, reply_markup=ReplyKeyboardRemove())
    await message.answer("Всё верно?", reply_markup=kb)


@router.callback_query(ClientBooking.confirming, F.data == "cb_confirm")
async def cb_confirm(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    data = await state.get_data()
    tz = ZoneInfo(tenant.timezone or "UTC")
    h, m = map(int, data["time_str"].split(":"))
    d = date.fromisoformat(data["date_str"])
    scheduled_at = datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(timezone.utc)

    booking_id = await repo.create_booking(
        tenant_id=tenant.id,
        user_id=callback.from_user.id,
        client_name=data["client_name"],
        service=data["service_name"],
        scheduled_at=scheduled_at,
        client_phone=data.get("client_phone"),
    )

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ <b>Вы записаны!</b>\n\n"
        f"Ждём вас <b>{data['date_str']}</b> в <b>{data['time_str']}</b>.\n"
        f"Спасибо, {data['client_name']}! 🙏"
    )
    await callback.answer("Запись подтверждена!")

    if tenant.owner_tg_id:
        owner_text = (
            f"🔔 <b>Новая запись через бот</b>\n\n"
            f"👤 Клиент: {data['client_name']}\n"
            f"📱 Телефон: {data.get('client_phone') or 'не указан'}\n"
            f"💇 Услуга: {data['service_name']}\n"
            f"📅 {data['date_str']} в {data['time_str']}\n"
            f"🆔 Запись #{booking_id}"
        )
        try:
            await callback.bot.send_message(tenant.owner_tg_id, owner_text)
        except Exception:
            log.warning(
                "Failed to notify owner %d (tenant %d) about booking #%d",
                tenant.owner_tg_id, tenant.id, booking_id,
            )


@router.callback_query(ClientBooking.confirming, F.data == "cb_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Запись отменена. Напишите /start чтобы начать заново.")
    await callback.answer()
