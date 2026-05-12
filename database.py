import sqlite3
import logging
import hashlib
import json
from datetime import datetime
from crypto import encrypt, decrypt
import config

logger = logging.getLogger(__name__)
DB_PATH = "vault.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vault (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        title_encrypted TEXT NOT NULL,
        content_encrypted TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        is_favorite INTEGER NOT NULL DEFAULT 0,
        tags TEXT NOT NULL DEFAULT ""
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_vault_category ON vault(category)')
    # Добавляем колонки если их нет (миграция)
    for col, definition in [
        ("is_favorite", "INTEGER NOT NULL DEFAULT 0"),
        ("tags", "TEXT NOT NULL DEFAULT \"\""),
    ]:
        try:
            c.execute(f'ALTER TABLE vault ADD COLUMN {col} {definition}')
        except Exception:
            pass
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()
    logger.info("БД инициализирована")


# ─── Настройки (пин-код) ───────────────────────────────────────────────────

def get_setting(key: str) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()


def set_pin(pin: str):
    hashed = hashlib.sha256(pin.encode()).hexdigest()
    set_setting("pin_hash", hashed)


def check_pin(pin: str) -> bool:
    stored = get_setting("pin_hash")
    if not stored:
        return False
    return hashlib.sha256(pin.encode()).hexdigest() == stored


def has_pin() -> bool:
    return get_setting("pin_hash") is not None


# ─── Основные операции с записями ─────────────────────────────────────────

def add_entry(category: str, title: str, content: str, tags: str = "") -> int:
    now = datetime.now().isoformat()
    title_enc = encrypt(title, config.MASTER_PASSWORD)
    content_enc = encrypt(content, config.MASTER_PASSWORD)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT INTO vault (category, title_encrypted, content_encrypted, created_at, updated_at, tags)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (category, title_enc, content_enc, now, now, tags)
    )
    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Добавлена запись #{entry_id} в категорию '{category}'")
    return entry_id


def update_entry(entry_id: int, content: str):
    now = datetime.now().isoformat()
    content_enc = encrypt(content, config.MASTER_PASSWORD)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'UPDATE vault SET content_encrypted = ?, updated_at = ? WHERE id = ?',
        (content_enc, now, entry_id)
    )
    conn.commit()
    conn.close()
    logger.info(f"Обновлена запись #{entry_id}")


def get_entries_by_category(category: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, title_encrypted, created_at, is_favorite FROM vault WHERE category = ? ORDER BY created_at DESC',
        (category,)
    )
    rows = c.fetchall()
    conn.close()
    result = []
    for row in rows:
        try:
            title = decrypt(row[1], config.MASTER_PASSWORD)
            result.append({
                "id": row[0],
                "title": title,
                "created_at": row[2],
                "is_favorite": bool(row[3]),
            })
        except Exception:
            logger.error(f"Не удалось расшифровать запись #{row[0]}")
    return result


def get_entry_by_id(entry_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, category, title_encrypted, content_encrypted, created_at, is_favorite, tags FROM vault WHERE id = ?',
        (entry_id,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    try:
        return {
            "id": row[0],
            "category": row[1],
            "title": decrypt(row[2], config.MASTER_PASSWORD),
            "content": decrypt(row[3], config.MASTER_PASSWORD),
            "created_at": row[4],
            "is_favorite": bool(row[5]),
            "tags": row[6] or "",
        }
    except Exception:
        logger.error(f"Не удалось расшифровать запись #{entry_id}")
        return None


def delete_entry(entry_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM vault WHERE id = ?', (entry_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Удалена запись #{entry_id}")
    return deleted


def toggle_favorite(entry_id: int) -> bool:
    """Переключает избранное, возвращает новое состояние."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT is_favorite FROM vault WHERE id = ?', (entry_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    new_val = 0 if row[0] else 1
    c.execute('UPDATE vault SET is_favorite = ? WHERE id = ?', (new_val, entry_id))
    conn.commit()
    conn.close()
    return bool(new_val)


def get_favorites() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, category, title_encrypted, created_at FROM vault WHERE is_favorite = 1 ORDER BY created_at DESC'
    )
    rows = c.fetchall()
    conn.close()
    result = []
    for row in rows:
        try:
            title = decrypt(row[2], config.MASTER_PASSWORD)
            result.append({
                "id": row[0],
                "category": row[1],
                "title": title,
                "created_at": row[3],
            })
        except Exception:
            continue
    return result


def search_entries(query: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, category, title_encrypted, content_encrypted, tags FROM vault')
    rows = c.fetchall()
    conn.close()
    query_lower = query.lower()
    results = []
    for row in rows:
        try:
            title = decrypt(row[2], config.MASTER_PASSWORD)
            content = decrypt(row[3], config.MASTER_PASSWORD)
            if query_lower in title.lower() or query_lower in content.lower():
                results.append({"id": row[0], "category": row[1], "title": title})
        except Exception:
            continue
    return results


def search_by_tag(tag: str) -> list:
    tag_lower = tag.lower().strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, category, title_encrypted, tags FROM vault')
    rows = c.fetchall()
    conn.close()
    results = []
    for row in rows:
        tags = [t.strip().lower() for t in (row[3] or "").split(",") if t.strip()]
        if tag_lower in tags:
            try:
                title = decrypt(row[2], config.MASTER_PASSWORD)
                results.append({"id": row[0], "category": row[1], "title": title})
            except Exception:
                continue
    return results


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT category, COUNT(*) FROM vault GROUP BY category')
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


# ─── Бэкап / восстановление ───────────────────────────────────────────────

def export_all_encrypted() -> list:
    """Возвращает список всех зашифрованных строк как есть (для бэкапа)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, category, title_encrypted, content_encrypted, created_at, updated_at, is_favorite, tags FROM vault'
    )
    rows = c.fetchall()
    conn.close()
    keys = ["id", "category", "title_encrypted", "content_encrypted",
            "created_at", "updated_at", "is_favorite", "tags"]
    return [dict(zip(keys, row)) for row in rows]


def import_from_backup(records: list) -> int:
    """Вставляет записи из бэкапа, пропускает дубликаты по id."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    inserted = 0
    for r in records:
        c.execute('SELECT id FROM vault WHERE id = ?', (r["id"],))
        if c.fetchone():
            continue
        c.execute(
            '''INSERT INTO vault (id, category, title_encrypted, content_encrypted,
               created_at, updated_at, is_favorite, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (r["id"], r["category"], r["title_encrypted"], r["content_encrypted"],
             r["created_at"], r["updated_at"], r.get("is_favorite", 0), r.get("tags", ""))
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted
