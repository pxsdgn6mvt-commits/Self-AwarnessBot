"""
Admin commands — only accessible to the platform administrator.
Lets you add new salon bots, list tenants, and deactivate them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import aria.db.repo as repo
from aria.config import settings
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_TELEGRAM_ID


class AddBot(StatesGroup):
    waiting_token = State()


class AdminBroadcast(StatesGroup):
    waiting_text = State()


# ── Keyboard button handlers (ADMIN_KB) ───────────────────────────────────────

@router.message(F.text == "📋 Список ботов")
async def kb_list_bots(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return
    tenants = await repo.list_active_tenants()
    if not tenants:
        await message.answer("Нет активных ботов.")
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
    await message.answer("Активные боты:\n\n" + "\n\n".join(lines))


@router.message(F.text == "➕ Добавить бота")
async def kb_add_bot(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AddBot.waiting_token)
    await message.answer(
        "Пришли токен нового бота (получить у @BotFather).\n\n"
        "После добавления владелец салона откроет бот и пройдёт настройку за 1 минуту."
    )


@router.message(F.text == "📣 Рассылка")
async def kb_broadcast(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminBroadcast.waiting_text)
    await message.answer("Введи текст рассылки. /cancel чтобы отменить.")


@router.message(AdminBroadcast.waiting_text)
async def process_broadcast_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    await state.clear()

    from aria import runtime
    tenants = await repo.list_active_owner_bots()
    sent = failed = 0
    for t in tenants:
        bot = runtime.bots.get(t["id"])
        if not bot:
            failed += 1
            continue
        try:
            await bot.send_message(chat_id=t["owner_tg_id"], text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:
            log.warning("Broadcast failed for tenant %d: %s", t["id"], exc)
            failed += 1

    await message.answer(f"✅ Отправлено: {sent}, ошибок: {failed}")


# ── /add_bot ──────────────────────────────────────────────────────────────────

@router.message(Command("add_bot"))
async def cmd_add_bot(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AddBot.waiting_token)
    await message.answer(
        "Пришли токен нового бота (получить у @BotFather).\n\n"
        "После добавления владелец салона откроет бот и пройдёт настройку за 1 минуту."
    )


@router.message(AddBot.waiting_token)
async def process_new_token(message: Message, state: FSMContext) -> None:
    token = message.text.strip()

    # Basic token format check
    if ":" not in token or len(token) < 30:
        await message.answer("Это не похоже на токен Telegram. Попробуй ещё раз или /cancel.")
        return

    existing = await repo.get_tenant_by_token(token)
    if existing:
        await state.clear()
        await message.answer(
            f"Этот токен уже есть в системе (салон #{existing['id']}: {existing['salon_name']})."
        )
        return

    tenant_id = await repo.create_tenant(bot_token=token, setup_complete=False)
    await state.clear()

    await message.answer(
        f"✅ Добавлен новый бот (ID #{tenant_id}).\n\n"
        f"Бот запустится в течение 60 секунд.\n"
        f"Скажи владельцу: открой бот и отправь /start — Aria проведёт настройку."
    )
    log.info("Admin added new tenant #%d", tenant_id)


# ── /list_bots ────────────────────────────────────────────────────────────────

@router.message(Command("list_bots"))
async def cmd_list_bots(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return

    tenants = await repo.list_active_tenants()
    if not tenants:
        await message.answer("Нет активных ботов.")
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

    await message.answer("Активные боты:\n\n" + "\n\n".join(lines))


# ── /reset_bot ────────────────────────────────────────────────────────────────

@router.message(Command("reset_bot"))
async def cmd_reset_bot(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /reset_bot <id>\nСбрасывает setup — владелец пройдёт настройку заново.")
        return

    tid = int(parts[1])
    t = await repo.get_tenant(tid)
    if not t:
        await message.answer(f"Бот #{tid} не найден.")
        return

    await repo.update_tenant(tid, setup_complete=False, owner_tg_id=None)
    from aria.middleware import TenantMiddleware
    from aria.services.booking import invalidate_adapter
    TenantMiddleware.invalidate(t["bot_token"])
    invalidate_adapter(tid)
    await message.answer(
        f"✅ Бот #{tid} ({t['salon_name']}) сброшен.\n"
        "Владелец снова пройдёт настройку при /start."
    )
    log.info("Admin reset setup for tenant #%d", tid)


# ── /del_bot ──────────────────────────────────────────────────────────────────

@router.message(Command("del_bot"))
async def cmd_del_bot(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /del_bot <id>")
        return

    tid = int(parts[1])
    t = await repo.get_tenant(tid)
    if not t:
        await message.answer(f"Бот #{tid} не найден.")
        return

    await repo.set_tenant_active(tid, False)
    await message.answer(f"Бот #{tid} ({t['salon_name']}) деактивирован.")
    log.info("Admin deactivated tenant #%d", tid)


# ── /cancel (clears any FSM state for any user) ───────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("Отменено.")
    else:
        await message.answer("Нечего отменять.")


# ── /broadcast ────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.answer("Использование: /broadcast <текст>")
        return

    text = parts[1]
    from aria import runtime
    tenants = await repo.list_active_owner_bots()
    sent = failed = 0
    for t in tenants:
        bot = runtime.bots.get(t["id"])
        if not bot:
            failed += 1
            continue
        try:
            await bot.send_message(chat_id=t["owner_tg_id"], text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:
            log.warning("Broadcast failed for tenant %d: %s", t["id"], exc)
            failed += 1

    await message.answer(f"✅ Отправлено: {sent}, ошибок: {failed}")


# ── /set_vip / /revoke_vip ────────────────────────────────────────────────────

@router.message(Command("set_vip"))
async def cmd_set_vip(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "Использование: /set_vip <tenant_id> <user_id> [дней]\n"
            "Пример: /set_vip 1 123456789 30"
        )
        return

    try:
        tid     = int(parts[1])
        user_id = int(parts[2])
        days    = int(parts[3]) if len(parts) > 3 else None
    except ValueError:
        await message.answer("Неверный формат. Пример: /set_vip 1 123456789 30")
        return

    vip_until = datetime.now(timezone.utc) + timedelta(days=days) if days else None
    await repo.set_client_vip(tid, user_id, True, vip_until)

    until_str = vip_until.strftime("%d.%m.%Y") if vip_until else "бессрочно"
    await message.answer(
        f"✅ VIP назначен: user {user_id} в тенанте #{tid}, действует до {until_str}"
    )
    log.info("Admin set VIP: tenant %d user %d until %s", tid, user_id, until_str)


@router.message(Command("revoke_vip"))
async def cmd_revoke_vip(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Использование: /revoke_vip <tenant_id> <user_id>")
        return

    try:
        tid     = int(parts[1])
        user_id = int(parts[2])
    except ValueError:
        await message.answer("Неверный формат.")
        return

    await repo.set_client_vip(tid, user_id, False, None)
    await message.answer(f"✅ VIP отозван: user {user_id} в тенанте #{tid}")
    log.info("Admin revoked VIP: tenant %d user %d", tid, user_id)
