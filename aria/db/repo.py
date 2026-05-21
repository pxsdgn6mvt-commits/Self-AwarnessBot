"""Data access layer for Aria — asyncpg, multi-tenant."""

from __future__ import annotations

import json
import logging
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg

from aria.db.models import SCHEMA

log = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_db(dsn: str) -> None:
    pool = await get_pool(dsn)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
    log.info("aria DB schema ready")


def _p() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_db() first")
    return _pool


# ── Tenants ───────────────────────────────────────────────────────────────────

async def get_tenant_by_token(bot_token: str) -> Optional[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM aria_tenants WHERE bot_token=$1", bot_token
        )


async def get_tenant(tenant_id: int) -> Optional[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM aria_tenants WHERE id=$1", tenant_id
        )


async def list_active_tenants() -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM aria_tenants WHERE active=TRUE ORDER BY id"
        )


async def create_tenant(
    bot_token: str,
    owner_tg_id: Optional[int] = None,
    salon_name: str = "My Salon",
    owner_name: str = "Owner",
    services: str = "haircut, manicure",
    hours: str = "Mon-Sat 10:00-20:00",
    open_hour: int = 10,
    close_hour: int = 20,
    slot_minutes: int = 60,
    working_days: str = "1,2,3,4,5,6",
    google_cal_credentials: Optional[str] = None,
    google_cal_id: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    setup_complete: bool = False,
) -> int:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO aria_tenants (
                bot_token, owner_tg_id, salon_name, owner_name, services, hours,
                open_hour, close_hour, slot_minutes, working_days,
                google_cal_credentials, google_cal_id, anthropic_api_key, setup_complete
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            ON CONFLICT (bot_token) DO UPDATE SET
                owner_tg_id = COALESCE(EXCLUDED.owner_tg_id, aria_tenants.owner_tg_id),
                salon_name  = EXCLUDED.salon_name,
                owner_name  = EXCLUDED.owner_name,
                services    = EXCLUDED.services,
                hours       = EXCLUDED.hours,
                setup_complete = EXCLUDED.setup_complete
            RETURNING id
            """,
            bot_token, owner_tg_id, salon_name, owner_name, services, hours,
            open_hour, close_hour, slot_minutes, working_days,
            google_cal_credentials, google_cal_id, anthropic_api_key, setup_complete,
        )
        return row["id"]


async def update_tenant(tenant_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields))
    vals = list(fields.values())
    async with _p().acquire() as conn:
        await conn.execute(
            f"UPDATE aria_tenants SET {cols} WHERE id=$1",
            tenant_id, *vals,
        )


async def set_tenant_active(tenant_id: int, active: bool) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_tenants SET active=$1 WHERE id=$2", active, tenant_id
        )


async def set_tenant_vip(
    tenant_id: int, is_vip: bool, vip_until: Optional[datetime] = None
) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_tenants SET is_vip=$2, vip_until=$3 WHERE id=$1",
            tenant_id, is_vip, vip_until,
        )


async def get_vip_context(tenant_id: int) -> dict:
    """Fetch enriched context for VIP tenant's AI prompt."""
    async with _p().acquire() as conn:
        client_rows = await conn.fetch(
            """SELECT notes FROM aria_clients
               WHERE tenant_id=$1 AND notes IS NOT NULL AND notes <> ''
               LIMIT 30""",
            tenant_id,
        )
        service_rows = await conn.fetch(
            """SELECT sc.name AS category, si.name, si.price, si.duration_minutes
               FROM aria_service_items si
               JOIN aria_service_categories sc ON sc.id = si.category_id
               WHERE sc.tenant_id=$1
               ORDER BY sc.position, si.position""",
            tenant_id,
        )
    return {
        "client_notes": [r["notes"] for r in client_rows],
        "services": [dict(r) for r in service_rows],
    }


# ── Clients ───────────────────────────────────────────────────────────────────

async def upsert_client(tenant_id: int, user_id: int, lang: str = "en") -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aria_clients(tenant_id, user_id, lang)
            VALUES ($1, $2, $3)
            ON CONFLICT (tenant_id, user_id) DO NOTHING
            """,
            tenant_id, user_id, lang,
        )


async def get_client_profile(tenant_id: int, user_id: int) -> Optional[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM aria_clients WHERE tenant_id=$1 AND user_id=$2",
            tenant_id, user_id,
        )


async def update_client_style(tenant_id: int, user_id: int, style: str) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aria_clients(tenant_id, user_id, communication_style)
            VALUES ($1,$2,$3)
            ON CONFLICT (tenant_id, user_id) DO UPDATE SET communication_style=$3
            """,
            tenant_id, user_id, style,
        )


async def set_client_vip(
    tenant_id: int, user_id: int, is_vip: bool, vip_until: Optional[datetime] = None
) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aria_clients(tenant_id, user_id, is_vip, vip_until)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (tenant_id, user_id) DO UPDATE SET is_vip=$3, vip_until=$4
            """,
            tenant_id, user_id, is_vip, vip_until,
        )


async def get_clients_without_recent_booking(
    tenant_id: int, days: int = 45, limit: int = 20
) -> list[asyncpg.Record]:
    """Client names whose last confirmed past booking was more than `days` days ago."""
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT client_name, MAX(scheduled_at) AS last_visit
            FROM aria_bookings
            WHERE tenant_id=$1 AND status='confirmed' AND scheduled_at < NOW()
            GROUP BY client_name
            HAVING MAX(scheduled_at) < NOW() - ($2 * INTERVAL '1 day')
            ORDER BY last_visit ASC
            LIMIT $3
            """,
            tenant_id, days, limit,
        )


async def list_active_owner_bots() -> list[asyncpg.Record]:
    """Active tenants with a configured owner — for broadcast and reactivation."""
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT id, owner_tg_id, salon_name, bot_token, timezone,
                   reminder_hours_before, daily_summary_hour, owner_lang
            FROM aria_tenants
            WHERE active=TRUE AND setup_complete=TRUE AND owner_tg_id IS NOT NULL
            ORDER BY id
            """
        )


# ── Bookings ──────────────────────────────────────────────────────────────────

async def create_booking(
    tenant_id: int,
    user_id: int,
    client_name: str,
    service: str,
    scheduled_at: datetime,
    calendar_event_id: Optional[str] = None,
    client_phone: str | None = None,
) -> int:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO aria_bookings
                (tenant_id, user_id, client_name, service, scheduled_at,
                 calendar_event_id, client_phone)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            RETURNING id
            """,
            tenant_id, user_id, client_name, service, scheduled_at,
            calendar_event_id, client_phone,
        )
        return row["id"]


async def get_booking(booking_id: int) -> Optional[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM aria_bookings WHERE id=$1", booking_id
        )


async def get_upcoming_booking(tenant_id: int, user_id: int) -> Optional[asyncpg.Record]:
    now = datetime.now(timezone.utc)
    async with _p().acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1 AND user_id=$2 AND status='confirmed' AND scheduled_at > $3
            ORDER BY scheduled_at ASC LIMIT 1
            """,
            tenant_id, user_id, now,
        )


async def update_booking_time(booking_id: int, new_time: datetime) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_bookings SET scheduled_at=$1, reminder_sent=FALSE WHERE id=$2",
            new_time, booking_id,
        )


async def update_booking_status(booking_id: int, status: str) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_bookings SET status=$1 WHERE id=$2", status, booking_id
        )


async def set_booking_paid(booking_id: int, paid: bool = True) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_bookings SET paid=$1 WHERE id=$2", paid, booking_id
        )


async def set_booking_note(booking_id: int, note: str) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_bookings SET notes=$1 WHERE id=$2", note, booking_id
        )


async def mark_reminder_sent(booking_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_bookings SET reminder_sent=TRUE WHERE id=$1", booking_id
        )


async def mark_noshow_check_sent(booking_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_bookings SET noshow_check_sent=TRUE WHERE id=$1", booking_id
        )


async def get_pending_reminders(tenant_id: int, within_minutes: int) -> list[asyncpg.Record]:
    """Bookings whose reminder is overdue or due within within_minutes — reminder not yet sent."""
    now = datetime.now(timezone.utc)
    upper = now + timedelta(minutes=within_minutes)
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1
              AND reminder_sent = FALSE
              AND status IN ('confirmed', 'pending')
              AND scheduled_at > $2
              AND scheduled_at <= $3
            ORDER BY scheduled_at ASC
            """,
            tenant_id, now, upper,
        )


async def get_bookings_for_tomorrow(tenant_id: int, tz_str: str) -> list[asyncpg.Record]:
    """All confirmed/pending bookings for tomorrow in the tenant's local timezone."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_str or "UTC")
    now_local = datetime.now(tz)
    tomorrow = (now_local + timedelta(days=1)).date()
    dt_from = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, tzinfo=tz).astimezone(timezone.utc)
    dt_to   = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 23, 59, 59, tzinfo=tz).astimezone(timezone.utc)
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1
              AND scheduled_at >= $2
              AND scheduled_at <= $3
              AND status IN ('confirmed', 'pending')
            ORDER BY scheduled_at ASC
            """,
            tenant_id, dt_from, dt_to,
        )


async def get_bookings_for_date(tenant_id: int, date_str: str) -> list[asyncpg.Record]:
    date_obj = _date.fromisoformat(date_str)
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1 AND scheduled_at::date=$2
              AND status IN ('confirmed','pending')
            ORDER BY scheduled_at ASC
            """,
            tenant_id, date_obj,
        )


async def get_bookings_in_range(
    tenant_id: int, date_from: datetime, date_to: datetime
) -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1 AND scheduled_at >= $2 AND scheduled_at <= $3
              AND status IN ('confirmed','pending')
            ORDER BY scheduled_at ASC
            """,
            tenant_id, date_from, date_to,
        )


async def get_all_upcoming_bookings(tenant_id: int, limit: int = 30) -> list[asyncpg.Record]:
    now = datetime.now(timezone.utc)
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1 AND scheduled_at > $2
              AND status IN ('confirmed','pending')
            ORDER BY scheduled_at ASC LIMIT $3
            """,
            tenant_id, now, limit,
        )


async def get_slots_on_date(tenant_id: int, date_str: str) -> list[datetime]:
    date_obj = _date.fromisoformat(date_str)
    async with _p().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT scheduled_at FROM aria_bookings
            WHERE tenant_id=$1 AND scheduled_at::date=$2 AND status='confirmed'
            """,
            tenant_id, date_obj,
        )
        return [r["scheduled_at"] for r in rows]



# ── Client status ─────────────────────────────────────────────────────────────

def client_status_emoji(visits: int, no_show: int, cancelled: int) -> str:
    """Return status emoji(s) based on visit and incident counts."""
    risky   = no_show >= 2 or cancelled >= 3
    regular = visits >= 3
    if risky and regular:
        return "⭐⚠️"
    if risky:
        return "⚠️"
    if regular:
        return "⭐"
    return "🆕"


# ── Dashboard & analytics ─────────────────────────────────────────────────────

async def get_today_stats(tenant_id: int, date_str: str) -> dict:
    """Returns booking count, paid count, expected and received income for a date."""
    date_obj = _date.fromisoformat(date_str)
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('confirmed','pending'))            AS total,
                COUNT(*) FILTER (WHERE paid = TRUE)                                  AS paid_count,
                COALESCE(SUM(si.price) FILTER (WHERE status IN ('confirmed','pending')), 0) AS expected,
                COALESCE(SUM(si.price) FILTER (WHERE paid = TRUE), 0)               AS received
            FROM aria_bookings b
            LEFT JOIN aria_service_items si
                ON LOWER(si.name) = LOWER(b.service)
               AND si.category_id IN (
                       SELECT id FROM aria_service_categories WHERE tenant_id = $1
                   )
            WHERE b.tenant_id = $1 AND b.scheduled_at::date = $2
            """,
            tenant_id, date_obj,
        )
        return dict(row) if row else {"total": 0, "paid_count": 0, "expected": 0, "received": 0}


async def get_week_booking_count(tenant_id: int, tz_str: str = "UTC") -> int:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_str)
    now_local = datetime.now(tz)
    monday     = now_local.date() - timedelta(days=now_local.weekday())
    next_monday = monday + timedelta(days=7)
    week_start = datetime(monday.year,      monday.month,      monday.day,      tzinfo=tz).astimezone(timezone.utc)
    week_end   = datetime(next_monday.year, next_monday.month, next_monday.day, tzinfo=tz).astimezone(timezone.utc)
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) FROM aria_bookings
            WHERE tenant_id=$1
              AND status IN ('confirmed','pending')
              AND scheduled_at >= $2
              AND scheduled_at <  $3
            """,
            tenant_id, week_start, week_end,
        )
        return row[0] if row else 0


async def get_period_stats(tenant_id: int, dt_from: datetime, dt_to: datetime) -> dict:
    """General booking stats for any time range."""
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE b.status IN ('confirmed','pending'))                   AS total,
                COUNT(*) FILTER (WHERE b.paid = TRUE)                                         AS paid_count,
                COALESCE(SUM(si.price) FILTER (WHERE b.status IN ('confirmed','pending')), 0) AS expected,
                COALESCE(SUM(si.price) FILTER (WHERE b.paid = TRUE), 0)                      AS received
            FROM aria_bookings b
            LEFT JOIN aria_service_items si
                ON LOWER(si.name) = LOWER(b.service)
               AND si.category_id IN (
                       SELECT id FROM aria_service_categories WHERE tenant_id = $1
                   )
            WHERE b.tenant_id = $1
              AND b.scheduled_at >= $2
              AND b.scheduled_at <= $3
            """,
            tenant_id, dt_from, dt_to,
        )
        return dict(row) if row else {"total": 0, "paid_count": 0, "expected": 0, "received": 0}


async def get_service_stats(tenant_id: int, limit: int = 5) -> list[asyncpg.Record]:
    """Returns services sorted by booking count with revenue."""
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT
                b.service,
                COUNT(*)                                              AS visits,
                COALESCE(SUM(si.price) FILTER (WHERE b.paid=TRUE), 0) AS revenue
            FROM aria_bookings b
            LEFT JOIN aria_service_items si
                ON LOWER(si.name) = LOWER(b.service)
               AND si.category_id IN (
                       SELECT id FROM aria_service_categories WHERE tenant_id = $1
                   )
            WHERE b.tenant_id = $1 AND b.status IN ('confirmed','pending','completed')
            GROUP BY b.service
            ORDER BY visits DESC
            LIMIT $2
            """,
            tenant_id, limit,
        )


async def get_client_stats(tenant_id: int, limit: int = 50) -> list[asyncpg.Record]:
    """Returns clients sorted by visit count with status counts."""
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT
                client_name,
                COUNT(*) FILTER (WHERE b.status IN ('confirmed','pending','completed')) AS visits,
                MAX(scheduled_at) FILTER (WHERE b.status IN ('confirmed','pending','completed')) AS last_visit,
                COUNT(*) FILTER (WHERE paid = TRUE)                AS paid_visits,
                COALESCE(SUM(si.price) FILTER (WHERE paid=TRUE), 0) AS total_spent,
                COUNT(*) FILTER (WHERE b.status = 'no_show')       AS no_show_count,
                COUNT(*) FILTER (WHERE b.status = 'cancelled')     AS cancelled_count
            FROM aria_bookings b
            LEFT JOIN aria_service_items si
                ON LOWER(si.name) = LOWER(b.service)
               AND si.category_id IN (
                       SELECT id FROM aria_service_categories WHERE tenant_id = $1
                   )
            WHERE b.tenant_id = $1
            GROUP BY client_name
            HAVING COUNT(*) FILTER (WHERE b.status IN ('confirmed','pending','completed')) > 0
            ORDER BY visits DESC
            LIMIT $2
            """,
            tenant_id, limit,
        )


async def get_client_statuses_batch(tenant_id: int, client_names: list[str]) -> dict[str, str]:
    """Returns {client_name_lower: status_emoji} for a list of names."""
    if not client_names:
        return {}
    lower_names = [n.lower() for n in client_names]
    async with _p().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                client_name,
                COUNT(*) FILTER (WHERE status IN ('confirmed','pending','completed')) AS visits,
                COUNT(*) FILTER (WHERE status = 'no_show')   AS no_show_count,
                COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_count
            FROM aria_bookings
            WHERE tenant_id=$1 AND LOWER(client_name) = ANY($2::text[])
            GROUP BY client_name
            """,
            tenant_id, lower_names,
        )
    result: dict[str, str] = {
        row["client_name"].lower(): client_status_emoji(
            int(row["visits"]), int(row["no_show_count"]), int(row["cancelled_count"])
        )
        for row in rows
    }
    for name in client_names:
        result.setdefault(name.lower(), "🆕")
    return result


async def get_risky_clients(tenant_id: int, limit: int = 5) -> list[asyncpg.Record]:
    """Clients with 2+ no-shows or 3+ cancellations, sorted by risk score."""
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT
                client_name,
                COUNT(*) FILTER (WHERE status = 'no_show')   AS no_show_count,
                COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_count,
                COUNT(*) FILTER (WHERE status IN ('confirmed','pending','completed')) AS visits
            FROM aria_bookings
            WHERE tenant_id=$1
            GROUP BY client_name
            HAVING COUNT(*) FILTER (WHERE status = 'no_show')   >= 2
                OR COUNT(*) FILTER (WHERE status = 'cancelled') >= 3
            ORDER BY (COUNT(*) FILTER (WHERE status = 'no_show') * 2
                    + COUNT(*) FILTER (WHERE status = 'cancelled')) DESC
            LIMIT $2
            """,
            tenant_id, limit,
        )


async def get_client_bookings(tenant_id: int, client_name: str) -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1 AND LOWER(client_name)=LOWER($2)
            ORDER BY scheduled_at DESC
            LIMIT 20
            """,
            tenant_id, client_name,
        )


# ── Waitlist ──────────────────────────────────────────────────────────────────

async def add_to_waitlist(
    tenant_id: int, user_id: int, client_name: str, service: str
) -> int:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO aria_waitlist(tenant_id, user_id, client_name, service)
            VALUES ($1,$2,$3,$4) RETURNING id
            """,
            tenant_id, user_id, client_name, service,
        )
        return row["id"]


async def mark_waitlist_notified(waitlist_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_waitlist SET notified=TRUE WHERE id=$1", waitlist_id
        )


# ── Conversations ─────────────────────────────────────────────────────────────

async def load_history(tenant_id: int, user_id: int) -> list[dict]:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT history FROM aria_conversations WHERE tenant_id=$1 AND user_id=$2",
            tenant_id, user_id,
        )
        if row is None:
            return []
        return json.loads(row["history"])


async def save_history(tenant_id: int, user_id: int, history: list[dict]) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aria_conversations(tenant_id, user_id, history, updated_at)
            VALUES ($1,$2,$3,NOW())
            ON CONFLICT (tenant_id, user_id)
            DO UPDATE SET history=$3, updated_at=NOW()
            """,
            tenant_id, user_id,
            json.dumps(history, ensure_ascii=False, default=str),
        )


async def clear_history(tenant_id: int, user_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "DELETE FROM aria_conversations WHERE tenant_id=$1 AND user_id=$2",
            tenant_id, user_id,
        )


# ── Service catalogue ─────────────────────────────────────────────────────────

async def get_categories(tenant_id: int) -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM aria_service_categories WHERE tenant_id=$1 ORDER BY position, id",
            tenant_id,
        )


async def get_all_service_items(tenant_id: int) -> list[asyncpg.Record]:
    """All items across all categories for a tenant (for booking wizard)."""
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT si.id, si.name, si.price, si.duration_minutes, sc.name AS category_name
            FROM aria_service_items si
            JOIN aria_service_categories sc ON si.category_id = sc.id
            WHERE sc.tenant_id = $1
            ORDER BY sc.name, si.position, si.id
            """,
            tenant_id,
        )


async def get_service_info(tenant_id: int, service_name: str) -> asyncpg.Record | None:
    """Fetch price and duration for a service by name."""
    async with _p().acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT si.price, si.duration_minutes
            FROM aria_service_items si
            JOIN aria_service_categories sc ON si.category_id = sc.id
            WHERE sc.tenant_id = $1 AND LOWER(si.name) = LOWER($2)
            LIMIT 1
            """,
            tenant_id, service_name,
        )


async def get_items(category_id: int) -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM aria_service_items WHERE category_id=$1 ORDER BY position, id",
            category_id,
        )


async def add_category(tenant_id: int, name: str) -> int:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO aria_service_categories(tenant_id, name) VALUES ($1,$2) RETURNING id",
            tenant_id, name,
        )
        return row["id"]


async def delete_category(category_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "DELETE FROM aria_service_categories WHERE id=$1", category_id
        )


async def add_item(
    category_id: int,
    name: str,
    price: float | None = None,
    duration_minutes: int | None = None,
) -> int:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO aria_service_items(category_id, name, price, duration_minutes)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            category_id, name, price, duration_minutes,
        )
        return row["id"]


async def delete_item(item_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "DELETE FROM aria_service_items WHERE id=$1", item_id
        )


async def update_item_price(item_id: int, price: float | None) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_service_items SET price=$2 WHERE id=$1", item_id, price
        )


async def update_item_duration(item_id: int, duration_minutes: int | None) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "UPDATE aria_service_items SET duration_minutes=$2 WHERE id=$1", item_id, duration_minutes
        )
