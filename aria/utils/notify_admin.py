from __future__ import annotations

import json as _json
import logging
import os
import urllib.request as _ur

log = logging.getLogger(__name__)


def notify_admin(context: str, error: Exception) -> None:
    """Send a Telegram message to the platform admin on critical error.

    Reads ARIA_BOT_TOKEN (fallback BOT_TOKEN) and
    ARIA_OWNER_TELEGRAM_ID (fallback OWNER_ID) from env.
    Silently skips if either is absent or Telegram is unreachable.
    """
    token    = os.getenv("ARIA_BOT_TOKEN", "") or os.getenv("BOT_TOKEN", "")
    admin_id = os.getenv("ARIA_OWNER_TELEGRAM_ID", "") or os.getenv("OWNER_ID", "")
    if not token or not admin_id:
        return
    text = f"🚨 Aria error in {context}:\n{type(error).__name__}: {error}"
    data = _json.dumps({"chat_id": admin_id, "text": text}).encode()
    req = _ur.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        _ur.urlopen(req, timeout=5)
    except Exception as exc:
        log.warning("notify_admin failed: %s", exc)
