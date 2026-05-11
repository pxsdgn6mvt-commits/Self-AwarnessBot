import sqlite3
import logging
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
        updated_at TEXT NOT NULL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_vault_category ON vault(category)')
    conn.commit()
    conn.close()
    logger.info("БД инициализирована")


def add_entry(category: str, title: str, content: str) -> int:
    now = datetime.now().isoformat()
    title_enc = encrypt(title, config.MASTER_PASSWORD)
    content_enc = encrypt(content, config.MASTER_PASSWORD)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT INTO vault (category, title_encrypted, content_encrypted, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)''',
        (category, title_enc, content_enc, now, now)
    )
    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Добавлена запись #{entry_id} в категорию '{category}'")
    return entry_id


def get_entries_by_category(category: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, title_encrypted, created_at FROM vault WHERE category = ? ORDER BY created_at DESC',
        (category,)
    )
    rows = c.fetchall()
    conn.close()
    result = []
    for row in rows:
        try:
            title = decrypt(row[1], config.MASTER_PASSWORD)
            result.append({"id": row[0], "title": title, "created_at": row[2]})
        except Exception:
            logger.error(f"Не удалось расшифровать запись #{row[0]}")
    return result


def get_entry_by_id(entry_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, category, title_encrypted, content_encrypted, created_at FROM vault WHERE id = ?',
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


def search_entries(query: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, category, title_encrypted, content_encrypted FROM vault')
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


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT category, COUNT(*) FROM vault GROUP BY category')
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}
