"""Inline menu — gives the owner access to all bot functions via button navigation."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import aria.db.repo as repo
from aria.config import settings
from aria.filters import SetupDone
from aria.services.booking import get_adapter
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📅 Сегодня",     callback_data="sched:today"),
            InlineKeyboardButton(text="📅 Завтра",      callback_data="sched:tomorrow"),
        ],
        [
            InlineKeyboardButton(text="📆 Эта неделя",  callback_data="sched:week"),
            InlineKeyboardButton(text="📆 Следующая",   callback_data="sched:next_week"),
        ],
        [
            InlineKeyboardButton(text="📋 Ближайшие",   callback_data="sched:upcoming"),
            InlineKeyboardButton(text="➕ Новая запись", callback_data="qb_start"),
        ],
        [InlineKeyboardButton(text="⚙️ Настройки",     callback_data="menu:settings")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="👑 Администрирование", callback_data="menu:admin")])
    rows.append([InlineKeyboardButton(text="✖️ Закрыть", callback_data="menu:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🕐 Часовой пояс",    callback_data="cfg:tz"),
            InlineKeyboardButton(text="📅 Google Calendar", callback_data="cfg:cal"),
        ],
        [
            InlineKeyboardButton(text="📧 Email",            callback_data="cfg:email"),
            InlineKeyboardButton(text="🔍 Тест GCal",        callback_data="cfg:test_cal"),
        ],
        [InlineKeyboardButton(text="🗑 Сбросить историю",    callback_data="cfg:reset_chat")],
        [InlineKeyboardButton(text="📊 Статус бота",         callback_data="cfg:status")],
        [InlineKeyboardButton(text="◀️ Назад",               callback_data="menu:main")],
    ])


def _admin_kb() -> InlineKeyboardMarkup:
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
        [InlineKeyboardButton(text="◀️ Назад",            callback_data="menu:main")],
    ])


# ── Week view helper ──────────────────────────────────────────────────────────

async def _show_week(message: Message, tenant: TenantConfig, offset_weeks: int = 0) -> None:
    from zoneinfo import ZoneInfo
    tz_str = tenant.timezone or "UTC"
    tz = ZoneInfo(tz_str)
    now = datetime.now(tz)
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

    week_label = "Эта неделя" if offset_weeks == 0 else "Следующая неделя"
    date_range = f"{monday_date.strftime('%-d %b')} – {sunday_date.strftime('%-d %b')}"

    if not events:
        await message.answer(f"📆 {week_label} ({date_range})\n\nЗаписей нет.")
        return

    by_day: dict[str, list] = defaultdict(list)
    for e in events:
        by_day[e.get("date", "")].append(e)

    _DAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    lines = [f"📆 <b>{week_label}</b> ({date_range})\n"]
    for i in range(7):
        d = monday_date + timedelta(days=i)
        d_iso = d.isoformat()
        day_label = f"{_DAY_RU[i]} {d.strftime('%-d %b')}"
        day_events = by_day.get(d_iso, [])
        if day_events:
            lines.append(f"\n<b>{day_label}:</b>")
            for e in day_events:
                lines.append(f"• {e['time']} — {e['client']}, {e['service']}")
        else:
            lines.append(f"\n<b>{day_label}:</b> свободно")

    await message.answer("\n".join(lines))


# ── Entry point: reply keyboard button ───────────────────────────────────────

@router.message(F.text == "📱 Меню", SetupDone())
async def cmd_menu(message: Message, tenant: TenantConfig) -> None:
    is_admin = message.from_user.id == settings.ADMIN_TELEGRAM_ID
    await message.answer("📱 <b>Меню</b>", reply_markup=_main_menu_kb(is_admin))


# ── Menu navigation ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:main", SetupDone())
async def cb_menu_main(callback: CallbackQuery, tenant: TenantConfig) -> None:
    is_admin = callback.from_user.id == settings.ADMIN_TELEGRAM_ID
    await callback.message.edit_text("📱 <b>Меню</b>", reply_markup=_main_menu_kb(is_admin))
    await callback.answer()


@router.callback_query(F.data == "menu:settings", SetupDone())
async def cb_menu_settings(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=_settings_kb())
    await callback.answer()


@router.callback_query(F.data == "menu:admin")
async def cb_menu_admin(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text("👑 <b>Администрирование</b>", reply_markup=_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "menu:close")
async def cb_menu_close(callback: CallbackQuery) -> None:
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()


# ── Schedule callbacks ────────────────────────────────────────────────────────

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

@router.callback_query(F.data == "cfg:tz", SetupDone())
async def cb_cfg_tz(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    from aria.handlers.start import OwnerSettings, _tz_kb
    await state.set_state(OwnerSettings.waiting_tz)
    await callback.message.answer(
        f"Текущий часовой пояс: <code>{tenant.timezone or 'UTC'}</code>\n\n"
        "Выбери новый или напиши IANA-имя вручную (например <code>Europe/Moscow</code>):",
        reply_markup=_tz_kb("owner_tz:"),
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:cal", SetupDone())
async def cb_cfg_cal(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    from aria.handlers.start import OwnerSettings
    creds = settings.GOOGLE_CALENDAR_CREDENTIALS
    svc_email = None
    if creds:
        try:
            svc_email = json.loads(creds).get("client_email")
        except Exception:
            pass
    svc_hint = (
        f"\n\nУбедись, что ты поделился(ась) этим календарём с сервисным аккаунтом:\n"
        f"<code>{svc_email}</code>\n(права: «Вносить изменения в мероприятия»)"
        if svc_email else ""
    )
    await state.set_state(OwnerSettings.waiting_cal_id)
    await callback.message.answer(
        "Введи ID Google Календаря.\n\n"
        "Найти: calendar.google.com → ⚙️ → нужный календарь → "
        "«Идентификатор календаря» (выглядит как <code>xxx@group.calendar.google.com</code> "
        "или твой Gmail-адрес).\n\n"
        "Напиши <b>убрать</b> чтобы отключить Google Calendar."
        + svc_hint
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:email", SetupDone())
async def cb_cfg_email(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    from aria.handlers.email_setup import _show_email_status
    await _show_email_status(callback.message, tenant)
    await callback.answer()


@router.callback_query(F.data == "cfg:test_cal", SetupDone())
async def cb_cfg_test_cal(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    from aria.handlers.start import cmd_test_cal
    await cmd_test_cal(callback.message, tenant)


@router.callback_query(F.data == "cfg:reset_chat", SetupDone())
async def cb_cfg_reset_chat(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await repo.clear_history(tenant.id, callback.from_user.id)
    await callback.answer("История очищена ✅", show_alert=True)


@router.callback_query(F.data == "cfg:status", SetupDone())
async def cb_cfg_status(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    from aria.handlers.start import cmd_status
    await cmd_status(callback.message, tenant)


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
    for t in tenants:
        status = "✅" if t["setup_complete"] else "⏳ ожидает настройки"
        cal = "📅" if t["google_cal_id"] else "💾"
        tz = t.get("timezone") or "UTC"
        owner = t["owner_tg_id"] or "—"
        lines.append(
            f"#{t['id']} <b>{t['salon_name']}</b> {cal}\n"
            f"  {status} | tz: {tz} | owner: {owner}"
        )
    await callback.message.answer("Активные боты:\n\n" + "\n\n".join(lines))
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
async def cb_adm_broadcast(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.answer(
        "Используй команду:\n<code>/broadcast текст рассылки</code>"
    )
    await callback.answer()


@router.callback_query(F.data == "adm:vip_help")
async def cb_adm_vip_help(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.answer(
        "Назначить VIP:\n"
        "<code>/set_vip &lt;tenant_id&gt; &lt;user_id&gt; [дней]</code>\n\n"
        "Пример: <code>/set_vip 1 123456789 30</code>\n"
        "Без дней — бессрочно."
    )
    await callback.answer()


@router.callback_query(F.data == "adm:revoke_help")
async def cb_adm_revoke_help(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.answer(
        "Отозвать VIP:\n"
        "<code>/revoke_vip &lt;tenant_id&gt; &lt;user_id&gt;</code>"
    )
    await callback.answer()
