"""Owner notification helpers for booking events."""

from __future__ import annotations

import logging

from aiogram import Bot

log = logging.getLogger(__name__)


async def notify_owner(bot: Bot, owner_tg_id: int, booking: dict) -> None:
    """Send a Telegram message to the salon owner about a new Mini App booking."""
    lines = [
        "📅 <b>Новая запись через Mini App</b>",
        f"Клиент: {booking['client_name']}",
    ]
    if booking.get("client_phone"):
        lines.append(f"Телефон: {booking['client_phone']}")
    lines.append(f"Услуга: {booking['service']}")
    lines.append(f"Время: {booking['scheduled_at']}")

    try:
        await bot.send_message(owner_tg_id, "\n".join(lines), parse_mode="HTML")
    except Exception:
        log.exception("Failed to notify owner %d about new booking", owner_tg_id)
