import asyncpg
import json
from datetime import datetime, timezone
from typing import Optional
from config import DATABASE_URL


_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ─── Инициализация схемы ──────────────────────────────────────────────────────

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      BIGINT PRIMARY KEY,
                username     TEXT,
                lang         TEXT NOT NULL DEFAULT 'ru',
                master_hash  TEXT,
                pin_hash     TEXT,
                plan         TEXT NOT NULL DEFAULT 'free',
                plan_expires TIMESTAMPTZ,
                referrer_id  BIGINT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS entries (
                id                BIGSERIAL PRIMARY KEY,
                user_id           BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                category          TEXT NOT NULL,
                name              TEXT NOT NULL,
                content_encrypted TEXT NOT NULL,
                tags              TEXT DEFAULT '',
                is_favorite       BOOLEAN NOT NULL DEFAULT FALSE,
                created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS payments (
                id         BIGSERIAL PRIMARY KEY,
                user_id    BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                type       TEXT NOT NULL,
                stars      INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id           BIGSERIAL PRIMARY KEY,
                referrer_id  BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                referred_id  BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                reward_given BOOLEAN NOT NULL DEFAULT FALSE,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS managed_users (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                custom_name TEXT NOT NULL DEFAULT '',
                is_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
                notes       TEXT NOT NULL DEFAULT '',
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_entries_user  ON entries(user_id);
            CREATE INDEX IF NOT EXISTS idx_entries_cat   ON entries(user_id, category);
            CREATE INDEX IF NOT EXISTS idx_referrals_ref ON referrals(referrer_id);
        """)


# ─── Пользователи ────────────────────────────────────────────────────────────

async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def create_user(user_id: int, username: str, lang: str = "ru",
                      referrer_id: int = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users(user_id, username, lang, referrer_id)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(user_id) DO NOTHING
            """,
            user_id, username, lang, referrer_id,
        )


async def set_master_hash(user_id: int, master_hash: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET master_hash=$1 WHERE user_id=$2",
            master_hash, user_id,
        )


async def set_pin_hash(user_id: int, pin_hash: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET pin_hash=$1 WHERE user_id=$2",
            pin_hash, user_id,
        )


async def set_lang(user_id: int, lang: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET lang=$1 WHERE user_id=$2",
            lang, user_id,
        )


async def set_plan(user_id: int, plan: str, expires=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET plan=$1, plan_expires=$2 WHERE user_id=$3",
            plan, expires, user_id,
        )


# ─── Записи ──────────────────────────────────────────────────────────────────

async def add_entry(user_id: int, category: str, name: str,
                    content_encrypted: str, tags: str = "") -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO entries(user_id, category, name, content_encrypted, tags)
            VALUES($1,$2,$3,$4,$5)
            RETURNING id
            """,
            user_id, category, name, content_encrypted, tags,
        )
        return row["id"]


async def get_entry(entry_id: int, user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM entries WHERE id=$1 AND user_id=$2",
            entry_id, user_id,
        )


async def get_entries_by_category(user_id: int, category: str) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM entries WHERE user_id=$1 AND category=$2 ORDER BY updated_at DESC",
            user_id, category,
        )


async def get_all_entries(user_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM entries WHERE user_id=$1 ORDER BY updated_at DESC",
            user_id,
        )


async def search_entries(user_id: int, query: str) -> list:
    pool = await get_pool()
    q = f"%{query.lower()}%"
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM entries
            WHERE user_id=$1 AND (LOWER(name) LIKE $2 OR LOWER(tags) LIKE $2)
            ORDER BY updated_at DESC
            """,
            user_id, q,
        )


async def get_favorites(user_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM entries WHERE user_id=$1 AND is_favorite=TRUE ORDER BY updated_at DESC",
            user_id,
        )


async def toggle_favorite(entry_id: int, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE entries SET is_favorite = NOT is_favorite WHERE id=$1 AND user_id=$2",
            entry_id, user_id,
        )


async def update_entry(entry_id: int, user_id: int, name: str,
                       content_encrypted: str, tags: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE entries
            SET name=$1, content_encrypted=$2, tags=$3, updated_at=NOW()
            WHERE id=$4 AND user_id=$5
            """,
            name, content_encrypted, tags, entry_id, user_id,
        )


async def delete_entry(entry_id: int, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM entries WHERE id=$1 AND user_id=$2",
            entry_id, user_id,
        )


async def count_entries(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM entries WHERE user_id=$1", user_id
        )


# ─── Платежи ─────────────────────────────────────────────────────────────────

async def add_payment(user_id: int, payment_type: str, stars: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO payments(user_id, type, stars) VALUES($1,$2,$3)",
            user_id, payment_type, stars,
        )


# ─── Рефералы ────────────────────────────────────────────────────────────────

async def add_referral(referrer_id: int, referred_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO referrals(referrer_id, referred_id)
            VALUES($1,$2) ON CONFLICT DO NOTHING
            """,
            referrer_id, referred_id,
        )


async def get_referral_count(referrer_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=$1", referrer_id
        )


async def mark_referral_rewarded(referred_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE referrals SET reward_given=TRUE WHERE referred_id=$1",
            referred_id,
        )


async def get_unrewarded_referral(referred_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM referrals WHERE referred_id=$1 AND reward_given=FALSE",
            referred_id,
        )


# ─── Статистика ───────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_users   = await conn.fetchval("SELECT COUNT(*) FROM users")
        free_users    = await conn.fetchval("SELECT COUNT(*) FROM users WHERE plan='free'")
        paid_users    = await conn.fetchval("SELECT COUNT(*) FROM users WHERE plan!='free'")
        total_entries = await conn.fetchval("SELECT COUNT(*) FROM entries")
        total_revenue = await conn.fetchval("SELECT COALESCE(SUM(stars),0) FROM payments")
        new_today     = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '1 day'"
        )
    return {
        "total_users": total_users,
        "free_users":  free_users,
        "paid_users":  paid_users,
        "total_entries": total_entries,
        "total_revenue_stars": int(total_revenue),
        "new_today": new_today,
    }


async def get_premium_users_for_backup() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id FROM users WHERE plan='premium'"
        )


# ─── Экспорт / импорт ────────────────────────────────────────────────────────

async def export_entries_encrypted(user_id: int) -> str:
    entries = await get_all_entries(user_id)
    data = [dict(e) for e in entries]
    for row in data:
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()
    return json.dumps(data, ensure_ascii=False)


async def import_entries_from_backup(user_id: int, entries_json: str):
    data = json.loads(entries_json)
    pool = await get_pool()
    async with pool.acquire() as conn:
        for e in data:
            await conn.execute(
                """
                INSERT INTO entries(user_id, category, name, content_encrypted, tags, is_favorite)
                VALUES($1,$2,$3,$4,$5,$6)
                """,
                user_id,
                e.get("category", "notes"),
                e.get("name", ""),
                e.get("content_encrypted", ""),
                e.get("tags", ""),
                e.get("is_favorite", False),
            )


# ─── Управляемые пользователи (блокировка) ───────────────────────────────────

async def add_managed_user(telegram_id: int, custom_name: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO managed_users(telegram_id, custom_name)
            VALUES($1, $2)
            ON CONFLICT(telegram_id) DO UPDATE SET custom_name=EXCLUDED.custom_name
            RETURNING id
            """,
            telegram_id, custom_name,
        )
        return row["id"]


async def get_all_managed_users() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM managed_users ORDER BY id ASC"
        )


async def get_managed_user_by_id(custom_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM managed_users WHERE id=$1", custom_id
        )


async def get_managed_user_by_telegram_id(telegram_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM managed_users WHERE telegram_id=$1", telegram_id
        )


async def toggle_managed_user_blocked(custom_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE managed_users SET is_blocked = NOT is_blocked
            WHERE id=$1 RETURNING is_blocked
            """,
            custom_id,
        )
        return row["is_blocked"] if row else False


async def update_managed_user_name(custom_id: int, new_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE managed_users SET custom_name=$1 WHERE id=$2",
            new_name, custom_id,
        )


async def update_managed_user_notes(custom_id: int, notes: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE managed_users SET notes=$1 WHERE id=$2",
            notes, custom_id,
        )


async def is_user_blocked(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_blocked FROM managed_users WHERE telegram_id=$1",
            telegram_id,
        )
        return bool(row and row["is_blocked"])
