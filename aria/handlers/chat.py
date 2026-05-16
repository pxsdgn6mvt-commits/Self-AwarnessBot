"""Catch-all message handler — routes to AI service."""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import aria.db.repo as repo
from aria.services.ai import chat
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()

# in-memory rate limit: user_id → timestamps of last 60 s
_rate_windows: dict[int, list[float]] = {}
_RATE_LIMIT = 20  # messages per minute


def _check_rate_limit(user_id: int) -> bool:
    now = time.monotonic()
    window = _rate_windows.setdefault(user_id, [])
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= _RATE_LIMIT:
        return False
    window.append(now)
    return True


def _detect_style(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in [" вы ", " вас ", " вам ", "пожалуйста", "будьте добры"]):
        return "formal"
    if len(text.split()) < 5:
        return "terse"
    return "casual"


@router.message()
async def handle_message(message: Message, bot: Bot, tenant: TenantConfig, state: FSMContext) -> None:
    if not message.text or not tenant or not tenant.setup_complete:
        return

    try:
        current_state = await state.get_state()
    except Exception:
        current_state = None

    if current_state is not None:
        log.info("FSM state active (%s) but no handler matched — message: %r", current_state, message.text[:40] if message.text else "")
        return

    user_id = message.from_user.id

    if not _check_rate_limit(user_id):
        await message.answer("Слишком много сообщений подряд. Подожди минуту.")
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Detect communication style and update DB in background if changed
    style = "casual"
    try:
        profile = await repo.get_client_profile(tenant.id, user_id)
        stored_style = (profile["communication_style"] if profile else None) or "casual"
        new_style = _detect_style(message.text)
        style = new_style
        if new_style != stored_style:
            asyncio.create_task(repo.update_client_style(tenant.id, user_id, new_style))
    except Exception:
        pass

    try:
        reply = await chat(
            user_id=user_id,
            user_text=message.text,
            bot=bot,
            tenant=tenant,
            style=style,
        )
    except Exception as exc:
        log.exception("AI error for tenant %d user %d: %s", tenant.id, user_id, exc)
        reply = "Что-то пошло не так. Попробуй ещё раз."

    await message.answer(reply)
