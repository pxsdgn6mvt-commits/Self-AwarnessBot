from __future__ import annotations
import os
from typing import Optional


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Required env var {key!r} is not set")
    return val


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _str(key: str, default: str = "") -> str:
    return os.getenv(key, default)


class Settings:
    # ── Global infrastructure ─────────────────────────────────────────────
    DATABASE_URL: str
    ANTHROPIC_API_KEY: str       # shared fallback; tenants can override per-row
    ADMIN_TELEGRAM_ID: int       # your personal Telegram ID — full admin access

    # ── Initial tenant seed ───────────────────────────────────────────────
    # Used on first startup to auto-create the initial tenant from env vars.
    # After that, new tenants are added via /add_bot admin command.
    BOT_TOKEN: str
    OWNER_TELEGRAM_ID: int
    SALON_NAME: str
    OWNER_NAME: str
    SALON_SERVICES: str
    SALON_HOURS: str
    SALON_OPEN_HOUR: int
    SALON_CLOSE_HOUR: int
    SALON_SLOT_MINUTES: int
    SALON_WORKING_DAYS: str
    GOOGLE_CALENDAR_CREDENTIALS: Optional[str]
    GOOGLE_CALENDAR_ID: Optional[str]

    def __init__(self) -> None:
        self.DATABASE_URL = (
            _str("ARIA_DATABASE_URL") or _str("DATABASE_URL", "postgresql://localhost/aria_salon")
        )
        self.ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
        self.ADMIN_TELEGRAM_ID = _int("ARIA_OWNER_TELEGRAM_ID", 0)

        self.BOT_TOKEN = _require("ARIA_BOT_TOKEN")
        self.OWNER_TELEGRAM_ID = _int("ARIA_OWNER_TELEGRAM_ID", 0)
        self.SALON_NAME = _str("SALON_NAME", "My Salon")
        self.OWNER_NAME = _str("SALON_OWNER_NAME", "Owner")
        self.SALON_SERVICES = _str("SALON_SERVICES", "haircut, manicure")
        self.SALON_HOURS = _str("SALON_HOURS", "Mon-Sat 10:00-20:00")
        self.SALON_OPEN_HOUR = _int("SALON_OPEN_HOUR", 10)
        self.SALON_CLOSE_HOUR = _int("SALON_CLOSE_HOUR", 20)
        self.SALON_SLOT_MINUTES = _int("SALON_SLOT_MINUTES", 60)
        self.SALON_WORKING_DAYS = _str("SALON_WORKING_DAYS", "1,2,3,4,5,6")
        self.GOOGLE_CALENDAR_CREDENTIALS = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
        self.GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
        # Webhook mode: set WEBHOOK_BASE_URL to your Railway public domain.
        # Accepted forms:
        #   https://aria-bot.up.railway.app   (full URL)
        #   aria-bot.up.railway.app           (auto-prepends https://)
        raw_url = _str("WEBHOOK_BASE_URL", "").strip().rstrip("/")
        if raw_url and not raw_url.startswith("http"):
            raw_url = "https://" + raw_url
        self.WEBHOOK_BASE_URL = raw_url
        self.WEBHOOK_SECRET = _str("WEBHOOK_SECRET", "")


settings = Settings()
