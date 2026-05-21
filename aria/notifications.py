"""Push notifications to salon owner via their tenant bot."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from aiogram.exceptions import TelegramAPIError

log = logging.getLogger(__name__)

_DATE_FMT = "%d.%m.%Y"
_TIME_FMT = "%H:%M"


def get_tenant_bot(tenant_id: int):
    """Module-level wrapper so tests can patch aria.notifications.get_tenant_bot."""
    from aria.main import get_tenant_bot as _impl
    return _impl(tenant_id)


def _fmt(dt: datetime) -> tuple[str, str]:
    return dt.strftime(_DATE_FMT), dt.strftime(_TIME_FMT)


async def notify_owner_new_booking(
    tenant_id: int,
    owner_tg_id: int,
    client_name: str,
    service_name: str,
    dt: datetime,
    client_phone: Optional[str] = None,
) -> None:
    bot = get_tenant_bot(tenant_id)
    if bot is None:
        return
    date, time = _fmt(dt)
    phone_line = f" ({client_phone})" if client_phone else ""
    text = (
        f"📅 <b>Новая запись!</b>\n"
        f"Клиент: {client_name}{phone_line}\n"
        f"Услуга: {service_name}\n"
        f"Дата: {date} в {time}"
    )
    try:
        await bot.send_message(owner_tg_id, text)
        log.info("New booking notification sent to owner tg_id=%d (tenant #%d)", owner_tg_id, tenant_id)
    except TelegramAPIError as e:
        log.warning("Failed to notify owner tg_id=%d (tenant #%d): %s", owner_tg_id, tenant_id, e)


async def notify_owner_cancelled(
    tenant_id: int,
    owner_tg_id: int,
    client_name: str,
    service_name: str,
    dt: datetime,
) -> None:
    bot = get_tenant_bot(tenant_id)
    if bot is None:
        return
    date, time = _fmt(dt)
    text = (
        f"❌ <b>Запись отменена</b>\n"
        f"Клиент: {client_name}\n"
        f"Услуга: {service_name}\n"
        f"Дата: {date} в {time}"
    )
    try:
        await bot.send_message(owner_tg_id, text)
        log.info("Cancellation notification sent to owner tg_id=%d (tenant #%d)", owner_tg_id, tenant_id)
    except TelegramAPIError as e:
        log.warning("Failed to notify owner tg_id=%d (tenant #%d): %s", owner_tg_id, tenant_id, e)


async def notify_owner_rescheduled(
    tenant_id: int,
    owner_tg_id: int,
    client_name: str,
    service_name: str,
    old_dt: datetime,
    new_dt: datetime,
) -> None:
    bot = get_tenant_bot(tenant_id)
    if bot is None:
        return
    old_date, old_time = _fmt(old_dt)
    new_date, new_time = _fmt(new_dt)
    text = (
        f"🔄 <b>Запись перенесена</b>\n"
        f"Клиент: {client_name}\n"
        f"Услуга: {service_name}\n"
        f"Было: {old_date} в {old_time}\n"
        f"Стало: {new_date} в {new_time}"
    )
    try:
        await bot.send_message(owner_tg_id, text)
        log.info("Reschedule notification sent to owner tg_id=%d (tenant #%d)", owner_tg_id, tenant_id)
    except TelegramAPIError as e:
        log.warning("Failed to notify owner tg_id=%d (tenant #%d): %s", owner_tg_id, tenant_id, e)
