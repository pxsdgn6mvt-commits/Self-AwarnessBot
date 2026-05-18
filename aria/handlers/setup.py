"""
Setup wizard — runs when a new tenant bot starts for the first time.
Guides the salon owner through configuring their bot via Telegram.
"""

from __future__ import annotations

import json as _json
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

import aria.db.repo as repo
from aria.filters import SetupRequired
from aria.middleware import TenantMiddleware
from aria.services.booking import invalidate_adapter
from aria.services.commands import set_commands
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()

# ── Timezone options ──────────────────────────────────────────────────────────

_TIMEZONES = [
    ("🇷🇺 Москва, Минск (UTC+3)",       "Europe/Moscow"),
    ("🇺🇦 Киев (UTC+2/+3)",              "Europe/Kiev"),
    ("🇦🇿 Баку, Тбилиси (UTC+4)",        "Asia/Baku"),
    ("🇰🇿 Алматы, Ташкент (UTC+5)",      "Asia/Almaty"),
    ("🇬🇧 Лондон (UTC±0)",               "Europe/London"),
    ("🇩🇪 Берлин, Варшава (UTC+1/+2)",   "Europe/Berlin"),
    ("🇦🇪 Дубай (UTC+4)",                "Asia/Dubai"),
    ("🇺🇸 Нью-Йорк (UTC-5/-4)",         "America/New_York"),
]


def _tz_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"tz:{tz}")]
        for label, tz in _TIMEZONES
    ])


def _platform_gcal_email() -> str | None:
    from aria.config import settings
    creds = settings.GOOGLE_CALENDAR_CREDENTIALS
    if not creds:
        return None
    try:
        return _json.loads(creds).get("client_email")
    except Exception:
        return None


async def _ask_google_cal(message: Message) -> None:
    svc_email = _platform_gcal_email()
    if svc_email:
        await message.answer(
            "Последний шаг — Google Calendar (необязательно).\n\n"
            "Бот будет видеть и создавать записи прямо в твоём календаре.\n\n"
            "<b>3 шага:</b>\n\n"
            "1️⃣ Открой <b>calendar.google.com</b> → ⚙️ Настройки\n"
            "   → выбери нужный календарь слева\n\n"
            "2️⃣ Раздел <b>«Доступ другим людям»</b> → «Добавить людей»\n"
            f"   Введи этот email:\n<code>{svc_email}</code>\n"
            "   Права: <b>«Вносить изменения в мероприятия»</b> → Отправить\n\n"
            "3️⃣ Там же найди <b>«Идентификатор календаря»</b>\n"
            "   (выглядит как <code>xxx@group.calendar.google.com</code>\n"
            "   или твой Gmail-адрес)\n"
            "   Скопируй и пришли его сюда.\n\n"
            "Или напиши <b>пропустить</b> — расписание будет только в боте."
        )
    else:
        await message.answer(
            "Google Calendar сейчас не подключён к платформе.\n"
            "Напиши <b>пропустить</b> — расписание будет храниться в боте."
        )


# ── FSM states ────────────────────────────────────────────────────────────────

class Setup(StatesGroup):
    salon_name = State()
    owner_name = State()
    services   = State()
    hours      = State()
    timezone   = State()
    google_cal = State()


# ── Debug ─────────────────────────────────────────────────────────────────────

@router.message(Command("ping"))
async def cmd_ping(message: Message, **kwargs) -> None:
    tenant = kwargs.get("tenant")
    if tenant:
        info = f"Tenant #{tenant.id} ({tenant.salon_name}), setup_complete={tenant.setup_complete}, tz={tenant.timezone}"
    else:
        info = "tenant NOT found in data"
    await message.answer(f"pong\n{info}")


# ── Wizard steps ──────────────────────────────────────────────────────────────

@router.message(CommandStart(), SetupRequired())
async def setup_start(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    log.info("setup_start called for tenant #%d user %d", tenant.id, message.from_user.id)
    await repo.update_tenant(tenant.id, owner_tg_id=message.from_user.id)
    await state.set_state(Setup.salon_name)
    await message.answer(
        "Привет! Я Aria — твой AI ресепшн. Давай настроим бота.\n\n"
        "Шаг 1/5 — Как называется твой салон?"
    )


@router.message(Setup.salon_name)
async def setup_salon_name(message: Message, state: FSMContext) -> None:
    await state.update_data(salon_name=message.text.strip())
    await state.set_state(Setup.owner_name)
    await message.answer("Шаг 2/5 — Как тебя зовут? (имя владельца)")


@router.message(Setup.owner_name)
async def setup_owner_name(message: Message, state: FSMContext) -> None:
    await state.update_data(owner_name=message.text.strip())
    await state.set_state(Setup.services)
    await message.answer(
        "Шаг 3/5 — Какие услуги предлагаешь?\n"
        "Напиши через запятую, например:\n"
        "Наращивание ресниц, Маникюр, Стрижка"
    )


@router.message(Setup.services)
async def setup_services(message: Message, state: FSMContext) -> None:
    await state.update_data(services=message.text.strip())
    await state.set_state(Setup.hours)
    await message.answer(
        "Шаг 4/5 — Рабочие часы?\n"
        "Например: Пн-Сб 10:00-20:00"
    )


@router.message(Setup.hours)
async def setup_hours(message: Message, state: FSMContext) -> None:
    await state.update_data(hours=message.text.strip())
    await state.set_state(Setup.timezone)
    await message.answer(
        "Шаг 5/5 — В каком часовом поясе работает салон?\n\n"
        "Выбери из списка или напиши вручную (например <code>Europe/Moscow</code>):",
        reply_markup=_tz_keyboard(),
    )


@router.callback_query(Setup.timezone, F.data.startswith("tz:"))
async def setup_timezone_callback(callback: CallbackQuery, state: FSMContext) -> None:
    tz = callback.data[3:]
    await state.update_data(timezone=tz)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"✓ {tz}")
    await state.set_state(Setup.google_cal)
    await _ask_google_cal(callback.message)


@router.message(Setup.timezone)
async def setup_timezone_text(message: Message, state: FSMContext) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    tz = message.text.strip()
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, Exception):
        await message.answer(
            "Не нашёл такой часовой пояс. Выбери кнопку выше или введи "
            "IANA-имя, например <code>Europe/Moscow</code>:"
        )
        return
    await state.update_data(timezone=tz)
    await state.set_state(Setup.google_cal)
    await _ask_google_cal(message)


@router.message(Setup.google_cal)
async def setup_google_cal(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    text = message.text.strip()

    if text.lower() in ("пропустить", "skip", "-", "нет", "no"):
        google_cal_id = None
    else:
        from aria.handlers.start import _extract_cal_id
        google_cal_id = _extract_cal_id(text)

    await repo.update_tenant(
        tenant.id,
        salon_name=data["salon_name"],
        owner_name=data["owner_name"],
        services=data["services"],
        hours=data["hours"],
        timezone=data.get("timezone", "UTC"),
        google_cal_id=google_cal_id,
        setup_complete=True,
    )
    invalidate_adapter(tenant.id)
    TenantMiddleware.invalidate(tenant.bot_token)
    await state.clear()
    await set_commands(message.bot, message.from_user.id)

    from aria.handlers.quick import get_main_kb
    # Use Telegram language_code as initial lang; owner can change later in Settings
    lang = (message.from_user.language_code or "ru")[:2]
    if lang not in ("ru", "en", "fi"):
        lang = "ru"
    await repo.update_tenant(tenant.id, owner_lang=lang)
    await message.answer(
        f"✅ Готово! Бот настроен для <b>{data['salon_name']}</b>.\n\n"
        f"Используй кнопки внизу или просто пиши:\n"
        f"• «что у меня сегодня?»\n"
        f"• «запиши Катю на {data['services'].split(',')[0].strip()} 20 мая в 14:00»\n"
        f"• «что на этой неделе?»\n\n"
        "Нажми 🎛 рядом с полем ввода — там все команды.",
        reply_markup=get_main_kb(lang),
    )
    log.info("Tenant %d setup complete: %s tz=%s", tenant.id, data["salon_name"], data.get("timezone", "UTC"))
