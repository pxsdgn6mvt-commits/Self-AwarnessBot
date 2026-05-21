"""
APScheduler background jobs for Aria.

  • Reminder scan  — every 15 min, sends individual reminders X hours before appointment
  • Daily summary  — every hour at :00, sends tomorrow's summary at owner's chosen hour
  • No-show        — fires 2 hours after an appointment
  • Waitlist       — fires immediately when a slot opens
  • Reactivation   — daily at 10:00 UTC, notifies owners about inactive clients
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import urllib.request as _ur
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

import aria.db.repo as repo
from aria.i18n import DAY_SHORT, MON_SHORT, fmt_time_label, t as _t

if TYPE_CHECKING:
    from aria.tenant import TenantConfig

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _notify_admin(context: str, error: Exception) -> None:
    token    = os.getenv("ARIA_BOT_TOKEN", "") or os.getenv("BOT_TOKEN", "")
    admin_id = os.getenv("ARIA_OWNER_TELEGRAM_ID", "") or os.getenv("OWNER_ID", "")
    if not token or not admin_id:
        return
    text = f"🚨 Aria scheduler error in {context}:\n{type(error).__name__}: {error}"
    data = _json.dumps({"chat_id": admin_id, "text": text}).encode()
    req = _ur.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        _ur.urlopen(req, timeout=5)
    except Exception:
        pass


def _is_tenant_vip(t: dict) -> bool:
    if not t.get("is_vip"):
        return False
    vip_until = t.get("vip_until")
    if vip_until is None:
        return True
    return vip_until > datetime.now(timezone.utc)

# In-memory dedup for daily summaries: (tenant_id, local_date_str)
_summary_sent: set[tuple[int, str]] = set()


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


# ── Individual booking reminder ───────────────────────────────────────────────

async def _send_reminder(booking_id: int, owner_id: int, bot: Any) -> None:
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] not in ("confirmed", "pending") or booking["reminder_sent"]:
        return

    tenant_row = await repo.get_tenant(booking["tenant_id"])
    tz_str = (tenant_row.get("timezone") or "UTC") if tenant_row else "UTC"
    hours_before = int(tenant_row.get("reminder_hours_before") or 2) if tenant_row else 2
    lang = (tenant_row.get("owner_lang") or "ru") if tenant_row else "ru"

    dt = booking["scheduled_at"]
    time_str = _local_time_str(dt, tz_str)
    date_str = _local_date_str(dt, tz_str)

    now = datetime.now(timezone.utc)
    mins_left = int((dt - now).total_seconds() / 60)
    time_label = fmt_time_label(mins_left, hours_before, lang)

    at_word = _t("sched_in", lang)
    text = (
        f"⏰ {time_label}: <b>{booking['client_name']}</b>\n"
        f"{booking['service']} — {date_str} {at_word} {time_str}"
    )
    try:
        await bot.send_message(chat_id=owner_id, text=text, parse_mode="HTML")
        await repo.mark_reminder_sent(booking_id)
        log.info("Reminder sent for booking %d", booking_id)
    except Exception as exc:
        log.warning("Reminder failed for booking %d: %s", booking_id, exc)

    # Send reminder to client too (if they booked via Mini App and have a TG ID)
    client_tg_id = booking.get("client_tg_id")
    if client_tg_id and not booking.get("client_reminder_sent"):
        client_text = (
            f"⏰ Напоминание о записи:\n"
            f"<b>{booking['service']}</b> — {date_str} {at_word} {time_str}"
        )
        try:
            await bot.send_message(chat_id=client_tg_id, text=client_text, parse_mode="HTML")
            await repo.mark_client_reminder_sent(booking_id)
            log.info("Client reminder sent for booking %d to user %d", booking_id, client_tg_id)
        except Exception as exc:
            log.warning("Client reminder failed for booking %d: %s", booking_id, exc)


# ── Periodic reminder scan (every 15 min, handles restarts) ──────────────────

async def _run_reminder_scan(bots_getter: Callable[[], dict[int, Any]]) -> None:
    """Send reminders for bookings whose reminder window has arrived."""
    tenants = await repo.list_active_owner_bots()
    bots = bots_getter()
    for t in tenants:
        tid = t["id"]
        bot = bots.get(tid)
        if not bot:
            continue
        if not _is_tenant_vip(t):
            continue
        owner_id = t["owner_tg_id"]
        hours_before = int(t.get("reminder_hours_before") or 2)
        within_minutes = hours_before * 60 + 15
        try:
            bookings = await repo.get_pending_reminders(tid, within_minutes)
            for b in bookings:
                # Only send if reminder time (scheduled_at - hours_before) has arrived
                reminder_time = b["scheduled_at"] - timedelta(hours=hours_before)
                if reminder_time > datetime.now(timezone.utc) + timedelta(minutes=15):
                    continue
                await _send_reminder(b["id"], owner_id, bot)
        except Exception as exc:
            log.warning("Reminder scan failed for tenant %d: %s", tid, exc)
            _notify_admin(f"_run_reminder_scan tenant={tid}", exc)


# ── Daily summary ─────────────────────────────────────────────────────────────

async def _run_daily_summary(bots_getter: Callable[[], dict[int, Any]]) -> None:
    """Every hour — send tomorrow's booking summary to owners whose local hour matches."""
    from zoneinfo import ZoneInfo
    tenants = await repo.list_active_owner_bots()
    bots = bots_getter()
    for t in tenants:
        tid = t["id"]
        bot = bots.get(tid)
        if not bot:
            continue
        if not _is_tenant_vip(t):
            continue
        owner_id = t["owner_tg_id"]
        tz_str = t.get("timezone") or "UTC"
        summary_hour = int(t.get("daily_summary_hour") or 20)
        lang = t.get("owner_lang") or "ru"

        tz = ZoneInfo(tz_str)
        now_local = datetime.now(tz)
        if now_local.hour != summary_hour:
            continue

        today_key = now_local.date().isoformat()
        if (tid, today_key) in _summary_sent:
            continue
        _summary_sent.add((tid, today_key))

        try:
            bookings = await repo.get_bookings_for_tomorrow(tid, tz_str)
            if not bookings:
                await bot.send_message(
                    chat_id=owner_id,
                    text=_t("sched_no_tomorrow", lang),
                )
            else:
                tomorrow = (now_local + timedelta(days=1)).date()
                day_names = DAY_SHORT.get(lang, DAY_SHORT["ru"])
                mon_names = MON_SHORT.get(lang, MON_SHORT["ru"])
                day_hdr = f"{day_names[tomorrow.weekday()]} {tomorrow.day} {mon_names[tomorrow.month - 1]}"
                client_names = [b["client_name"] for b in bookings]
                statuses = await repo.get_client_statuses_batch(tid, client_names)
                header = _t("sched_summary_header", lang).format(day=day_hdr, n=len(bookings))
                lines = [header]
                for b in bookings:
                    t_str = _local_time_str(b["scheduled_at"], tz_str)
                    paid_mark = " ✅" if b.get("paid") else ""
                    status = statuses.get(b["client_name"].lower(), "🆕")
                    lines.append(f"• {t_str} — {status} {b['client_name']}, {b['service']}{paid_mark}")
                await bot.send_message(
                    chat_id=owner_id,
                    text="\n".join(lines),
                    parse_mode="HTML",
                )
            log.info("Daily summary sent for tenant %d", tid)
        except Exception as exc:
            log.warning("Daily summary failed for tenant %d: %s", tid, exc)


# ── No-show check ─────────────────────────────────────────────────────────────

async def _send_noshow_check(booking_id: int, owner_id: int, bot: Any) -> None:
    booking = await repo.get_booking(booking_id)
    if not booking or booking["status"] != "confirmed" or booking["noshow_check_sent"]:
        return

    tenant_row = await repo.get_tenant(booking["tenant_id"])
    tz_str = (tenant_row.get("timezone") or "UTC") if tenant_row else "UTC"
    lang = (tenant_row.get("owner_lang") or "ru") if tenant_row else "ru"

    dt = booking["scheduled_at"]
    time_str = _local_time_str(dt, tz_str)

    text = _t("sched_noshow", lang).format(
        client=booking["client_name"],
        time=time_str,
        service=booking["service"],
    )
    try:
        await bot.send_message(chat_id=owner_id, text=text)
        await repo.mark_noshow_check_sent(booking_id)
        log.info("No-show check sent for booking %d", booking_id)
    except Exception as exc:
        log.warning("No-show check failed for booking %d: %s", booking_id, exc)


# ── Waitlist ──────────────────────────────────────────────────────────────────

async def _notify_waitlist_client(waitlist_id: int, owner_id: int, bot: Any, lang: str = "ru") -> None:
    await repo.mark_waitlist_notified(waitlist_id)
    try:
        await bot.send_message(
            chat_id=owner_id,
            text=_t("sched_waitlist", lang),
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
    """Schedule a per-booking reminder X hours before appointment (VIP only)."""
    if not tenant.is_vip_active:
        return
    hours = getattr(tenant, "reminder_hours_before", 2) or 2
    remind_at_utc = scheduled_at - timedelta(hours=hours)

    if remind_at_utc <= datetime.now(timezone.utc):
        log.debug("Reminder time already passed for booking %d — scan will handle it", booking_id)
        return

    get_scheduler().add_job(
        _send_reminder,
        trigger=DateTrigger(run_date=remind_at_utc),
        id=f"reminder_{booking_id}",
        replace_existing=True,
        args=[booking_id, owner_id, bot],
    )
    log.info("Reminder scheduled for booking %d at %s UTC", booking_id, remind_at_utc)


def schedule_noshow_job(
    booking_id: int,
    scheduled_at: datetime,
    owner_id: int,
    bot: Any,
    tenant: "TenantConfig",
) -> None:
    """Schedule a no-show check 2 hours after the appointment (VIP only)."""
    if not tenant.is_vip_active:
        return
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
            pass


def schedule_waitlist_notify(waitlist_id: int, owner_id: int, bot: Any, lang: str = "ru") -> None:
    """Immediately notify owner about a waitlist opening."""
    fire_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    get_scheduler().add_job(
        _notify_waitlist_client,
        trigger=DateTrigger(run_date=fire_at),
        id=f"waitlist_{waitlist_id}",
        replace_existing=True,
        args=[waitlist_id, owner_id, bot, lang],
    )


def schedule_owner_reminders(bots_getter: Callable[[], dict[int, Any]]) -> None:
    """Register periodic reminder scan (every 15 min) and daily summary (every hour)."""
    from apscheduler.triggers.cron import CronTrigger
    get_scheduler().add_job(
        _run_reminder_scan,
        trigger=CronTrigger(minute="*/15"),
        id="reminder_scan",
        replace_existing=True,
        args=[bots_getter],
    )
    get_scheduler().add_job(
        _run_daily_summary,
        trigger=CronTrigger(minute=0),
        id="daily_summary",
        replace_existing=True,
        args=[bots_getter],
    )
    log.info("Owner reminder jobs registered (scan every 15 min, summary every hour)")


# ── Daily reactivation ────────────────────────────────────────────────────────

async def _run_reactivation(bots_getter: Callable[[], dict[int, Any]]) -> None:
    """Notify owners about salon clients who haven't visited in 45+ days."""
    tenants = await repo.list_active_owner_bots()
    bots = bots_getter()
    for t in tenants:
        tid = t["id"]
        bot = bots.get(tid)
        if not bot:
            continue
        if not _is_tenant_vip(t):
            continue
        owner_id = t["owner_tg_id"]
        lang = t.get("owner_lang") or "ru"
        try:
            inactive = await repo.get_clients_without_recent_booking(tid, days=45, limit=20)
            if not inactive:
                continue
            shown = inactive[:10]
            names = "\n".join(f"• {r['client_name']}" for r in shown)
            suffix = (
                _t("sched_reactivation_more", lang).format(total=len(inactive))
                if len(inactive) > 10 else ""
            )
            await bot.send_message(
                chat_id=owner_id,
                text=_t("sched_reactivation", lang).format(suffix=suffix, names=names),
            )
            log.info("Reactivation: tenant %d — %d inactive clients", tid, len(inactive))
            await asyncio.sleep(0.5)
        except Exception as exc:
            log.warning("Reactivation failed for tenant %d: %s", tid, exc)


def schedule_daily_reactivation(bots_getter: Callable[[], dict[int, Any]]) -> None:
    """Register daily reactivation job at 10:00 UTC."""
    from apscheduler.triggers.cron import CronTrigger
    get_scheduler().add_job(
        _run_reactivation,
        trigger=CronTrigger(hour=10, minute=0, timezone="UTC"),
        id="daily_reactivation",
        replace_existing=True,
        args=[bots_getter],
    )
    log.info("Daily reactivation job registered (10:00 UTC)")
