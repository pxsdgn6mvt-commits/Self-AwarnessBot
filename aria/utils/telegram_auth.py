import os
import time
import hmac
import hashlib
from urllib.parse import parse_qsl, unquote


def verify_telegram_webapp(init_data: str, bot_token: str) -> bool:
    if os.getenv("TELEGRAM_WEBAPP_SKIP_AUTH", "").lower() == "true":
        return True

    parsed = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
    hash_received = parsed.pop("hash", None)
    if not hash_received:
        return False

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, hash_received):
        return False

    try:
        auth_date = int(parsed.get("auth_date", 0))
        max_age = int(os.getenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "600"))
        if time.time() - auth_date > max_age:
            return False
    except (ValueError, TypeError):
        return False

    return True
