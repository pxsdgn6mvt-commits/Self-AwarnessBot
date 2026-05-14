"""Handlers for /start, /help, /reset commands."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

import aria.db.repo as repo
from aria.config import settings

log = logging.getLogger(__name__)
router = Router()

_WELCOME = (
    "Hi! I'm Aria, your personal assistant at {salon}.\n\n"
    "I can help you book an appointment, reschedule, answer questions about "
    "our services, or join the waitlist if we're fully booked.\n\n"
    "Just tell me what you need."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    await repo.upsert_client(user_id)
    await repo.clear_history(user_id)
    await message.answer(_WELCOME.format(salon=settings.SALON_NAME))


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    await repo.clear_history(message.from_user.id)
    await message.answer("Fresh start — how can I help you?")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Just write me a message — no special commands needed.\n\n"
        "You can:\n"
        "• Book an appointment\n"
        "• Reschedule or cancel\n"
        "• Ask about our services\n"
        "• Join the waitlist\n\n"
        "/reset — start a new conversation"
    )
