"""
APScheduler background jobs for Aria.

  • Reminder    — fires at 09:00 local time the day before an appointment
  • No-show     — fires 2 hours after an appointment
  • Waitlist    — fires immediately when a slot opens
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

import aria.db.repo as repo

if TYPE_CHECKING:
    from aria.tenant import TenantConfig

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


# ── Helpers ───────────────────────────────────────────────────────────────────

def _local_time_str(dt: datetime, tz_str: str) -> str:
    from zoneinfo import ZoneInfo
    return dt.astimezone(ZoneInfo(tz_str or "UTC")).strftime("%H:%M")


def _local_date_str(dt: datetime, tz_str: str) -> str:
    from zoneinfo import ZoneInfo
    return dt.astimezone(ZoneInfo(tz_str or "UTC")).strftime("%-d %B")


# ── Job functions ─────────────────────────────────────────────────────────────

async def _send_reminder(booking_id: int, owner_id: int, bot: Any) -> None:
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] != "confirmed" or booking["reminder_sent"]:
        return

    tenant_row = await repo.get_tenant(booking["tenant_id"])
    tz_str = (tenant_row.get("timezone") or "UTC") if tenant_row else "UTC"

    dt = booking["scheduled_at"]
    time_str = _local_time_str(dt, tz_str)
    date_str = _local_date_str(dt, tz_str)

    text = (
        f"⏰ Напоминание: завтра, {date_str} в {time_str} — "
        f"{booking['client_name']}, {booking['service']}"
    )
    try:
        await bot.send_message(chat_id=owner_id, text=text)
        await repo.mark_reminder_sent(booking_id)
        log.info("Reminder sent for booking %d", booking_id)
    except Exception as exc:
        log.warning("Reminder failed for booking %d: %s", booking_id, exc)


async def _send_noshow_check(booking_id: int, owner_id: int, bot: Any) -> None:
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] != "confirmed" or booking["noshow_check_sent"]:
        return

    tenant_row = await repo.get_tenant(booking["tenant_id"])
    tz_str = (tenant_row.get("timezone") or "UTC") if tenant_row else "UTC"

    dt = booking["scheduled_at"]
    time_str = _local_time_str(dt, tz_str)

    text = (
        f"❓ {booking['client_name']} пришла в {time_str}? "
        f"({booking['service']})\n\n"
        "Ответь «да» или «нет» — я обновлю запись."
    )
    try:
        await bot.send_message(chat_id=owner_id, text=text)
        await repo.mark_noshow_check_sent(booking_id)
        log.info("No-show check sent for booking %d", booking_id)
    except Exception as exc:
        log.warning("No-show check failed for booking %d: %s", booking_id, exc)


async def _notify_waitlist_client(waitlist_id: int, owner_id: int, bot: Any) -> None:
    await repo.mark_waitlist_notified(waitlist_id)
    try:
        await bot.send_message(
            chat_id=owner_id,
            text="🟢 Открылось свободное окно! Проверь лист ожидания.",
        )
        log.info("Waitlist notification sent (id=%d)", waitlist_id)
    except Exception as exc:
        log.warning("Waitlist notify failed (id=%d): %s", waitlist_id, exc)


# ── Public scheduling API ─────────────────────────────────────────────────────

def schedule_reminder_job(
    booking_id: int,
    scheduled_at: datetime,
    owner_id: int,
    bot: Any,
    tenant: "TenantConfig",
) -> None:
    """Schedule a reminder for 09:00 LOCAL time the day before the appointment."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tenant.timezone or "UTC")
    # midnight local of the appointment day, then go back 1 day and set 09:00
    local_dt = scheduled_at.astimezone(tz)
    remind_at = local_dt.replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=1)
    remind_at_utc = remind_at.astimezone(timezone.utc)

    if remind_at_utc <= datetime.now(timezone.utc):
        log.debug("Reminder time already passed for booking %d — skipping", booking_id)
        return

    get_scheduler().add_job(
        _send_reminder,
        trigger=DateTrigger(run_date=remind_at_utc),
        id=f"reminder_{booking_id}",
        replace_existing=True,
        args=[booking_id, owner_id, bot],
    )
    log.info("Reminder scheduled for booking %d at %s local", booking_id, remind_at)


def schedule_noshow_job(
    booking_id: int,
    scheduled_at: datetime,
    owner_id: int,
    bot: Any,
    tenant: "TenantConfig",
) -> None:
    """Schedule a no-show check 2 hours after the appointment."""
    check_at = scheduled_at + timedelta(hours=2)
    if check_at <= datetime.now(timezone.utc):
        return

    get_scheduler().add_job(
        _send_noshow_check,
        trigger=DateTrigger(run_date=check_at),
        id=f"noshow_{booking_id}",
        replace_existing=True,
        args=[booking_id, owner_id, bot],
    )
    log.info("No-show job scheduled for booking %d at %s UTC", booking_id, check_at)


def cancel_booking_jobs(booking_id: int) -> None:
    """Remove reminder and no-show jobs when a booking is cancelled."""
    sched = get_scheduler()
    for job_id in (f"reminder_{booking_id}", f"noshow_{booking_id}"):
        try:
            sched.remove_job(job_id)
            log.info("Removed job %s", job_id)
        except Exception:
            pass  # job may not exist (already fired or never scheduled)


def schedule_waitlist_notify(waitlist_id: int, owner_id: int, bot: Any) -> None:
    """Immediately notify owner about a waitlist opening."""
    fire_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    get_scheduler().add_job(
        _notify_waitlist_client,
        trigger=DateTrigger(run_date=fire_at),
        id=f"waitlist_{waitlist_id}",
        replace_existing=True,
        args=[waitlist_id, owner_id, bot],
    )
