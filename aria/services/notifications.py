"""Owner notification helpers — reusable across bot handlers and API layer."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


async def notify_owner(bot: Any, owner_tg_id: int, booking: dict) -> None:
    """Send new-booking notification to salon owner. Swallows all exceptions."""
    text = (
        f"🔔 <b>Новая запись через бот</b>\n\n"
        f"👤 Клиент: {booking['client_name']}\n"
        f"📱 Телефон: {booking.get('client_phone') or 'не указан'}\n"
        f"💇 Услуга: {booking['service']}\n"
        f"📅 {booking['scheduled_at']}\n"
        f"🆔 Запись #{booking['booking_id']}"
    )
    try:
        await bot.send_message(owner_tg_id, text)
    except Exception:
        log.warning(
            "Failed to notify owner %d about booking #%s",
            owner_tg_id, booking.get("booking_id"),
        )
