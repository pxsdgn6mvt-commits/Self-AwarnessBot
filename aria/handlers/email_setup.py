"""Email notification setup — connect an IMAP inbox to Telegram."""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

import aria.db.repo as repo
from aria.filters import SetupDone
from aria.middleware import TenantMiddleware
from aria.services.email_monitor import (
    check_email, detect_imap_host, start_email_job, stop_email_job,
)
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


class EmailSetup(StatesGroup):
    address  = State()
    host     = State()
    password = State()


class EmailFilter(StatesGroup):
    value = State()   # only entered when filter_type requires a text value


# ── Booking service presets ───────────────────────────────────────────────────

# (display name, sender domain/pattern used for matching)
_BOOKING_SERVICES: list[tuple[str, str]] = [
    ("Yclients",       "yclients.com"),
    ("Dikidi",         "dikidi.net"),
    ("Booksy",         "booksy.com"),
    ("Fresha",         "fresha.com"),
    ("SimplyBook.me",  "simplybook.me"),
    ("Reservio",       "reservio.com"),
    ("Treatwell",      "treatwell.com"),
    ("Sber (СберБизнес)", "sber.ru"),
]

_DOMAIN_TO_SERVICE: dict[str, str] = {domain: name for name, domain in _BOOKING_SERVICES}


def _service_select_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"email_svc:{domain}")]
        for name, domain in _BOOKING_SERVICES
    ]
    rows.append([InlineKeyboardButton(text="✏️ Другой сервис", callback_data="email_svc:custom")])
    rows.append([InlineKeyboardButton(text="❌ Отмена",         callback_data="email_filter:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Filter helpers ────────────────────────────────────────────────────────────

_FILTER_LABELS = {
    "all":      "📬 Все письма",
    "keywords": "🔍 По ключевым словам",
    "senders":  "👤 По отправителям",
}


def _filter_label(filter_type: str, filter_value: str | None) -> str:
    if filter_type == "all" or not filter_value:
        return "📬 Все письма"
    # Check if the value is a known booking service domain
    if filter_type == "senders":
        service_name = _DOMAIN_TO_SERVICE.get(filter_value.strip())
        if service_name:
            return f"🗓 {service_name}"
    base = _FILTER_LABELS.get(filter_type, "📬 Все письма")
    short = filter_value[:28] + ("…" if len(filter_value) > 28 else "")
    return f"{base}: {short}"


def _filter_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📬 Все новые письма",           callback_data="email_filter:all")],
        [InlineKeyboardButton(text="🔍 По ключевым словам в теме",  callback_data="email_filter:keywords")],
        [InlineKeyboardButton(text="👤 От конкретных отправителей", callback_data="email_filter:senders")],
        [InlineKeyboardButton(text="🗓 Конкретный сервис бронирования", callback_data="email_filter:service")],
        [InlineKeyboardButton(text="❌ Отмена",                     callback_data="email_filter:cancel")],
    ])


# ── Status display ────────────────────────────────────────────────────────────

def _email_menu_kb(connected: bool, filter_type: str = "all", filter_value: str | None = None) -> InlineKeyboardMarkup:
    if connected:
        flabel = _filter_label(filter_type, filter_value)
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить сейчас", callback_data="email:check"),
                InlineKeyboardButton(text="✏️ Изменить",          callback_data="email:setup"),
            ],
            [InlineKeyboardButton(text=f"⚙️ Фильтр: {flabel}", callback_data="email:filter")],
            [InlineKeyboardButton(text="🔴 Отключить",           callback_data="email:disconnect")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Подключить почту", callback_data="email:setup")]
    ])


async def _show_email_status(target: Message, tenant: TenantConfig) -> None:
    row = await repo.get_tenant(tenant.id)
    user         = (row.get("email_user")         or "") if row else ""
    srv          = (row.get("email_host")          or "") if row else ""
    filter_type  = (row.get("email_filter_type")   or "all") if row else "all"
    filter_value = (row.get("email_filter_value")  or None) if row else None

    connected = bool(user and srv)
    if connected:
        flabel = _filter_label(filter_type, filter_value)
        text = (
            "📧 <b>Email-уведомления</b>\n\n"
            f"✅ Подключено\n"
            f"Адрес: <code>{html.escape(user)}</code>\n"
            f"Сервер: <code>{html.escape(srv)}</code>\n"
            f"Фильтр: {flabel}\n\n"
            "Новые письма приходят сюда каждые 5 минут."
        )
    else:
        text = (
            "📧 <b>Email-уведомления</b>\n\n"
            "❌ Не подключено\n\n"
            "Подключи почту — и нужные письма будут приходить прямо в этот чат."
        )
    await target.answer(text, reply_markup=_email_menu_kb(connected, filter_type, filter_value))


# ── Entry points ──────────────────────────────────────────────────────────────

@router.message(F.text == "📧 Почта", SetupDone())
async def quick_email(message: Message, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return
    await _show_email_status(message, tenant)


@router.message(Command("connect_email"), SetupDone())
async def cmd_connect_email(message: Message, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return
    await _show_email_status(message, tenant)


# ── Inline button callbacks ───────────────────────────────────────────────────

@router.callback_query(F.data == "email:check", SetupDone())
async def cb_check(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer("Проверяю...")
    try:
        count = await check_email(tenant.id, callback.bot)
    except Exception as exc:
        err = str(exc)
        tip = ""
        row = await repo.get_tenant(tenant.id)
        addr = (row.get("email_user") or "") if row else ""
        domain = addr.split("@")[-1].lower() if addr else ""
        if "gmail" in domain:
            tip = "\n\n⚠️ Gmail требует App Password:\nmyaccount.google.com → Безопасность → Пароли приложений"
        elif "yandex" in domain or "ya.ru" in domain:
            tip = "\n\n⚠️ Яндекс: создай пароль приложения:\npassport.yandex.ru → Безопасность"
        await callback.message.answer(
            f"❌ Ошибка подключения:\n<code>{html.escape(err[:300])}</code>{tip}\n\n"
            "Нажми «✏️ Изменить» чтобы ввести пароль заново."
        )
        return
    if count:
        await callback.message.answer(f"✅ Переслано новых писем: {count}")
    else:
        await callback.message.answer("📭 Новых писем нет (с учётом фильтра).")


@router.callback_query(F.data == "email:disconnect", SetupDone())
async def cb_disconnect(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await repo.update_tenant(
        tenant.id,
        email_host=None, email_user=None,
        email_password=None, email_last_uid=None,
        email_filter_type="all", email_filter_value=None,
    )
    TenantMiddleware.invalidate(tenant.bot_token)
    stop_email_job(tenant.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Email-уведомления отключены.")
    await callback.answer()


@router.callback_query(F.data == "email:setup", SetupDone())
async def cb_setup(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(EmailSetup.address)
    await callback.message.answer(
        "Введи адрес почты, которую хочешь подключить:\n"
        "(например <code>mysalon@gmail.com</code>)\n\n"
        "Отменить: /cancel"
    )


# ── Filter callbacks ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "email:filter", SetupDone())
async def cb_filter_menu(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.answer(
        "⚙️ <b>Фильтр писем</b>\n\n"
        "Какие письма пересылать в бот?\n\n"
        "• <b>Все новые</b> — любое новое письмо\n"
        "• <b>По ключевым словам</b> — только если тема или текст содержат нужные слова\n"
        "• <b>По отправителям</b> — только от конкретных адресов или доменов\n"
        "• <b>Сервис бронирования</b> — выбери платформу из списка, бот настроится автоматически",
        reply_markup=_filter_select_kb(),
    )


@router.callback_query(F.data == "email_filter:all", SetupDone())
async def cb_filter_all(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await repo.update_tenant(tenant.id, email_filter_type="all", email_filter_value=None)
    TenantMiddleware.invalidate(tenant.bot_token)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Фильтр: все новые письма.")
    await callback.answer()


@router.callback_query(F.data == "email_filter:keywords", SetupDone())
async def cb_filter_keywords(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(EmailFilter.value)
    await state.update_data(pending_filter_type="keywords")
    row = await repo.get_tenant(tenant.id)
    current = (row.get("email_filter_value") or "") if row else ""
    hint = f"\n\nТекущие слова: <code>{html.escape(current)}</code>" if current else ""
    await callback.message.answer(
        f"Введи ключевые слова через запятую:{hint}\n\n"
        "Письма с этими словами в теме или тексте будут приходить в бот.\n"
        "Например: <code>запись, бронь, клиент, booking</code>"
    )


@router.callback_query(F.data == "email_filter:senders", SetupDone())
async def cb_filter_senders(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(EmailFilter.value)
    await state.update_data(pending_filter_type="senders")
    row = await repo.get_tenant(tenant.id)
    current = (row.get("email_filter_value") or "") if row else ""
    hint = f"\n\nТекущие адреса: <code>{html.escape(current)}</code>" if current else ""
    await callback.message.answer(
        f"Введи email-адреса или домены через запятую:{hint}\n\n"
        "Письма только от этих отправителей будут приходить в бот.\n"
        "Например: <code>client@gmail.com, @instagram.com, noreply@booking</code>"
    )


@router.callback_query(F.data == "email_filter:service", SetupDone())
async def cb_filter_service(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🗓 <b>Сервис бронирования</b>\n\n"
        "Выбери платформу — бот будет пересылать только уведомления от неё:",
        reply_markup=_service_select_kb(),
    )


@router.callback_query(F.data.startswith("email_svc:"), SetupDone())
async def cb_service_preset(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return

    value = callback.data[len("email_svc:"):]
    await callback.message.edit_reply_markup(reply_markup=None)

    if value == "custom":
        await callback.answer()
        await state.set_state(EmailFilter.value)
        await state.update_data(pending_filter_type="senders")
        await callback.message.answer(
            "Введи домен или адрес сервиса бронирования:\n"
            "Например: <code>mybookingservice.com</code>"
        )
        return

    service_name = _DOMAIN_TO_SERVICE.get(value, value)
    await repo.update_tenant(tenant.id, email_filter_type="senders", email_filter_value=value)
    TenantMiddleware.invalidate(tenant.bot_token)
    await callback.answer(f"✓ {service_name}")
    await callback.message.answer(
        f"✅ Фильтр: уведомления от <b>{service_name}</b>\n\n"
        f"Домен: <code>{html.escape(value)}</code>\n\n"
        "Бот будет пересылать только письма от этого сервиса."
    )


@router.callback_query(F.data == "email_filter:cancel")
async def cb_filter_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отменено.")


@router.message(EmailFilter.value)
async def step_filter_value(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    filter_type = data.get("pending_filter_type", "keywords")
    value = message.text.strip()
    await repo.update_tenant(tenant.id, email_filter_type=filter_type, email_filter_value=value)
    TenantMiddleware.invalidate(tenant.bot_token)
    await state.clear()

    label = _FILTER_LABELS.get(filter_type, filter_type)
    await message.answer(
        f"✅ Фильтр сохранён!\n\n"
        f"{label}: <code>{html.escape(value)}</code>"
    )


# ── Setup FSM steps ───────────────────────────────────────────────────────────

@router.message(EmailSetup.address)
async def step_address(message: Message, state: FSMContext) -> None:
    addr = message.text.strip()
    if "@" not in addr or "." not in addr.split("@")[-1]:
        await message.answer("Не похоже на email-адрес. Попробуй ещё раз:")
        return

    auto_host = detect_imap_host(addr)
    await state.update_data(address=addr, host=auto_host)

    if auto_host:
        await state.set_state(EmailSetup.password)
        await message.answer(
            f"✅ Адрес: <code>{html.escape(addr)}</code>\n"
            f"IMAP-сервер: <code>{html.escape(auto_host)}</code> (определён автоматически)\n\n"
            f"{_password_hint(addr)}\n\n"
            "Введи пароль (или App Password):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✏️ Изменить сервер вручную", callback_data="email_setup:change_host")
            ]]),
        )
    else:
        await state.set_state(EmailSetup.host)
        await message.answer(
            f"✅ Адрес: <code>{html.escape(addr)}</code>\n\n"
            "Не удалось определить IMAP-сервер автоматически.\n"
            "Введи адрес IMAP-сервера (например <code>imap.example.com</code>):"
        )


def _password_hint(addr: str) -> str:
    domain = addr.split("@")[-1].lower()
    if "gmail" in domain:
        return (
            "⚠️ <b>Gmail:</b> нужен App Password, не обычный пароль.\n"
            "myaccount.google.com → Безопасность → Пароли приложений"
        )
    if "yandex" in domain or "ya.ru" in domain:
        return (
            "⚠️ <b>Яндекс:</b> включи IMAP и создай пароль приложения:\n"
            "passport.yandex.ru → Безопасность → Пароли приложений"
        )
    if any(d in domain for d in ("mail.ru", "bk.ru", "list.ru", "inbox.ru")):
        return (
            "⚠️ <b>Mail.ru:</b> включи IMAP и создай пароль приложения:\n"
            "Настройки почты → Безопасность → Пароли для внешних приложений"
        )
    return "⚠️ Используй пароль приложения если включена двухфакторная аутентификация."


@router.callback_query(F.data == "email_setup:change_host", EmailSetup.password)
async def cb_change_host(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(EmailSetup.host)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Введи IMAP-сервер вручную (например <code>imap.example.com</code>):"
    )


@router.message(EmailSetup.host)
async def step_host(message: Message, state: FSMContext) -> None:
    host = message.text.strip()
    await state.update_data(host=host)
    await state.set_state(EmailSetup.password)
    data = await state.get_data()
    await message.answer(
        f"✅ IMAP-сервер: <code>{html.escape(host)}</code>\n\n"
        f"{_password_hint(data.get('address', ''))}\n\n"
        "Введи пароль (или App Password):"
    )


@router.message(EmailSetup.password)
async def step_password(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    password = message.text.strip()
    data = await state.get_data()
    address = data["address"]
    host    = data.get("host") or ""

    try:
        await message.delete()
    except Exception:
        pass

    if not host:
        await state.clear()
        await message.answer("Ошибка: IMAP-сервер не задан. Попробуй /connect_email заново.")
        return

    await repo.update_tenant(
        tenant.id,
        email_host=host,
        email_port=993,
        email_user=address,
        email_password=password,
        email_folder="INBOX",
        email_last_uid=None,
    )
    TenantMiddleware.invalidate(tenant.bot_token)
    start_email_job(tenant.id, message.bot)
    await state.clear()

    domain = address.split("@")[-1].lower()
    extra = ""
    if "gmail" in domain:
        extra = (
            "\n\n⚠️ <b>Gmail:</b> если письма не приходят — нужен App Password:\n"
            "myaccount.google.com → Безопасность → Пароли приложений\n"
            "Нажми «✏️ Изменить» и введи App Password вместо обычного."
        )
    elif "yandex" in domain or "ya.ru" in domain:
        extra = (
            "\n\n⚠️ <b>Яндекс:</b> если письма не приходят — включи IMAP и создай пароль приложения:\n"
            "passport.yandex.ru → Безопасность → Пароли приложений"
        )

    await message.answer(
        f"✅ Почта сохранена!\n\n"
        f"<code>{html.escape(address)}</code>\n\n"
        f"Нажми <b>🔄 Проверить сейчас</b> — бот проверит подключение и покажет ошибку если что-то не так."
        f"{extra}",
        reply_markup=_email_menu_kb(True),
    )
    log.info("Tenant %d connected email %s @ %s", tenant.id, address, host)
