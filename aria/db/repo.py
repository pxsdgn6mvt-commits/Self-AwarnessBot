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
        # Migration: add PRIMARY KEY to tables created by older schema versions
        for table in ("aria_clients", "aria_conversations"):
            try:
                await conn.execute(
                    f"DELETE FROM {table} a USING {table} b"
                    f" WHERE a.ctid < b.ctid AND a.user_id = b.user_id"
                )
                await conn.execute(
                    f"ALTER TABLE {table} ADD PRIMARY KEY (user_id)"
                )
                log.info("Migration: added PRIMARY KEY to %s", table)
            except Exception:
                pass  # Already has PRIMARY KEY — nothing to do

        # Migration: add tenant_id to service categories if missing
        try:
            await conn.execute(
                "ALTER TABLE aria_service_categories"
                " ADD COLUMN IF NOT EXISTS tenant_id INTEGER NOT NULL DEFAULT 1"
            )
            await conn.execute(
                "ALTER TABLE aria_service_categories"
                " DROP CONSTRAINT IF EXISTS aria_service_categories_name_key"
            )
            try:
                await conn.execute(
                    "ALTER TABLE aria_service_categories"
                    " ADD CONSTRAINT aria_service_categories_tenant_name_key"
                    " UNIQUE (tenant_id, name)"
                )
            except Exception:
                pass  # Constraint already exists
        except Exception:
            pass

        # Migration: add email columns to aria_tenant_settings if missing.
        # Use information_schema so we add only truly absent columns.
        existing_cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'aria_tenant_settings'"
            )
        }
        for col, defn in [
            ("email_address",         "TEXT"),
            ("email_password",        "TEXT"),
            ("email_imap_server",     "TEXT NOT NULL DEFAULT 'imap.gmail.com'"),
            ("email_imap_port",       "INTEGER NOT NULL DEFAULT 993"),
            ("email_allowed_senders", "TEXT NOT NULL DEFAULT ''"),
            ("email_poll_seconds",    "INTEGER NOT NULL DEFAULT 60"),
        ]:
            if col not in existing_cols:
                try:
                    await conn.execute(
                        f"ALTER TABLE aria_tenant_settings ADD COLUMN {col} {defn}"
                    )
                    log.info("Migration: added column %s to aria_tenant_settings", col)
                except Exception as exc:
                    log.warning("Migration: could not add column %s: %s", col, exc)
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
            ON CONFLICT DO NOTHING
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
    data = json.dumps(history, ensure_ascii=False, default=str)
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        result = await conn.execute(
            "UPDATE aria_conversations SET history=$2, updated_at=NOW() WHERE user_id=$1",
            user_id, data,
        )
        if result == "UPDATE 0":
            try:
                await conn.execute(
                    "INSERT INTO aria_conversations(user_id, history) VALUES ($1, $2)",
                    user_id, data,
                )
            except Exception:
                pass


async def clear_history(user_id: int) -> None:
    async with _p().acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(
            "DELETE FROM aria_conversations WHERE user_id=$1", user_id
        )


def get_pool_instance() -> Optional[asyncpg.Pool]:
    return _pool


# ── Tenant settings ───────────────────────────────────────────────────────────

async def get_tenant_owner(tenant_id: int) -> Optional[int]:
    """Return owner Telegram ID stored in DB, or None if not set yet."""
    async with _p().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT owner_telegram_id FROM aria_tenant_settings WHERE tenant_id=$1",
            tenant_id,
        )
        return row["owner_telegram_id"] if row else None


async def set_tenant_owner(tenant_id: int, owner_telegram_id: int) -> None:
    """Persist owner Telegram ID for this tenant (called once on first /start)."""
    async with _p().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aria_tenant_settings(tenant_id, owner_telegram_id)
            VALUES ($1, $2)
            ON CONFLICT (tenant_id) DO NOTHING
            """,
            tenant_id, owner_telegram_id,
        )


async def get_email_settings(tenant_id: int) -> Optional[asyncpg.Record]:
    """Return the full settings row or None if not configured."""
    async with _p().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM aria_tenant_settings WHERE tenant_id=$1",
            tenant_id,
        )


async def _ensure_email_cols(conn: asyncpg.Connection) -> None:
    existing = {
        r["column_name"]
        for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'aria_tenant_settings'"
        )
    }
    for col, defn in [
        ("email_address",         "TEXT"),
        ("email_password",        "TEXT"),
        ("email_imap_server",     "TEXT NOT NULL DEFAULT 'imap.gmail.com'"),
        ("email_imap_port",       "INTEGER NOT NULL DEFAULT 993"),
        ("email_allowed_senders", "TEXT NOT NULL DEFAULT ''"),
        ("email_poll_seconds",    "INTEGER NOT NULL DEFAULT 60"),
    ]:
        if col not in existing:
            await conn.execute(f"ALTER TABLE aria_tenant_settings ADD COLUMN {col} {defn}")
            log.info("save_email_settings: added missing column %s", col)


_UPDATE_EMAIL_SQL = """
    UPDATE aria_tenant_settings SET
        email_address=$2, email_password=$3,
        email_imap_server=$4, email_imap_port=$5,
        email_allowed_senders=$6, email_poll_seconds=$7
    WHERE tenant_id=$1
"""


async def save_email_settings(
    tenant_id: int,
    *,
    email_address: str,
    email_password: str,
    email_imap_server: str = "imap.gmail.com",
    email_imap_port: int = 993,
    email_allowed_senders: str = "",
    email_poll_seconds: int = 60,
) -> None:
    args = (
        tenant_id, email_address, email_password,
        email_imap_server, email_imap_port,
        email_allowed_senders, email_poll_seconds,
    )
    async with _p().acquire() as conn:
        try:
            await conn.execute(_UPDATE_EMAIL_SQL, *args)
        except asyncpg.exceptions.UndefinedColumnError:
            log.warning("save_email_settings: email columns missing, migrating now")
            await _ensure_email_cols(conn)
            await conn.execute(_UPDATE_EMAIL_SQL, *args)


async def clear_email_settings(tenant_id: int) -> None:
    async with _p().acquire() as conn:
        await conn.execute(
            """
            UPDATE aria_tenant_settings SET
                email_address=NULL, email_password=NULL
            WHERE tenant_id=$1
            """,
            tenant_id,
        )


# ── Service catalogue (owner-managed) ────────────────────────────────────────

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
            """
            INSERT INTO aria_service_categories(tenant_id, name, position)
            VALUES ($1, $2,
                (SELECT COALESCE(MAX(position),0)+1
                 FROM aria_service_categories WHERE tenant_id=$1))
            ON CONFLICT (tenant_id, name) DO NOTHING
            RETURNING id
            """,
            tenant_id, name,
        )
        if row is None:
            row = await conn.fetchrow(
                "SELECT id FROM aria_service_categories WHERE tenant_id=$1 AND name=$2",
                tenant_id, name,
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


async def get_services_tree(tenant_id: int) -> dict[str, list[str]]:
    """Return {category: [items]} for this tenant from DB."""
    cats = await get_categories(tenant_id)
    if not cats:
        return {}
    result: dict[str, list[str]] = {}
    for cat in cats:
        items = await get_items(cat["id"])
        result[cat["name"]] = [it["name"] for it in items]
    return result
