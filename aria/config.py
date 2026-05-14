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
    # ── Telegram ──────────────────────────────────────────────
    BOT_TOKEN: str
    OWNER_TELEGRAM_ID: int

    # ── Anthropic ─────────────────────────────────────────────
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str

    # ── Salon identity ────────────────────────────────────────
    SALON_NAME: str
    OWNER_NAME: str
    SALON_SERVICES: str
    SALON_HOURS: str
    BOOKING_LINK: str
    ESCALATION_HOURS: int

    # ── Schedule grid ─────────────────────────────────────────
    SALON_OPEN_HOUR: int
    SALON_CLOSE_HOUR: int
    SALON_SLOT_MINUTES: int
    SALON_WORKING_DAYS: str   # e.g. "1,2,3,4,5,6"  (ISO: 1=Mon)

    # ── Google Calendar (optional) ────────────────────────────
    GOOGLE_CALENDAR_CREDENTIALS: Optional[str]
    GOOGLE_CALENDAR_ID: Optional[str]

    # ── Upsell pairs  "service1:upsell1,service2:upsell2" ─────
    UPSELL_PAIRS: str

    def __init__(self) -> None:
        self.BOT_TOKEN = _require("ARIA_BOT_TOKEN")
        self.OWNER_TELEGRAM_ID = _int("ARIA_OWNER_TELEGRAM_ID", 0)
        self.ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
        self.CLAUDE_MODEL = _str("ARIA_CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.DATABASE_URL = _str("ARIA_DATABASE_URL", "postgresql://localhost/aria_salon")

        self.SALON_NAME = _str("SALON_NAME", "Our Salon")
        self.OWNER_NAME = _str("SALON_OWNER_NAME", "the manager")
        self.SALON_SERVICES = _str(
            "SALON_SERVICES",
            "haircut, coloring, manicure, pedicure, facial"
        )
        self.SALON_HOURS = _str("SALON_HOURS", "Mon–Sat 10:00–20:00")
        self.BOOKING_LINK = _str("SALON_BOOKING_LINK", "")
        self.ESCALATION_HOURS = _int("SALON_ESCALATION_HOURS", 2)

        self.SALON_OPEN_HOUR = _int("SALON_OPEN_HOUR", 10)
        self.SALON_CLOSE_HOUR = _int("SALON_CLOSE_HOUR", 20)
        self.SALON_SLOT_MINUTES = _int("SALON_SLOT_MINUTES", 60)
        self.SALON_WORKING_DAYS = _str("SALON_WORKING_DAYS", "1,2,3,4,5,6")

        self.GOOGLE_CALENDAR_CREDENTIALS = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
        self.GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

        self.UPSELL_PAIRS = _str(
            "SALON_UPSELL_PAIRS",
            "haircut:coloring,manicure:pedicure,facial:massage"
        )

    @property
    def working_days(self) -> list[int]:
        return [int(d) for d in self.SALON_WORKING_DAYS.split(",") if d.strip()]

    @property
    def upsell_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for pair in self.UPSELL_PAIRS.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2:
                result[parts[0].strip().lower()] = parts[1].strip()
        return result

    def upsell_for(self, service: str) -> Optional[str]:
        return self.upsell_map.get(service.lower())


settings = Settings()
