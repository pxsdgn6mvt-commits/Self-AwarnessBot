"""
APScheduler-based background jobs for Aria.

  • Reminder job  — fires at 9:00 UTC the day before an appointment
  • No-show job   — fires 2 hours after an appointment to check attendance
  • Waitlist job  — fired when a slot is cancelled to notify waitlist clients
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

import aria.db.repo as repo

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


# ── Job functions ─────────────────────────────────────────────────────────────

async def _send_reminder(booking_id: int, user_id: int, bot: Any) -> None:
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] != "confirmed" or booking["reminder_sent"]:
        return
    dt = booking["scheduled_at"]
    text = (
        f"Quick reminder — your {booking['service']} appointment is tomorrow "
        f"at {dt.strftime('%H:%M')} UTC. See you then!"
    )
    try:
        await bot.send_message(chat_id=user_id, text=text)
        await repo.mark_reminder_sent(booking_id)
        log.info("Reminder sent for booking %d", booking_id)
    except Exception as exc:
        log.warning("Failed to send reminder for booking %d: %s", booking_id, exc)


async def _send_noshow_check(booking_id: int, user_id: int, bot: Any) -> None:
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] != "confirmed" or booking["noshow_check_sent"]:
        return
    client_name = booking["client_name"]
    text = (
        f"We missed you today, {client_name}. Life happens — "
        "want me to find you a new slot this week?"
    )
    try:
        await bot.send_message(chat_id=user_id, text=text)
        await repo.mark_noshow_check_sent(booking_id)
        await repo.update_booking_status(booking_id, "no_show")
        log.info("No-show check sent for booking %d", booking_id)
    except Exception as exc:
        log.warning("No-show check failed for booking %d: %s", booking_id, exc)


async def _notify_waitlist_client(waitlist_id: int, user_id: int, bot: Any) -> None:
    await repo.mark_waitlist_notified(waitlist_id)
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "Good news — a slot just opened up! "
                "Reply here to book it before it's gone."
            ),
        )
        log.info("Waitlist notification sent to user %d", user_id)
    except Exception as exc:
        log.warning("Waitlist notify failed for user %d: %s", user_id, exc)


# ── Public scheduling helpers ─────────────────────────────────────────────────

def schedule_reminder_job(
    booking_id: int, scheduled_at: datetime, user_id: int, bot: Any
) -> None:
    """Schedule a reminder for 9:00 UTC the day before the appointment."""
    remind_at = (scheduled_at - timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    now = datetime.now(timezone.utc)
    if remind_at <= now:
        log.debug("Reminder time already passed for booking %d — skipping", booking_id)
        return

    get_scheduler().add_job(
        _send_reminder,
        trigger=DateTrigger(run_date=remind_at),
        id=f"reminder_{booking_id}",
        replace_existing=True,
        args=[booking_id, user_id, bot],
    )
    log.info("Reminder scheduled for booking %d at %s", booking_id, remind_at)


def schedule_noshow_job(
    booking_id: int, scheduled_at: datetime, user_id: int, bot: Any
) -> None:
    """Schedule a no-show check 2 hours after the appointment."""
    check_at = scheduled_at + timedelta(hours=2)
    now = datetime.now(timezone.utc)
    if check_at <= now:
        return

    get_scheduler().add_job(
        _send_noshow_check,
        trigger=DateTrigger(run_date=check_at),
        id=f"noshow_{booking_id}",
        replace_existing=True,
        args=[booking_id, user_id, bot],
    )
    log.info("No-show job scheduled for booking %d at %s", booking_id, check_at)


def schedule_waitlist_notify(waitlist_id: int, user_id: int, bot: Any) -> None:
    """Immediately schedule (in 1 second) a waitlist notification."""
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    get_scheduler().add_job(
        _notify_waitlist_client,
        trigger=DateTrigger(run_date=now),
        id=f"waitlist_{waitlist_id}",
        replace_existing=True,
        args=[waitlist_id, user_id, bot],
    )
