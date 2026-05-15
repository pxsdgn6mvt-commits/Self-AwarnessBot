"""PostgreSQL-backed FSM storage for aiogram 3.

Replaces MemoryStorage so FSM wizard states (email setup, booking wizard,
settings FSMs, etc.) survive bot restarts and Railway redeploys.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from aiogram.fsm.storage.base import BaseStorage, StorageKey


def _key(key: StorageKey) -> str:
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"


class PostgresFSMStorage(BaseStorage):

    async def set_state(self, key: StorageKey, state: Optional[Any] = None) -> None:
        from aria.db.repo import _p
        state_str = str(state) if state is not None else None
        await _p().execute(
            """
            INSERT INTO aria_fsm_states (key, state)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET state = EXCLUDED.state
            """,
            _key(key), state_str,
        )

    async def get_state(self, key: StorageKey) -> Optional[str]:
        from aria.db.repo import _p
        row = await _p().fetchrow(
            "SELECT state FROM aria_fsm_states WHERE key = $1", _key(key)
        )
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        from aria.db.repo import _p
        await _p().execute(
            """
            INSERT INTO aria_fsm_states (key, data)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data
            """,
            _key(key), json.dumps(data, default=str),
        )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        from aria.db.repo import _p
        row = await _p().fetchrow(
            "SELECT data FROM aria_fsm_states WHERE key = $1", _key(key)
        )
        if not row or not row["data"]:
            return {}
        raw = row["data"]
        return dict(raw) if not isinstance(raw, str) else json.loads(raw)

    async def close(self) -> None:
        pass  # pool lifecycle is managed by the application
