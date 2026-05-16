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
from aria.config import settings as _settings
from aria.filters import SetupDone
from aria.handlers.menu import ADMIN_KB, _is_admin_bot
from aria.handlers.quick import MAIN_KB
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

    if _is_admin_bot(tenant, message.from_user.id):
        await message.answer(
            "👑 <b>Aria — панель управления</b>\n\n"
            "Управляй ботами через кнопки ниже или команды:\n"
            "• /list_bots — список активных ботов\n"
            "• /add_bot — добавить новый бот\n"
            "• /broadcast &lt;текст&gt; — рассылка всем владельцам\n"
            "• /set_vip &lt;tid&gt; &lt;uid&gt; [дней] — назначить VIP",
            reply_markup=ADMIN_KB,
        )
    else:
        await message.answer(
            f"Привет, {tenant.owner_name}! Я Aria — твой ресепшн для <b>{tenant.salon_name}</b>.\n\n"
            "Используй кнопки внизу или просто пиши:\n"
            "• «что у меня сегодня?»\n"
            "• «запиши Катю на ресницы 20 мая в 14:00»\n"
            "• «что на этой неделе?»\n\n"
            "/help — список примеров",
            reply_markup=MAIN_KB,
        )


@router.message(Command("reset"))
async def cmd_reset(message: Message, tenant: TenantConfig) -> None:
    await repo.clear_history(tenant.id, message.from_user.id)
    await message.answer("История очищена. Начнём заново — чем могу помочь?")


@router.message(Command("help"))
async def cmd_help(message: Message, tenant: TenantConfig) -> None:
    owner_hint = (
        "\n/status — статус бота, GCal и почты"
        "\n/connect_email — email-уведомления"
        "\n/set_cal — изменить ID календаря"
        "\n/set_tz — изменить часовой пояс"
    ) if tenant.is_owner(message.from_user.id) else ""
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
async def cmd_status(message: Message, tenant: TenantConfig, caller_id: int | None = None) -> None:
    if not tenant.is_owner(caller_id if caller_id is not None else message.from_user.id):
        return

    import html as _html
    from aria.config import settings
    import aria.db.repo as repo

    # ── Google Calendar ───────────────────────────────────────────────────
    creds = settings.GOOGLE_CALENDAR_CREDENTIALS
    svc_email = None
    if creds:
        try:
            svc_email = _json.loads(creds).get("client_email")
        except Exception:
            pass

    tz_val = tenant.timezone or "UTC"

    if creds and tenant.google_cal_id:
        gcal_status = f"✅ Подключён\nID: <code>{tenant.google_cal_id}</code>"
    elif tenant.google_cal_id:
        gcal_status = "⚠️ ID задан, нет credentials"
    else:
        gcal_status = "❌ Не подключён"

    svc_line = f"\n<code>{svc_email}</code>" if svc_email else ""

    # ── Email ─────────────────────────────────────────────────────────────
    row = await repo.get_tenant(tenant.id)
    email_user   = (row.get("email_user")        or "") if row else ""
    email_host   = (row.get("email_host")        or "") if row else ""
    filter_type  = (row.get("email_filter_type") or "all") if row else "all"
    filter_value = (row.get("email_filter_value") or "") if row else ""

    if email_user and email_host:
        filter_desc = {
            "all":      "все письма",
            "keywords": f"по словам: {filter_value}",
            "senders":  f"от: {filter_value}",
        }.get(filter_type, filter_type)
        email_status = (
            f"✅ Подключена\n"
            f"<code>{_html.escape(email_user)}</code>\n"
            f"Фильтр: {_html.escape(filter_desc)}"
        )
    else:
        email_status = "❌ Не подключена  /connect_email"

    await message.answer(
        f"<b>Статус бота</b>\n\n"
        f"Салон: <b>{_html.escape(tenant.salon_name)}</b>\n"
        f"Часовой пояс: <code>{tz_val}</code>\n\n"
        f"📅 <b>Google Calendar:</b>\n{gcal_status}{svc_line}\n\n"
        f"📧 <b>Email-уведомления:</b>\n{email_status}\n\n"
        "Команды:\n"
        "/set_cal — изменить ID календаря\n"
        "/set_tz — изменить часовой пояс\n"
        "/connect_email — настроить email"
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


def _extract_cal_id(text: str) -> str:
    """Extract calendar ID from a raw ID string or a Google Calendar iCal/HTML URL."""
    import re
    from urllib.parse import unquote
    # iCal URL: .../calendar/ical/ENCODED_ID/...
    m = re.search(r"/calendar/(?:ical|r)/([^/\s]+)/", text)
    if m:
        return unquote(m.group(1))
    # HTML URL: calendar.google.com/calendar/u/0?cid=ENCODED_ID
    m = re.search(r"[?&]cid=([^&\s]+)", text)
    if m:
        return unquote(m.group(1))
    return text.strip()


@router.message(OwnerSettings.waiting_cal_id)
async def process_set_cal(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    text = message.text.strip()
    if text.lower() in ("убрать", "удалить", "нет", "no", "-"):
        cal_id = None
    else:
        cal_id = _extract_cal_id(text)

    await repo.update_tenant(tenant.id, google_cal_id=cal_id)
    invalidate_adapter(tenant.id)
    TenantMiddleware.invalidate(tenant.bot_token)
    await state.clear()

    if cal_id:
        await message.answer(
            f"✅ Google Calendar обновлён: <code>{cal_id}</code>\n\n"
            "Попробуй добавить запись — если бот скажет «поделись календарём», "
            "значит нужно ещё добавить доступ сервисному аккаунту."
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


@router.message(Command("test_cal"), SetupDone())
async def cmd_test_cal(message: Message, tenant: TenantConfig, caller_id: int | None = None) -> None:
    if not tenant.is_owner(caller_id if caller_id is not None else message.from_user.id):
        return

    import json as _j
    from aria.config import settings
    from aria.services.booking import GoogleAdapter, _adapters, get_adapter

    lines: list[str] = ["<b>🔍 Диагностика Google Calendar</b>\n"]

    # 1. Calendar ID in DB
    cal_id = tenant.google_cal_id
    lines.append(f"google_cal_id: <code>{cal_id or '❌ НЕ ЗАДАН'}</code>")

    # 2. Credentials
    creds_json = tenant.google_cal_credentials or settings.GOOGLE_CALENDAR_CREDENTIALS
    if creds_json:
        try:
            svc_email = _j.loads(creds_json).get("client_email", "?")
            lines.append(f"Сервисный аккаунт: <code>{svc_email}</code>")
        except Exception as exc:
            lines.append(f"❌ Credentials невалидны: {exc}")
            creds_json = None
    else:
        lines.append("❌ GOOGLE_CALENDAR_CREDENTIALS не задан в Railway Variables!")

    if not cal_id:
        lines.append("\n💡 Используй /set_cal и введи свой Gmail-адрес")
        await message.answer("\n".join(lines))
        return

    if not creds_json:
        await message.answer("\n".join(lines))
        return

    # 3. Which adapter is actually cached?
    cached = _adapters.get(tenant.id)
    if cached is None:
        lines.append("\nАдаптер: ещё не создан (будет при первом запросе)")
        get_adapter(tenant)
        cached = _adapters.get(tenant.id)

    adapter_name = "✅ GoogleAdapter" if isinstance(cached, GoogleAdapter) else "⚠️ LocalAdapter (GCal не используется)"
    lines.append(f"Адаптер: {adapter_name}")

    # 4. Live API test
    if isinstance(cached, GoogleAdapter):
        lines.append("\nПроверяю подключение к GCal API...")
        await message.answer("\n".join(lines))
        lines = []
        try:
            import asyncio as _aio
            from datetime import datetime, timezone as _tz, timedelta as _td
            day_start = datetime.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end   = day_start + _td(days=30)
            items = await _aio.to_thread(
                cached._list_events_sync,
                day_start.isoformat(),
                day_end.isoformat(),
            )
            lines.append(f"✅ GCal API работает! Ближайших событий: {len(items)}")
        except Exception as exc:
            err = str(exc)
            if "404" in err or "Not Found" in err:
                lines.append(
                    "❌ Ошибка 404 — календарь не найден.\n\n"
                    "Что делать:\n"
                    "1. Открой calendar.google.com\n"
                    "2. Настройки → нужный календарь → «Доступ другим людям»\n"
                    f"3. Добавь <code>{svc_email}</code> с правом «Вносить изменения»\n"
                    "4. Скопируй «Идентификатор календаря» и отправь боту /set_cal"
                )
            elif "403" in err or "disabled" in err:
                lines.append(
                    "❌ Ошибка 403 — нет доступа или API отключён.\n\n"
                    "Проверь: console.cloud.google.com → APIs → Google Calendar API → Enable"
                )
            else:
                lines.append(f"❌ Ошибка API:\n<code>{err[:300]}</code>")
    else:
        lines.append(
            "\n⚠️ Используется локальная БД, не GCal.\n"
            "Это значит или credentials невалидны, или cal_id неверный.\n"
            "Попробуй /set_cal заново."
        )

    if lines:
        await message.answer("\n".join(lines))
