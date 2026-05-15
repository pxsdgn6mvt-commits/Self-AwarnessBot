"""PostgreSQL-backed FSM storage for aiogram 3.

Replaces MemoryStorage so FSM wizard states (email setup, booking wizard,
settings FSMs, etc.) survive bot restarts and Railway redeploys.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from aiogram.fsm.storage.base import BaseStorage, StorageKey

log = logging.getLogger(__name__)


def _key(key: StorageKey) -> str:
    destiny = getattr(key, "destiny", "")
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{destiny}"


class PostgresFSMStorage(BaseStorage):

    async def set_state(self, key: StorageKey, state: Optional[Any] = None) -> None:
        from aria.db.repo import _p
        state_str = str(state) if state is not None else None
        try:
            await _p().execute(
                """
                INSERT INTO aria_fsm_states (key, state)
                VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET state = EXCLUDED.state
                """,
                _key(key), state_str,
            )
            log.debug("FSM set_state key=%s state=%s", _key(key), state_str)
        except Exception:
            log.exception("FSM set_state failed for key=%s", _key(key))
            raise

    async def get_state(self, key: StorageKey) -> Optional[str]:
        from aria.db.repo import _p
        try:
            row = await _p().fetchrow(
                "SELECT state FROM aria_fsm_states WHERE key = $1", _key(key)
            )
            result = row["state"] if row else None
            log.debug("FSM get_state key=%s → %s", _key(key), result)
            return result
        except Exception:
            log.exception("FSM get_state failed for key=%s", _key(key))
            return None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        from aria.db.repo import _p
        try:
            await _p().execute(
                """
                INSERT INTO aria_fsm_states (key, data)
                VALUES ($1, $2::jsonb)
                ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data
                """,
                _key(key), json.dumps(data, default=str),
            )
        except Exception:
            log.exception("FSM set_data failed for key=%s", _key(key))
            raise

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        from aria.db.repo import _p
        try:
            row = await _p().fetchrow(
                "SELECT data FROM aria_fsm_states WHERE key = $1", _key(key)
            )
            if not row or not row["data"]:
                return {}
            raw = row["data"]
            return dict(raw) if not isinstance(raw, str) else json.loads(raw)
        except Exception:
            log.exception("FSM get_data failed for key=%s", _key(key))
            return {}

    async def close(self) -> None:
        pass  # pool lifecycle is managed by the application
