"""Catch-all message handler — routes to AI service."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from aria.services.ai import chat
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


@router.message()
async def handle_message(message: Message, bot: Bot, tenant: TenantConfig, state: FSMContext) -> None:
    if not message.text or not tenant or not tenant.setup_complete:
        return

    # If the user is mid-wizard (email setup, booking, settings…) let the FSM
    # handlers process the message. Never hand it to AI.
    try:
        current_state = await state.get_state()
    except Exception:
        current_state = None

    if current_state is not None:
        log.debug("Skipping AI handler — active FSM state: %s", current_state)
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        reply = await chat(
            user_id=message.from_user.id,
            user_text=message.text,
            bot=bot,
            tenant=tenant,
        )
    except Exception as exc:
        log.exception("AI error for tenant %d user %d: %s", tenant.id, message.from_user.id, exc)
        reply = "Что-то пошло не так. Попробуй ещё раз."

    await message.answer(reply)
