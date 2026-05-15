"""
Admin commands — only accessible to the platform administrator.
Lets you add new salon bots, list tenants, and deactivate them.
"""

from __future__ import annotations

import logging

from aiogram import Router
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


# ── /cancel (admin state reset) ───────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")
