"""Handlers for /start, /help, /reset, /status, /set_cal, /set_tz — only runs when setup is complete."""

from __future__ import annotations

import json as _json
import logging

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

import aria.db.repo as repo
from aria.filters import SetupDone
from aria.middleware import TenantMiddleware
from aria.services.booking import invalidate_adapter
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


# ── Owner settings FSM ────────────────────────────────────────────────────────

class OwnerSettings(StatesGroup):
    waiting_cal_id = State()
    waiting_tz     = State()


_TIMEZONES = [
    ("🇷🇺 Москва, Минск (UTC+3)",     "Europe/Moscow"),
    ("🇺🇦 Киев (UTC+2/+3)",            "Europe/Kiev"),
    ("🇦🇿 Баку, Тбилиси (UTC+4)",      "Asia/Baku"),
    ("🇰🇿 Алматы, Ташкент (UTC+5)",    "Asia/Almaty"),
    ("🇬🇧 Лондон (UTC±0)",             "Europe/London"),
    ("🇩🇪 Берлин, Варшава (UTC+1/+2)", "Europe/Berlin"),
    ("🇦🇪 Дубай (UTC+4)",              "Asia/Dubai"),
    ("🇺🇸 Нью-Йорк (UTC-5/-4)",       "America/New_York"),
]


def _tz_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"{prefix}{tz}")]
        for label, tz in _TIMEZONES
    ])


@router.message(CommandStart(), SetupDone())
async def cmd_start(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await repo.upsert_client(tenant.id, message.from_user.id,
                              message.from_user.language_code or "ru")
    await repo.clear_history(tenant.id, message.from_user.id)

    await message.answer(
        f"Привет, {tenant.owner_name}! Я Aria — твой ресепшн для <b>{tenant.salon_name}</b>.\n\n"
        "Просто пиши как обычно:\n"
        "• «что у меня сегодня?»\n"
        "• «запиши Катю на ресницы 20 мая в 14:00»\n"
        "• «что на этой неделе?»\n\n"
        "/help — список примеров"
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message, tenant: TenantConfig) -> None:
    await repo.clear_history(tenant.id, message.from_user.id)
    await message.answer("История очищена. Начнём заново — чем могу помочь?")


@router.message(Command("help"))
async def cmd_help(message: Message, tenant: TenantConfig) -> None:
    owner_hint = "\n/status — статус бота и Google Calendar\n/set_cal — изменить ID календаря\n/set_tz — изменить часовой пояс" if tenant.is_owner(message.from_user.id) else ""
    await message.answer(
        "Просто пиши мне:\n\n"
        "• «что у меня сегодня?» — расписание на сегодня\n"
        "• «что на завтра?» — расписание на завтра\n"
        "• «что на неделе с 19 по 25 мая?» — диапазон дат\n"
        "• «запиши Катю на ресницы 20 мая в 14:00» — добавить запись\n"
        "• «перенеси запись #5 на 22 мая в 11:00» — перенос\n"
        "• «отмени запись #5» — отмена\n"
        "• «свободно 20 мая в 15:00?» — проверить слот\n\n"
        f"/reset — очистить историю{owner_hint}"
    )


# ── Owner-only commands ───────────────────────────────────────────────────────

@router.message(Command("status"), SetupDone())
async def cmd_status(message: Message, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return

    from aria.config import settings
    creds = settings.GOOGLE_CALENDAR_CREDENTIALS
    svc_email = None
    if creds:
        try:
            svc_email = _json.loads(creds).get("client_email")
        except Exception:
            pass

    cal_id = tenant.google_cal_id or "—"
    tz_val = tenant.timezone or "UTC"

    if creds and tenant.google_cal_id:
        gcal_status = f"✅ Подключён\nID: <code>{tenant.google_cal_id}</code>"
    elif tenant.google_cal_id:
        gcal_status = "⚠️ ID задан, но нет credentials сервисного аккаунта"
    else:
        gcal_status = "❌ Не подключён (записи только в боте)"

    svc_line = f"\nEmail сервисного аккаунта:\n<code>{svc_email}</code>" if svc_email else ""

    await message.answer(
        f"<b>Статус бота</b>\n\n"
        f"Салон: {tenant.salon_name}\n"
        f"Часовой пояс: <code>{tz_val}</code>\n\n"
        f"Google Calendar: {gcal_status}{svc_line}\n\n"
        "Команды:\n"
        "/set_cal — изменить ID календаря\n"
        "/set_tz — изменить часовой пояс"
    )


@router.message(Command("set_cal"), SetupDone())
async def cmd_set_cal(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return

    from aria.config import settings
    creds = settings.GOOGLE_CALENDAR_CREDENTIALS
    svc_email = None
    if creds:
        try:
            svc_email = _json.loads(creds).get("client_email")
        except Exception:
            pass

    svc_hint = (
        f"\n\nУбедись, что ты поделился(ась) этим календарём с сервисным аккаунтом:\n"
        f"<code>{svc_email}</code>\n(права: «Вносить изменения в мероприятия»)"
        if svc_email else ""
    )

    await state.set_state(OwnerSettings.waiting_cal_id)
    await message.answer(
        "Введи ID Google Календаря.\n\n"
        "Найти: calendar.google.com → ⚙️ → нужный календарь → "
        "«Идентификатор календаря» (выглядит как <code>xxx@group.calendar.google.com</code> "
        "или твой Gmail-адрес).\n\n"
        "Напиши <b>убрать</b> чтобы отключить Google Calendar."
        + svc_hint
    )


@router.message(OwnerSettings.waiting_cal_id)
async def process_set_cal(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    text = message.text.strip()
    cal_id = None if text.lower() in ("убрать", "удалить", "нет", "no", "-") else text

    await repo.update_tenant(tenant.id, google_cal_id=cal_id)
    invalidate_adapter(tenant.id)
    TenantMiddleware.invalidate(tenant.bot_token)
    await state.clear()

    if cal_id:
        await message.answer(
            f"✅ Google Calendar обновлён: <code>{cal_id}</code>\n\n"
            "Попробуй добавить запись — если бот скажет «поделись календарём», "
            "значит сервисный аккаунт ещё не имеет доступа."
        )
    else:
        await message.answer("✅ Google Calendar отключён. Записи хранятся только в боте.")
    log.info("Tenant %d updated google_cal_id to %s", tenant.id, cal_id)


@router.message(Command("set_tz"), SetupDone())
async def cmd_set_tz(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return
    await state.set_state(OwnerSettings.waiting_tz)
    await message.answer(
        f"Текущий часовой пояс: <code>{tenant.timezone or 'UTC'}</code>\n\n"
        "Выбери новый или напиши IANA-имя вручную (например <code>Europe/Moscow</code>):",
        reply_markup=_tz_kb("owner_tz:"),
    )


@router.callback_query(OwnerSettings.waiting_tz, F.data.startswith("owner_tz:"))
async def cb_set_tz(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    tz = callback.data[len("owner_tz:"):]
    await _apply_tz(callback.message, state, tenant, tz)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"✓ {tz}")


@router.message(OwnerSettings.waiting_tz)
async def text_set_tz(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    tz = message.text.strip()
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, Exception):
        await message.answer("Не нашёл такой часовой пояс. Попробуй ещё раз или выбери кнопку:")
        return
    await _apply_tz(message, state, tenant, tz)


async def _apply_tz(message: Message, state: FSMContext, tenant: TenantConfig, tz: str) -> None:
    await repo.update_tenant(tenant.id, timezone=tz)
    TenantMiddleware.invalidate(tenant.bot_token)
    await state.clear()
    await message.answer(f"✅ Часовой пояс обновлён: <code>{tz}</code>")
    log.info("Tenant %d updated timezone to %s", tenant.id, tz)
