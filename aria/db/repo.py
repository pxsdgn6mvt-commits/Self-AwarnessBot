"""Data access layer for the Aria salon bot (asyncpg)."""

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


# ── Clients ───────────────────────────────────────────────────────────────────

async def upsert_client(user_id: int, lang: str = "en") -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aria_clients(user_id, lang)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id, lang,
        )


async def set_client_lang(user_id: int, lang: str) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "UPDATE aria_clients SET lang=$1 WHERE user_id=$2",
            lang, user_id,
        )


async def get_client(user_id: int) -> Optional[asyncpg.Record]:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        return await conn.fetchrow(
            "SELECT * FROM aria_clients WHERE user_id=$1", user_id
        )


# ── Bookings ──────────────────────────────────────────────────────────────────

async def create_booking(
    user_id: int,
    client_name: str,
    service: str,
    scheduled_at: datetime,
    calendar_event_id: Optional[str] = None,
) -> int:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        row = await conn.fetchrow(
            """
            INSERT INTO aria_bookings
                (user_id, client_name, service, scheduled_at, calendar_event_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            user_id, client_name, service, scheduled_at, calendar_event_id,
        )
        return row["id"]


async def get_booking(booking_id: int) -> Optional[asyncpg.Record]:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        return await conn.fetchrow(
            "SELECT * FROM aria_bookings WHERE id=$1", booking_id
        )


async def get_upcoming_booking(user_id: int) -> Optional[asyncpg.Record]:
    now = datetime.now(timezone.utc)
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        return await conn.fetchrow(
            """
            SELECT * FROM aria_bookings
            WHERE user_id=$1 AND status='confirmed' AND scheduled_at > $2
            ORDER BY scheduled_at ASC
            LIMIT 1
            """,
            user_id, now,
        )


async def update_booking_time(booking_id: int, new_time: datetime) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            """
            UPDATE aria_bookings
            SET scheduled_at=$1, reminder_sent=FALSE
            WHERE id=$2
            """,
            new_time, booking_id,
        )


async def update_booking_status(booking_id: int, status: str) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "UPDATE aria_bookings SET status=$1 WHERE id=$2",
            status, booking_id,
        )


async def mark_reminder_sent(booking_id: int) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "UPDATE aria_bookings SET reminder_sent=TRUE WHERE id=$1", booking_id
        )


async def mark_noshow_check_sent(booking_id: int) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "UPDATE aria_bookings SET noshow_check_sent=TRUE WHERE id=$1", booking_id
        )


async def mark_upsell_offered(booking_id: int) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "UPDATE aria_bookings SET upsell_offered=TRUE WHERE id=$1", booking_id
        )


async def get_confirmed_bookings_at(dt: datetime) -> list[asyncpg.Record]:
    """Bookings confirmed for a specific datetime (used by scheduler)."""
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        return await conn.fetch(
            """
            SELECT * FROM aria_bookings
            WHERE scheduled_at=$1 AND status='confirmed'
            """,
            dt,
        )


async def get_slots_on_date(date_str: str) -> list[datetime]:
    """Returns all booked datetimes on a given date (YYYY-MM-DD)."""
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        rows = await conn.fetch(
            """
            SELECT scheduled_at FROM aria_bookings
            WHERE scheduled_at::date = $1::date
              AND status = 'confirmed'
            """,
            date_str,
        )
        return [r["scheduled_at"] for r in rows]


# ── Waitlist ──────────────────────────────────────────────────────────────────

async def add_to_waitlist(user_id: int, client_name: str, service: str) -> int:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        row = await conn.fetchrow(
            """
            INSERT INTO aria_waitlist(user_id, client_name, service)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            user_id, client_name, service,
        )
        return row["id"]


async def get_waitlist_for_service(service: str) -> list[asyncpg.Record]:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        return await conn.fetch(
            """
            SELECT * FROM aria_waitlist
            WHERE LOWER(service)=LOWER($1) AND notified=FALSE
            ORDER BY added_at ASC
            """,
            service,
        )


async def mark_waitlist_notified(waitlist_id: int) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "UPDATE aria_waitlist SET notified=TRUE WHERE id=$1", waitlist_id
        )


# ── Conversations ─────────────────────────────────────────────────────────────

async def load_history(user_id: int) -> list[dict]:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        row = await conn.fetchrow(
            "SELECT history FROM aria_conversations WHERE user_id=$1", user_id
        )
        if row is None:
            return []
        return json.loads(row["history"])


async def save_history(user_id: int, history: list[dict]) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            """
            INSERT INTO aria_conversations(user_id, history, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET history=$2, updated_at=NOW()
            """,
            user_id, json.dumps(history, ensure_ascii=False, default=str),
        )


async def clear_history(user_id: int) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "DELETE FROM aria_conversations WHERE user_id=$1", user_id
        )


def get_pool_instance() -> Optional[asyncpg.Pool]:
    return _pool


# ── Service catalogue (owner-managed) ────────────────────────────────────────

async def get_categories() -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM aria_service_categories ORDER BY position, id"
        )


async def get_items(category_id: int) -> list[asyncpg.Record]:
    async with _p().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM aria_service_items WHERE category_id=$1 ORDER BY position, id",
            category_id,
        )


async def add_category(name: str) -> int:
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO aria_service_categories(name, position)
            VALUES ($1, (SELECT COALESCE(MAX(position),0)+1 FROM aria_service_categories))
            ON CONFLICT (name) DO NOTHING
            RETURNING id
            """,
            name,
        )
        if row is None:
            row = await conn.fetchrow(
                "SELECT id FROM aria_service_categories WHERE name=$1", name
            )
        return row["id"]


async def delete_category(category_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "DELETE FROM aria_service_categories WHERE id=$1", category_id
        )


async def add_item(category_id: int, name: str) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aria_service_items(category_id, name, position)
            VALUES ($1, $2, (SELECT COALESCE(MAX(position),0)+1
                             FROM aria_service_items WHERE category_id=$1))
            ON CONFLICT DO NOTHING
            """,
            category_id, name,
        )


async def delete_item(item_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            "DELETE FROM aria_service_items WHERE id=$1", item_id
        )


async def get_services_tree() -> dict[str, list[str]]:
    """Return {category: [items]} from DB. Empty dict if nothing configured."""
    cats = await get_categories()
    if not cats:
        return {}
    result: dict[str, list[str]] = {}
    for cat in cats:
        items = await get_items(cat["id"])
        result[cat["name"]] = [it["name"] for it in items]
    return result
