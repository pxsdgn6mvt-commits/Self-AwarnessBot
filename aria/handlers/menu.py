"""Inline menu — settings panel for salon owners; admin panel for platform admin."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
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
from aria.config import settings
from aria.filters import SetupDone
from aria.handlers.quick import MAIN_KB_TEXTS, all_variants
from aria.i18n import t
from aria.services.booking import get_adapter
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


class IncomeSettings(StatesGroup):
    master_percent = State()
    tax_percent    = State()


# ── Admin reply keyboard (shown in @AriaReseptionist_Bot) ─────────────────────

ADMIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список ботов"), KeyboardButton(text="➕ Добавить бота")],
        [KeyboardButton(text="📣 Рассылка"),      KeyboardButton(text="📱 Управление")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _is_admin_bot(tenant: TenantConfig, user_id: int) -> bool:
    mgmt_token = settings.MANAGEMENT_BOT_TOKEN
    if not mgmt_token:
        return False
    return user_id == settings.ADMIN_TELEGRAM_ID and tenant.bot_token == mgmt_token


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _owner_settings_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("btn_services", lang),      callback_data="adm:services"),
            InlineKeyboardButton(text=t("btn_clients", lang),       callback_data="cfg:clients"),
        ],
        [
            InlineKeyboardButton(text=t("btn_income", lang),        callback_data="cfg:income"),
            InlineKeyboardButton(text=t("btn_reminders", lang),     callback_data="cfg:reminders"),
        ],
        [
            InlineKeyboardButton(text=t("btn_help", lang),          callback_data="cfg:help"),
            InlineKeyboardButton(text=t("btn_integrations", lang),  callback_data="cfg:integrations"),
        ],
        [InlineKeyboardButton(text=t("btn_close", lang),            callback_data="menu:close")],
    ])


def _integrations_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("btn_tz", lang),       callback_data="cfg:tz"),
            InlineKeyboardButton(text=t("btn_gcal", lang),     callback_data="cfg:cal"),
        ],
        [
            InlineKeyboardButton(text=t("btn_email", lang),    callback_data="cfg:email"),
            InlineKeyboardButton(text=t("btn_status", lang),   callback_data="cfg:status"),
        ],
        [InlineKeyboardButton(text=t("btn_reset_hist", lang),  callback_data="cfg:reset_chat")],
        [InlineKeyboardButton(text=t("btn_lang", lang),        callback_data="cfg:lang")],
        [InlineKeyboardButton(text=t("btn_back", lang),        callback_data="menu:settings")],
    ])


def _income_kb(master_pct: float | None, tax_pct: float | None, lang: str = "ru") -> InlineKeyboardMarkup:
    m_val   = f"{int(master_pct)}%" if master_pct is not None else t("master_pct_none", lang)
    t_val   = f"{int(tax_pct)}%"    if tax_pct    is not None else t("tax_none", lang)
    m_label = f"{t('master_pct_lbl', lang)}: {m_val}"
    t_label = f"{t('tax_lbl', lang)}: {t_val}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m_label, callback_data="cfg:inc_master")],
        [InlineKeyboardButton(text=t_label, callback_data="cfg:inc_tax")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu:settings")],
    ])


def _lang_kb(current_lang: str) -> InlineKeyboardMarkup:
    options = [("🇷🇺 Русский", "ru"), ("🇬🇧 English", "en"), ("🇫🇮 Suomi", "fi")]
    rows = [
        [InlineKeyboardButton(
            text=f"{'✓ ' if lc == current_lang else ''}{label}",
            callback_data=f"cfg:lang_set:{lc}",
        )]
        for label, lc in options
    ]
    rows.append([InlineKeyboardButton(
        text=t("btn_back", current_lang), callback_data="cfg:integrations"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _admin_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🕐 Часовой пояс",    callback_data="cfg:tz"),
            InlineKeyboardButton(text="📅 Google Calendar", callback_data="cfg:cal"),
        ],
        [
            InlineKeyboardButton(text="📧 Email",            callback_data="cfg:email"),
            InlineKeyboardButton(text="🔍 Тест GCal",        callback_data="cfg:test_cal"),
        ],
        [InlineKeyboardButton(text="📋 Услуги и категории",  callback_data="adm:services")],
        [InlineKeyboardButton(text="🗑 Сбросить историю",    callback_data="cfg:reset_chat")],
        [InlineKeyboardButton(text="📊 Статус бота",         callback_data="cfg:status")],
        [InlineKeyboardButton(text="◀️ Назад",               callback_data="menu:main")],
    ])


def _admin_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Список ботов",  callback_data="adm:list"),
            InlineKeyboardButton(text="➕ Добавить бота", callback_data="adm:add"),
        ],
        [InlineKeyboardButton(text="📣 Рассылка",         callback_data="adm:broadcast")],
        [
            InlineKeyboardButton(text="👑 Дать VIP",      callback_data="adm:vip_help"),
            InlineKeyboardButton(text="❌ Отозвать VIP",  callback_data="adm:revoke_help"),
        ],
        [InlineKeyboardButton(text="⚙️ Настройки",        callback_data="menu:settings")],
        [InlineKeyboardButton(text="✖️ Закрыть",          callback_data="menu:close")],
    ])


def _menu_tz_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    _TIMEZONES = [
        ("🇷🇺 Москва, Минск (UTC+3)",     "Europe/Moscow"),
        ("🇺🇦 Киев (UTC+2/+3)",            "Europe/Kiev"),
        ("🇦🇿 Баку, Тбилиси (UTC+4)",      "Asia/Baku"),
        ("🇰🇿 Алматы, Ташкент (UTC+5)",    "Asia/Almaty"),
        ("🇬🇧 Лондон (UTC±0)",             "Europe/London"),
        ("🇩🇪 Берлин, Варшава (UTC+1/+2)", "Europe/Berlin"),
        ("🇫🇮 Хельсинки (UTC+2/+3)",       "Europe/Helsinki"),
        ("🇦🇪 Дубай (UTC+4)",              "Asia/Dubai"),
        ("🇺🇸 Нью-Йорк (UTC-5/-4)",       "America/New_York"),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"menu_tz:{tz}")]
        for label, tz in _TIMEZONES
    ]
    rows.append([InlineKeyboardButton(text=t("btn_back_settings", lang), callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_week(message: Message, tenant: TenantConfig, offset_weeks: int = 0) -> None:
    from zoneinfo import ZoneInfo
    lang   = tenant.owner_lang or "ru"
    tz_str = tenant.timezone or "UTC"
    tz     = ZoneInfo(tz_str)
    now    = datetime.now(tz)
    monday = now - timedelta(days=now.weekday())
    monday = monday + timedelta(weeks=offset_weeks)
    monday_date = monday.date()
    sunday_date = monday_date + timedelta(days=6)

    dt_from = datetime(monday_date.year, monday_date.month, monday_date.day,
                       0, 0, tzinfo=tz).astimezone(timezone.utc)
    dt_to   = datetime(sunday_date.year, sunday_date.month, sunday_date.day,
                       23, 59, tzinfo=tz).astimezone(timezone.utc)

    adapter = get_adapter(tenant)
    events  = await adapter.get_events(dt_from, dt_to)

    week_label = t("this_week", lang) if offset_weeks == 0 else t("next_week", lang)
    date_range = f"{monday_date.strftime('%-d %b')} – {sunday_date.strftime('%-d %b')}"

    if not events:
        await message.answer(f"📆 {week_label} ({date_range})\n\n{t('no_bookings', lang)}")
        return

    by_day: dict[str, list] = defaultdict(list)
    for e in events:
        by_day[e.get("date", "")].append(e)

    from aria.i18n import DAY_SHORT
    day_names = DAY_SHORT.get(lang, DAY_SHORT["ru"])
    lines = [f"📆 <b>{week_label}</b> ({date_range})\n"]
    for i in range(7):
        d = monday_date + timedelta(days=i)
        day_label = f"{day_names[i]} {d.strftime('%-d %b')}"
        day_events = by_day.get(d.isoformat(), [])
        if day_events:
            lines.append(f"\n<b>{day_label}:</b>")
            for e in day_events:
                lines.append(f"• {e['time']} — {e['client']}, {e['service']}")
        else:
            lines.append(f"\n<b>{day_label}:</b> {t('free_day', lang)}")

    await message.answer("\n".join(lines), parse_mode="HTML")


def _reminders_kb(hours_before: int, summary_hour: int, lang: str = "ru") -> InlineKeyboardMarkup:
    _HOURS = [1, 2, 3, 4]
    hour_row = [
        InlineKeyboardButton(
            text=f"{'✓ ' if h == hours_before else ''}{h}{t('in_h', lang)}",
            callback_data=f"cfg:rem_h:{h}",
        )
        for h in _HOURS
    ]
    _SUMMARY_HOURS = [17, 18, 19, 20, 21, 22]
    sum_rows = [
        [
            InlineKeyboardButton(
                text=f"{'✓ ' if h == summary_hour else ''}{h}:00",
                callback_data=f"cfg:rem_s:{h}",
            )
            for h in _SUMMARY_HOURS[i:i+3]
        ]
        for i in range(0, len(_SUMMARY_HOURS), 3)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        hour_row,
        *sum_rows,
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu:settings")],
    ])


# ── Entry points: reply keyboard buttons ──────────────────────────────────────

@router.message(
    F.text.in_(all_variants("btn_settings") | {"📱 Меню"}),
    SetupDone(),
    StateFilter("*"),
)
async def cmd_menu(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.clear()
    lang = tenant.owner_lang or "ru"
    if _is_admin_bot(tenant, message.from_user.id):
        await message.answer("👑 <b>Управление платформой</b>", reply_markup=_admin_inline_kb(), parse_mode="HTML")
    else:
        await message.answer(t("settings_title", lang), reply_markup=_owner_settings_kb(lang), parse_mode="HTML")


@router.message(F.text == "📱 Управление", SetupDone())
async def cmd_admin_manage(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin_bot(tenant, message.from_user.id):
        return
    await message.answer("👑 <b>Управление платформой</b>", reply_markup=_admin_inline_kb(), parse_mode="HTML")


# ── Menu navigation ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:main", SetupDone())
async def cb_menu_main(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    if _is_admin_bot(tenant, callback.from_user.id):
        await callback.message.edit_text(
            "👑 <b>Управление платформой</b>", reply_markup=_admin_inline_kb(), parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            t("settings_title", lang), reply_markup=_owner_settings_kb(lang), parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "menu:settings", SetupDone())
async def cb_menu_settings(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    kb = _admin_settings_kb() if _is_admin_bot(tenant, callback.from_user.id) else _owner_settings_kb(lang)
    await callback.message.edit_text(t("settings_title", lang), reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "menu:close")
async def cb_menu_close(callback: CallbackQuery) -> None:
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()


# ── Schedule callbacks (accessible from inline menu for owner bots) ────────────

@router.callback_query(F.data == "sched:today", SetupDone())
async def cb_sched_today(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    from aria.handlers.quick import _show_schedule
    await _show_schedule(callback.message, tenant, 0)


@router.callback_query(F.data == "sched:tomorrow", SetupDone())
async def cb_sched_tomorrow(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    from aria.handlers.quick import _show_schedule
    await _show_schedule(callback.message, tenant, 1)


@router.callback_query(F.data == "sched:week", SetupDone())
async def cb_sched_week(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    await _show_week(callback.message, tenant, 0)


@router.callback_query(F.data == "sched:next_week", SetupDone())
async def cb_sched_next_week(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    await _show_week(callback.message, tenant, 1)


@router.callback_query(F.data == "sched:upcoming", SetupDone())
async def cb_sched_upcoming(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    from aria.handlers.quick import quick_upcoming
    await quick_upcoming(callback.message, tenant)


# ── Settings callbacks ────────────────────────────────────────────────────────

@router.callback_query(F.data == "cfg:integrations", SetupDone())
async def cb_cfg_integrations(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    await callback.message.edit_text(
        t("integrations_title", lang), reply_markup=_integrations_kb(lang), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:tz", SetupDone())
async def cb_cfg_tz(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    await callback.message.edit_text(
        f"{t('tz_title', lang)}\n\n{t('tz_current', lang)}: <code>{tenant.timezone or 'UTC'}</code>\n\n{t('tz_choose', lang)}",
        reply_markup=_menu_tz_kb(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("menu_tz:"), SetupDone())
async def cb_menu_tz_select(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    tz = callback.data[len("menu_tz:"):]
    await repo.update_tenant(tenant.id, timezone=tz)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(tenant.bot_token)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_back_settings", lang), callback_data="menu:settings")]
    ])
    await callback.message.edit_text(
        f"{t('tz_saved', lang)} <code>{tz}</code>",
        reply_markup=back_kb,
        parse_mode="HTML",
    )
    await callback.answer(f"✓ {tz}")


@router.callback_query(F.data == "cfg:cal", SetupDone())
async def cb_cfg_cal(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    from aria.handlers.start import OwnerSettings
    creds = settings.GOOGLE_CALENDAR_CREDENTIALS
    svc_email = None
    if creds:
        try:
            svc_email = json.loads(creds).get("client_email")
        except Exception as e:
            log.error("Failed to parse GOOGLE_CALENDAR_CREDENTIALS: %s", e, exc_info=True)
    svc_hint = (
        f"\n\nСервисный аккаунт:\n<code>{svc_email}</code>\n(добавь с правом «Вносить изменения»)"
        if svc_email else ""
    )
    await state.set_state(OwnerSettings.waiting_cal_id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "📅 <b>Google Календарь</b>\n\n"
        "Как найти нужный ID:\n"
        "1. Открой <a href=\"https://calendar.google.com\">calendar.google.com</a>\n"
        "2. Рядом с нужным календарём нажми <b>⋮ → Настройки</b>\n"
        "3. Прокрути вниз до раздела <b>«Интеграция календаря»</b>\n"
        "4. Скопируй строку <b>«Идентификатор календаря»</b>\n\n"
        "Он выглядит как: <code>твой@gmail.com</code> или <code>xxx@group.calendar.google.com</code>\n\n"
        "Вставь его сюда 👇\n"
        "_(или напиши <b>убрать</b> чтобы отключить)_"
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:email", SetupDone())
async def cb_cfg_email(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    from aria.handlers.email_setup import _show_email_status
    await _show_email_status(callback.message, tenant)
    await callback.answer()


@router.callback_query(F.data == "cfg:test_cal", SetupDone())
async def cb_cfg_test_cal(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    from aria.handlers.start import cmd_test_cal
    await cmd_test_cal(callback.message, tenant, caller_id=callback.from_user.id)


@router.callback_query(F.data == "cfg:reset_chat", SetupDone())
async def cb_cfg_reset_chat(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    await repo.clear_history(tenant.id, callback.from_user.id)
    await callback.answer(t("history_cleared", lang), show_alert=True)


@router.callback_query(F.data == "cfg:status", SetupDone())
async def cb_cfg_status(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    from aria.handlers.start import cmd_status
    await cmd_status(callback.message, tenant, caller_id=callback.from_user.id)


# ── Language picker ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cfg:lang", SetupDone())
async def cb_cfg_lang(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    await callback.message.edit_text(
        t("btn_lang", lang),
        reply_markup=_lang_kb(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cfg:lang_set:"), SetupDone())
async def cb_lang_set(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    new_lang = callback.data[len("cfg:lang_set:"):]
    if new_lang not in ("ru", "en", "fi"):
        await callback.answer()
        return
    await repo.update_tenant(tenant.id, owner_lang=new_lang)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(tenant.bot_token)
    flag = {"ru": "🇷🇺", "en": "🇬🇧", "fi": "🇫🇮"}.get(new_lang, "")
    await callback.message.edit_text(
        f"✅ {flag}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_back_settings", new_lang), callback_data="menu:settings")]
        ]),
        parse_mode="HTML",
    )
    await callback.answer(f"✓ {flag}")


# ── Clients panel ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cfg:clients", SetupDone())
async def cb_clients_list(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    await callback.answer()
    clients = await repo.get_client_stats(tenant.id)
    if not clients:
        await callback.message.edit_text(
            t("clients_empty", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="menu:main")],
            ]),
            parse_mode="HTML",
        )
        return
    rows = []
    for c in clients[:20]:
        last = c["last_visit"].strftime("%-d %b") if c["last_visit"] else "—"
        status = repo.client_status_emoji(int(c["visits"]), int(c["no_show_count"]), int(c["cancelled_count"]))
        label = f"{status} {c['client_name']}  ({c['visits']} {t('visits_short', lang)}·{last})"
        import urllib.parse
        safe = urllib.parse.quote(c["client_name"])
        rows.append([InlineKeyboardButton(text=label, callback_data=f"cfg:client:{safe}")])
    rows.append([InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="menu:main")])
    await callback.message.edit_text(
        f"👤 <b>{t('btn_clients', lang).split(' ', 1)[-1]}</b> — {len(clients)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cfg:client:"), SetupDone())
async def cb_client_card(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    import urllib.parse
    lang = tenant.owner_lang or "ru"
    client_name = urllib.parse.unquote(callback.data.split("cfg:client:")[1])
    bookings = await repo.get_client_bookings(tenant.id, client_name)
    await callback.answer()
    if not bookings:
        await callback.answer(t("not_found", lang), show_alert=True)
        return

    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    visits          = sum(1 for b in bookings if b["status"] in ("confirmed", "pending", "completed"))
    paid_count      = sum(1 for b in bookings if b.get("paid"))
    no_show_count   = sum(1 for b in bookings if b["status"] == "no_show")
    cancelled_count = sum(1 for b in bookings if b["status"] == "cancelled")
    last = bookings[0]["scheduled_at"].astimezone(tz).strftime("%-d %B %Y")
    services: dict[str, int] = {}
    for b in bookings:
        if b["status"] in ("confirmed", "pending", "completed"):
            svc = b["service"]
            services[svc] = services.get(svc, 0) + 1
    top_services = sorted(services.items(), key=lambda x: x[1], reverse=True)[:3]
    notes_list = [b["notes"] for b in bookings if b.get("notes")]

    status = repo.client_status_emoji(visits, no_show_count, cancelled_count)
    lines = [f"👤 <b>{client_name}</b> {status}\n"]
    lines.append(f"{t('client_visits', lang)}: {visits}")
    lines.append(f"{t('client_last', lang)}: {last}")
    lines.append(f"{t('client_paid', lang)}: {paid_count} {t('client_of', lang)} {visits}")
    if no_show_count:
        lines.append(f"{t('client_noshows', lang)}: {no_show_count}")
    if cancelled_count:
        lines.append(f"{t('client_cancels', lang)}: {cancelled_count}")
    if top_services:
        svc_str = ", ".join(f"{s} ({n})" for s, n in top_services)
        lines.append(f"{t('client_services', lang)}: {svc_str}")
    if notes_list:
        lines.append(f"\n{t('client_notes', lang)}: {notes_list[-1]}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_back_clients", lang), callback_data="cfg:clients")],
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cfg:help", SetupDone())
async def cb_cfg_help(callback: CallbackQuery, tenant: TenantConfig) -> None:
    lang = tenant.owner_lang or "ru"
    await callback.answer()
    await callback.message.edit_text(
        t("help_text", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="menu:main")],
        ]),
        parse_mode="HTML",
    )


# ── Admin callbacks ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:list")
async def cb_adm_list(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    tenants = await repo.list_active_tenants()
    if not tenants:
        await callback.answer("Нет активных ботов.", show_alert=True)
        return
    lines = []
    for tn in tenants:
        status = "✅" if tn["setup_complete"] else "⏳ ожидает настройки"
        cal = "📅" if tn["google_cal_id"] else "💾"
        tz = tn.get("timezone") or "UTC"
        owner = tn["owner_tg_id"] or "—"
        lines.append(
            f"#{tn['id']} <b>{tn['salon_name']}</b> {cal}\n"
            f"  {status} | tz: {tz} | owner: {owner}"
        )
    await callback.message.answer("Активные боты:\n\n" + "\n\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm:add")
async def cb_adm_add(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    from aria.handlers.admin import AddBot
    await state.set_state(AddBot.waiting_token)
    await callback.message.answer(
        "Пришли токен нового бота (получить у @BotFather).\n\n"
        "После добавления владелец салона откроет бот и пройдёт настройку за 1 минуту."
    )
    await callback.answer()


@router.callback_query(F.data == "adm:broadcast")
async def cb_adm_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    from aria.handlers.admin import AdminBroadcast
    await state.set_state(AdminBroadcast.waiting_text)
    await callback.message.answer("Введи текст рассылки. /cancel чтобы отменить.")
    await callback.answer()


@router.callback_query(F.data == "adm:vip_help")
async def cb_adm_vip_help(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.answer(
        "Назначить VIP тенанту:\n"
        "<code>/set_vip &lt;tenant_id&gt; [дней]</code>\n\n"
        "Пример: <code>/set_vip 1 30</code>\n"
        "Без дней — бессрочно.\n\n"
        "<b>VIP включает:</b>\n"
        "• Google Calendar синхронизация\n"
        "• Автонапоминания клиентам\n"
        "• Реактивация спящих клиентов\n"
        "• Расширенный AI контекст (100 сообщений)\n"
        "• Мониторинг email",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "adm:revoke_help")
async def cb_adm_revoke_help(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.answer(
        "Отозвать VIP у тенанта:\n"
        "<code>/revoke_vip &lt;tenant_id&gt;</code>",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Income settings (master % + tax %) ───────────────────────────────────────

@router.callback_query(F.data == "cfg:income", SetupDone())
async def cb_cfg_income(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    await callback.message.edit_text(
        f"{t('income_title', lang)}\n\n{t('income_desc', lang)}",
        reply_markup=_income_kb(tenant.master_percent, tenant.tax_percent, lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:inc_master", SetupDone())
async def cb_cfg_inc_master(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    cur = f"{int(tenant.master_percent)}%" if tenant.master_percent is not None else t("master_pct_none", lang)
    await state.set_state(IncomeSettings.master_percent)
    await state.update_data(tenant_id=tenant.id, bot_token=tenant.bot_token, lang=lang)
    await callback.message.answer(
        f"{t('master_title', lang)}\n\n{t('master_current', lang)}: <b>{cur}</b>\n\n{t('master_prompt', lang)}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IncomeSettings.master_percent, Command("skip"))
async def skip_master_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await repo.update_tenant(data["tenant_id"], master_percent=None)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer(t("master_deleted", lang))


@router.message(IncomeSettings.master_percent, F.text, ~F.text.in_(MAIN_KB_TEXTS), F.text.func(lambda x: not x.startswith("/")))
async def save_master_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    text = message.text.strip().replace("%", "").replace(",", ".")
    try:
        pct = float(text)
        if not 0 < pct <= 100:
            raise ValueError
    except ValueError:
        await message.answer(t("master_bad", lang), parse_mode="HTML")
        return
    await repo.update_tenant(data["tenant_id"], master_percent=pct)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer(f"{t('master_saved', lang)} <b>{int(pct)}%</b>", parse_mode="HTML")


@router.callback_query(F.data == "cfg:inc_tax", SetupDone())
async def cb_cfg_inc_tax(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    cur = f"{int(tenant.tax_percent)}%" if tenant.tax_percent is not None else t("tax_none", lang)
    await state.set_state(IncomeSettings.tax_percent)
    await state.update_data(tenant_id=tenant.id, bot_token=tenant.bot_token, lang=lang)
    await callback.message.answer(
        f"{t('tax_title', lang)}\n\n{t('tax_current', lang)}: <b>{cur}</b>\n\n{t('tax_prompt', lang)}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IncomeSettings.tax_percent, Command("skip"))
async def skip_tax_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await repo.update_tenant(data["tenant_id"], tax_percent=None)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer(t("tax_deleted", lang))


@router.message(IncomeSettings.tax_percent, F.text, ~F.text.in_(MAIN_KB_TEXTS), F.text.func(lambda x: not x.startswith("/")))
async def save_tax_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    text = message.text.strip().replace("%", "").replace(",", ".")
    try:
        pct = float(text)
        if not 0 <= pct < 100:
            raise ValueError
    except ValueError:
        await message.answer(t("tax_bad", lang), parse_mode="HTML")
        return
    await repo.update_tenant(data["tenant_id"], tax_percent=pct)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer(f"{t('tax_saved', lang)} <b>{int(pct)}%</b>", parse_mode="HTML")


# ── Reminder settings ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "cfg:reminders", SetupDone())
async def cb_cfg_reminders(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    hours = tenant.reminder_hours_before or 2
    summary_hour = tenant.daily_summary_hour or 20
    await callback.message.edit_text(
        f"{t('reminders_title', lang)}\n\n{t('remind_before', lang)}\n\n{t('remind_summary', lang)}",
        reply_markup=_reminders_kb(hours, summary_hour, lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cfg:rem_h:"), SetupDone())
async def cb_cfg_rem_hours(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    hours = int(callback.data.split(":")[-1])
    await repo.update_tenant(tenant.id, reminder_hours_before=hours)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(tenant.bot_token)
    summary_hour = tenant.daily_summary_hour or 20
    await callback.message.edit_reply_markup(reply_markup=_reminders_kb(hours, summary_hour, lang))
    await callback.answer(f"✓ {hours}{t('in_h', lang)}")


@router.callback_query(F.data.startswith("cfg:rem_s:"), SetupDone())
async def cb_cfg_rem_summary(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer(t("no_access", tenant.owner_lang or "ru"), show_alert=True)
        return
    lang = tenant.owner_lang or "ru"
    hour = int(callback.data.split(":")[-1])
    await repo.update_tenant(tenant.id, daily_summary_hour=hour)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(tenant.bot_token)
    hours_before = tenant.reminder_hours_before or 2
    await callback.message.edit_reply_markup(reply_markup=_reminders_kb(hours_before, hour, lang))
    await callback.answer(f"✓ {hour}:00")
