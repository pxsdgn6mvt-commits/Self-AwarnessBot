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
    """True when the admin is using the designated management bot (MANAGEMENT_BOT_TOKEN)."""
    mgmt_token = settings.MANAGEMENT_BOT_TOKEN
    if not mgmt_token:
        return False
    return user_id == settings.ADMIN_TELEGRAM_ID and tenant.bot_token == mgmt_token


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _owner_settings_kb() -> InlineKeyboardMarkup:
    """Settings panel for salon owner bots — no back button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🕐 Часовой пояс",    callback_data="cfg:tz"),
            InlineKeyboardButton(text="📅 Google Calendar", callback_data="cfg:cal"),
        ],
        [
            InlineKeyboardButton(text="📧 Email",            callback_data="cfg:email"),
            InlineKeyboardButton(text="📊 Статус",           callback_data="cfg:status"),
        ],
        [InlineKeyboardButton(text="📋 Услуги и категории",  callback_data="adm:services")],
        [InlineKeyboardButton(text="💼 Доходы мастера",      callback_data="cfg:income")],
        [InlineKeyboardButton(text="👤 Клиенты",             callback_data="cfg:clients")],
        [InlineKeyboardButton(text="🗑 Сбросить историю",    callback_data="cfg:reset_chat")],
        [InlineKeyboardButton(text="❓ Помощь",              callback_data="cfg:help")],
        [InlineKeyboardButton(text="✖️ Закрыть",             callback_data="menu:close")],
    ])


def _income_kb(master_pct: float | None, tax_pct: float | None) -> InlineKeyboardMarkup:
    m_label = f"👤 Доля мастера: {int(master_pct)}%" if master_pct is not None else "👤 Доля мастера: не задана"
    t_label = f"🧾 Налог: {int(tax_pct)}%"            if tax_pct is not None    else "🧾 Налог: не задан"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m_label, callback_data="cfg:inc_master")],
        [InlineKeyboardButton(text=t_label, callback_data="cfg:inc_tax")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:settings")],
    ])


def _admin_settings_kb() -> InlineKeyboardMarkup:
    """Settings panel for admin bot — has Back button to admin panel."""
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
    """Main admin panel for @AriaReseptionist_Bot."""
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


def _menu_tz_kb() -> InlineKeyboardMarkup:
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
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"menu_tz:{tz}")]
        for label, tz in _TIMEZONES
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)




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
        day_label = f"{_DAY_RU[i]} {d.strftime('%-d %b')}"
        day_events = by_day.get(d.isoformat(), [])
        if day_events:
            lines.append(f"\n<b>{day_label}:</b>")
            for e in day_events:
                lines.append(f"• {e['time']} — {e['client']}, {e['service']}")
        else:
            lines.append(f"\n<b>{day_label}:</b> свободно")

    await message.answer("\n".join(lines))


# ── Entry points: reply keyboard buttons ──────────────────────────────────────

@router.message(F.text.in_({"📱 Меню", "⚙️ Настройки"}), SetupDone())
async def cmd_menu(message: Message, tenant: TenantConfig) -> None:
    if _is_admin_bot(tenant, message.from_user.id):
        await message.answer("👑 <b>Управление платформой</b>", reply_markup=_admin_inline_kb())
    else:
        await message.answer("⚙️ <b>Настройки</b>", reply_markup=_owner_settings_kb())


@router.message(F.text == "📱 Управление", SetupDone())
async def cmd_admin_manage(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin_bot(tenant, message.from_user.id):
        return
    await message.answer("👑 <b>Управление платформой</b>", reply_markup=_admin_inline_kb())


# ── Menu navigation ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:main", SetupDone())
async def cb_menu_main(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if _is_admin_bot(tenant, callback.from_user.id):
        await callback.message.edit_text(
            "👑 <b>Управление платформой</b>", reply_markup=_admin_inline_kb()
        )
    else:
        await callback.message.edit_text(
            "⚙️ <b>Настройки</b>", reply_markup=_owner_settings_kb()
        )
    await callback.answer()


@router.callback_query(F.data == "menu:settings", SetupDone())
async def cb_menu_settings(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    kb = _admin_settings_kb() if _is_admin_bot(tenant, callback.from_user.id) else _owner_settings_kb()
    await callback.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=kb)
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

@router.callback_query(F.data == "cfg:tz", SetupDone())
async def cb_cfg_tz(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text(
        f"🕐 <b>Часовой пояс</b>\n\nТекущий: <code>{tenant.timezone or 'UTC'}</code>\n\nВыбери новый:",
        reply_markup=_menu_tz_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("menu_tz:"), SetupDone())
async def cb_menu_tz_select(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    tz = callback.data[len("menu_tz:"):]
    await repo.update_tenant(tenant.id, timezone=tz)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(tenant.bot_token)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к настройкам", callback_data="menu:settings")]
    ])
    await callback.message.edit_text(
        f"✅ Часовой пояс: <code>{tz}</code>",
        reply_markup=back_kb,
    )
    await callback.answer(f"✓ {tz}")


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
        f"\n\nСервисный аккаунт:\n<code>{svc_email}</code>\n(добавь с правом «Вносить изменения»)"
        if svc_email else ""
    )
    await state.set_state(OwnerSettings.waiting_cal_id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "Введи ID Google Календаря.\n\n"
        "Найти: calendar.google.com → ⚙️ → нужный календарь → «Идентификатор календаря».\n\n"
        "Напиши <b>убрать</b> чтобы отключить."
        + svc_hint
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:email", SetupDone())
async def cb_cfg_email(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
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
        await callback.answer("Нет доступа.", show_alert=True)
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
    await repo.clear_history(tenant.id, callback.from_user.id)
    await callback.answer("История очищена ✅", show_alert=True)


@router.callback_query(F.data == "cfg:status", SetupDone())
async def cb_cfg_status(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    from aria.handlers.start import cmd_status
    await cmd_status(callback.message, tenant, caller_id=callback.from_user.id)


@router.callback_query(F.data == "cfg:clients", SetupDone())
async def cb_clients_list(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    clients = await repo.get_client_stats(tenant.id)
    if not clients:
        await callback.message.edit_text(
            "👤 <b>Клиенты</b>\n\nЗаписей пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="menu:main")],
            ]),
        )
        return
    rows = []
    for c in clients[:20]:
        last = c["last_visit"].strftime("%-d %b") if c["last_visit"] else "—"
        label = f"👤 {c['client_name']}  ({c['visits']} визит·{last})"
        import urllib.parse
        safe = urllib.parse.quote(c["client_name"])
        rows.append([InlineKeyboardButton(text=label, callback_data=f"cfg:client:{safe}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="menu:main")])
    await callback.message.edit_text(
        f"👤 <b>Клиенты</b> — {len(clients)} чел.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("cfg:client:"), SetupDone())
async def cb_client_card(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    import urllib.parse
    client_name = urllib.parse.unquote(callback.data.split("cfg:client:")[1])
    bookings = await repo.get_client_bookings(tenant.id, client_name)
    await callback.answer()
    if not bookings:
        await callback.answer("Данные не найдены.", show_alert=True)
        return

    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    visits = len(bookings)
    paid_count = sum(1 for b in bookings if b.get("paid"))
    last = bookings[0]["scheduled_at"].astimezone(tz).strftime("%-d %B %Y")
    services: dict[str, int] = {}
    for b in bookings:
        svc = b["service"]
        services[svc] = services.get(svc, 0) + 1
    top_services = sorted(services.items(), key=lambda x: x[1], reverse=True)[:3]
    notes_list = [b["notes"] for b in bookings if b.get("notes")]

    lines = [f"👤 <b>{client_name}</b>\n"]
    lines.append(f"📋 Визитов: {visits}")
    lines.append(f"📅 Последний: {last}")
    lines.append(f"✅ Оплачено: {paid_count} из {visits}")
    if top_services:
        svc_str = ", ".join(f"{s} ({n})" for s, n in top_services)
        lines.append(f"💅 Услуги: {svc_str}")
    if notes_list:
        lines.append(f"\n📝 Заметки: {notes_list[-1]}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К списку", callback_data="cfg:clients")],
        ]),
    )


@router.callback_query(F.data == "cfg:help", SetupDone())
async def cb_cfg_help(callback: CallbackQuery) -> None:
    await callback.answer()
    text = (
        "❓ <b>Помощь — что умеет Aria</b>\n\n"
        "📅 <b>Сегодня / Завтра</b> — расписание на день\n"
        "➕ <b>Новая запись</b> — пошаговый мастер записи\n"
        "📋 <b>Ближайшие</b> — все записи на 14 дней вперёд\n"
        "📊 <b>Дашборд</b> — статистика за день / неделю / месяц\n"
        "⚙️ <b>Настройки</b> — услуги, часы работы, % мастера\n\n"
        "<b>Просто напиши мне:</b>\n"
        "• «запиши Катю на ресницы 20 мая в 14:00»\n"
        "• «перенеси Катю с 20 мая на 21-е в 15:00»\n"
        "• «что на этой неделе?»\n\n"
        "📧 <b>Почта</b>\n"
        "Если подключён почтовый ящик — Aria пересылает\n"
        "тебе новые письма прямо в Telegram. Удобно если\n"
        "букинг-сервис шлёт уведомления о новых записях на почту.\n"
        "Настроить: ⚙️ Настройки → 📧 Почта\n\n"
        "<b>Команды:</b> /reset · /status"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="menu:main")],
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


# ── Income settings (master % + tax %) ───────────────────────────────────────

@router.callback_query(F.data == "cfg:income", SetupDone())
async def cb_cfg_income(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text(
        "💼 <b>Доходы мастера</b>\n\n"
        "Укажи долю мастера и ставку налога — дашборд покажет чистый заработок.\n\n"
        "Нажми кнопку чтобы изменить значение:",
        reply_markup=_income_kb(tenant.master_percent, tenant.tax_percent),
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:inc_master", SetupDone())
async def cb_cfg_inc_master(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    cur = f"{int(tenant.master_percent)}%" if tenant.master_percent is not None else "не задана"
    await state.set_state(IncomeSettings.master_percent)
    await state.update_data(tenant_id=tenant.id, bot_token=tenant.bot_token)
    await callback.message.answer(
        f"👤 <b>Доля мастера</b>\n\nТекущая: <b>{cur}</b>\n\n"
        "Введи процент (например <code>70</code>) или /skip чтобы убрать.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IncomeSettings.master_percent, Command("skip"))
async def skip_master_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await repo.update_tenant(data["tenant_id"], master_percent=None)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer("✅ Доля мастера удалена.")


@router.message(IncomeSettings.master_percent, F.text.func(lambda x: not x.startswith("/")))
async def save_master_percent(message: Message, state: FSMContext) -> None:
    text = message.text.strip().replace("%", "").replace(",", ".")
    try:
        pct = float(text)
        if not 0 < pct <= 100:
            raise ValueError
    except ValueError:
        await message.answer("Введи число от 1 до 100, например <code>70</code>, или /skip:", parse_mode="HTML")
        return
    data = await state.get_data()
    await repo.update_tenant(data["tenant_id"], master_percent=pct)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer(f"✅ Доля мастера: <b>{int(pct)}%</b>", parse_mode="HTML")


@router.callback_query(F.data == "cfg:inc_tax", SetupDone())
async def cb_cfg_inc_tax(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    cur = f"{int(tenant.tax_percent)}%" if tenant.tax_percent is not None else "не задан"
    await state.set_state(IncomeSettings.tax_percent)
    await state.update_data(tenant_id=tenant.id, bot_token=tenant.bot_token)
    await callback.message.answer(
        f"🧾 <b>Налог</b>\n\nТекущий: <b>{cur}</b>\n\n"
        "Введи ставку в % (например <code>6</code> для самозанятого, <code>13</code> для НДФЛ)\n"
        "Или /skip чтобы убрать.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IncomeSettings.tax_percent, Command("skip"))
async def skip_tax_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await repo.update_tenant(data["tenant_id"], tax_percent=None)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer("✅ Налог удалён.")


@router.message(IncomeSettings.tax_percent, F.text.func(lambda x: not x.startswith("/")))
async def save_tax_percent(message: Message, state: FSMContext) -> None:
    text = message.text.strip().replace("%", "").replace(",", ".")
    try:
        pct = float(text)
        if not 0 <= pct < 100:
            raise ValueError
    except ValueError:
        await message.answer("Введи число от 0 до 99, например <code>6</code>, или /skip:", parse_mode="HTML")
        return
    data = await state.get_data()
    await repo.update_tenant(data["tenant_id"], tax_percent=pct)
    from aria.middleware import TenantMiddleware
    TenantMiddleware.invalidate(data["bot_token"])
    await state.clear()
    await message.answer(f"✅ Налог: <b>{int(pct)}%</b>", parse_mode="HTML")
