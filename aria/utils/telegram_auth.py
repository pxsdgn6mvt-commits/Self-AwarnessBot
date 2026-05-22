"""Telegram WebApp initData HMAC-SHA256 verification.

Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import parse_qsl


def verify_telegram_webapp(init_data: str, bot_token: str) -> bool:
    """Return True if initData signature is valid for the given bot_token.

    Set env TELEGRAM_WEBAPP_SKIP_AUTH=true to bypass verification in dev/test.
    """
    if os.getenv("TELEGRAM_WEBAPP_SKIP_AUTH", "").lower() == "true":
        return True

    if not init_data or not bot_token:
        return False

    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = params.pop("hash", None)
        if not received_hash:
            return False

        check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

        return hmac.compare_digest(calculated, received_hash)
    except Exception:
        return False
