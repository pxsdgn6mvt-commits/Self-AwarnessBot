"""Data access layer for Aria — asyncpg, multi-tenant."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
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
            SELECT id, owner_tg_id, salon_name, bot_token
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
) -> int:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO aria_bookings
                (tenant_id, user_id, client_name, service, scheduled_at, calendar_event_id)
            VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING id
            """,
            tenant_id, user_id, client_name, service, scheduled_at, calendar_event_id,
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


async def get_bookings_for_date(tenant_id: int, date_str: str) -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE tenant_id=$1 AND scheduled_at::date=$2::date
              AND status IN ('confirmed','pending')
            ORDER BY scheduled_at ASC
            """,
            tenant_id, date_str,
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
    async with _p().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT scheduled_at FROM aria_bookings
            WHERE tenant_id=$1 AND scheduled_at::date=$2::date AND status='confirmed'
            """,
            tenant_id, date_str,
        )
        return [r["scheduled_at"] for r in rows]



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
