"""Email notification setup — connect an IMAP inbox to Telegram."""

from __future__ import annotations

import asyncio
import html
import imaplib
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


# ── Status display ────────────────────────────────────────────────────────────

def _email_menu_kb(connected: bool) -> InlineKeyboardMarkup:
    if connected:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить сейчас", callback_data="email:check"),
                InlineKeyboardButton(text="✏️ Изменить",          callback_data="email:setup"),
            ],
            [InlineKeyboardButton(text="🔴 Отключить", callback_data="email:disconnect")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Подключить почту", callback_data="email:setup")]
    ])


async def _show_email_status(target: Message, tenant: TenantConfig) -> None:
    row = await repo.get_tenant(tenant.id)
    user = (row.get("email_user") or "") if row else ""
    srv  = (row.get("email_host") or "") if row else ""
    if user and srv:
        text = (
            "📧 <b>Email-уведомления</b>\n\n"
            f"✅ Подключено\n"
            f"Адрес: <code>{html.escape(user)}</code>\n"
            f"Сервер: <code>{html.escape(srv)}</code>\n\n"
            "Новые письма приходят сюда каждые 5 минут."
        )
    else:
        text = (
            "📧 <b>Email-уведомления</b>\n\n"
            "❌ Не подключено\n\n"
            "Подключи почту — и все новые письма будут приходить "
            "прямо в этот чат."
        )
    await target.answer(text, reply_markup=_email_menu_kb(bool(user and srv)))


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
    count = await check_email(tenant.id, callback.bot)
    if count:
        await callback.message.answer(f"✅ Переслано новых писем: {count}")
    else:
        await callback.message.answer("📭 Новых писем нет.")


@router.callback_query(F.data == "email:disconnect", SetupDone())
async def cb_disconnect(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer()
        return
    await repo.update_tenant(
        tenant.id,
        email_host=None, email_user=None,
        email_password=None, email_last_uid=None,
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
        "(например <code>mysalon@gmail.com</code>)"
    )


# ── FSM steps ─────────────────────────────────────────────────────────────────

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

    # Delete the password message immediately for security
    try:
        await message.delete()
    except Exception:
        pass

    if not host:
        await state.clear()
        await message.answer("Ошибка: IMAP-сервер не задан. Попробуй /connect_email заново.")
        return

    wait_msg = await message.answer("🔄 Проверяю подключение...")

    # Test IMAP login in a thread
    try:
        def _test_login():
            imap = imaplib.IMAP4_SSL(host, 993)
            imap.login(address, password)
            imap.logout()

        await asyncio.to_thread(_test_login)
    except imaplib.IMAP4.error as exc:
        await state.clear()
        await wait_msg.edit_text(
            f"❌ Ошибка входа: <code>{html.escape(str(exc))}</code>\n\n"
            "Проверь email и пароль, убедись что IMAP включён в настройках почты.\n"
            "Попробуй снова: /connect_email"
        )
        return
    except Exception as exc:
        await state.clear()
        await wait_msg.edit_text(
            f"❌ Не удалось подключиться: <code>{html.escape(str(exc)[:300])}</code>\n\n"
            "Попробуй снова: /connect_email"
        )
        return

    # Save credentials
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

    await wait_msg.edit_text(
        f"✅ Почта подключена!\n\n"
        f"<code>{html.escape(address)}</code>\n\n"
        "Новые письма будут приходить сюда каждые 5 минут.\n"
        "Первая проверка пройдёт через 5 минут — или нажми «Проверить сейчас».",
        reply_markup=_email_menu_kb(True),
    )
    log.info("Tenant %d connected email %s @ %s", tenant.id, address, host)
