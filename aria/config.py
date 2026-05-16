from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _int_env(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


@dataclass
class TenantConfig:
    """Per-bot configuration injected into every handler via aiogram DI."""
    bot_token: str
    tenant_id: int

    salon_name: str = "Our Salon"
    owner_name: str = "the manager"
    owner_telegram_id: int = 0

    salon_services: str = "haircut, coloring, manicure, pedicure, facial"
    salon_services_tree: str = ""   # "Cat[sub1,sub2];Cat2[sub3]"
    salon_hours: str = "Mon–Sat 10:00–20:00"
    booking_link: str = ""
    escalation_hours: int = 2
    max_services: int = 20
    salon_avatar_url: str = ""

    salon_open_hour: int = 10
    salon_close_hour: int = 20
    salon_slot_minutes: int = 60
    salon_working_days: str = "1,2,3,4,5,6"
    upsell_pairs: str = "haircut:coloring,manicure:pedicure,facial:massage"

    claude_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: str = ""
    database_url: str = ""

    @property
    def services_tree_dict(self) -> dict[str, list[str]]:
        raw = self.salon_services_tree.strip()
        if not raw:
            return {}
        result: dict[str, list[str]] = {}
        for chunk in raw.split(";"):
            chunk = chunk.strip()
            if "[" not in chunk or not chunk.endswith("]"):
                continue
            cat, rest = chunk.split("[", 1)
            subs = [s.strip() for s in rest[:-1].split(",") if s.strip()]
            if cat.strip() and subs:
                result[cat.strip()] = subs
        return result

    @property
    def working_days(self) -> list[int]:
        return [int(d) for d in self.salon_working_days.split(",") if d.strip()]

    def upsell_for(self, service: str) -> Optional[str]:
        for pair in self.upsell_pairs.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2 and parts[0].strip().lower() == service.lower():
                return parts[1].strip()
        return None


def _build_tenant(n: int, prefix: str) -> TenantConfig:
    def p(key: str, shared: str, default: str = "") -> str:
        return _env(f"{prefix}{key}", _env(shared, default))

    def pi(key: str, shared: str, default: int) -> int:
        raw = os.getenv(f"{prefix}{key}") or os.getenv(shared)
        return int(raw) if raw else default

    return TenantConfig(
        bot_token=_env(f"{prefix}TOKEN"),
        tenant_id=n,
        salon_name=p("SALON_NAME", "SALON_NAME", "Our Salon"),
        owner_name=p("OWNER_NAME", "SALON_OWNER_NAME", "the manager"),
        owner_telegram_id=pi("OWNER_ID", "ARIA_OWNER_TELEGRAM_ID", 0),
        salon_services=p("SERVICES", "SALON_SERVICES", "haircut, coloring, manicure"),
        salon_services_tree=p("SERVICES_TREE", "SALON_SERVICES_TREE", ""),
        salon_hours=p("HOURS", "SALON_HOURS", "Mon–Sat 10:00–20:00"),
        booking_link=p("BOOKING_LINK", "SALON_BOOKING_LINK", ""),
        escalation_hours=pi("ESCALATION_HOURS", "SALON_ESCALATION_HOURS", 2),
        max_services=pi("MAX_SERVICES", "SALON_MAX_SERVICES", 20),
        salon_avatar_url=p("AVATAR_URL", "SALON_AVATAR_URL", ""),
        salon_open_hour=pi("OPEN_HOUR", "SALON_OPEN_HOUR", 10),
        salon_close_hour=pi("CLOSE_HOUR", "SALON_CLOSE_HOUR", 20),
        salon_slot_minutes=pi("SLOT_MINUTES", "SALON_SLOT_MINUTES", 60),
        salon_working_days=p("WORKING_DAYS", "SALON_WORKING_DAYS", "1,2,3,4,5,6"),
        upsell_pairs=p("UPSELL_PAIRS", "SALON_UPSELL_PAIRS",
                       "haircut:coloring,manicure:pedicure,facial:massage"),
        claude_model=_env("ARIA_CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        database_url=_env("ARIA_DATABASE_URL", "postgresql://localhost/aria_salon"),
    )


def load_tenants() -> list[TenantConfig]:
    """
    Load all tenant configs from environment variables.

    Format A — numbered bots (multi-tenant):
      ARIA_BOT_1_TOKEN, ARIA_BOT_1_SALON_NAME, ARIA_BOT_1_OWNER_ID,
      ARIA_BOT_1_SERVICES_TREE, ...
      ARIA_BOT_2_TOKEN, ...

    Format B — legacy single bot:
      ARIA_BOT_TOKEN, SALON_NAME, ...

    Shared across all bots (used as defaults):
      ANTHROPIC_API_KEY, ARIA_DATABASE_URL, ARIA_CLAUDE_MODEL,
      SALON_MAX_SERVICES, SALON_OPEN_HOUR, SALON_CLOSE_HOUR, ...
    """
    tenants: list[TenantConfig] = []

    for i in range(1, 21):
        prefix = f"ARIA_BOT_{i}_"
        if not _env(f"{prefix}TOKEN"):
            continue
        tenants.append(_build_tenant(i, prefix))

    if not tenants:
        token = _env("ARIA_BOT_TOKEN")
        if token:
            t = _build_tenant(1, "ARIA_BOT_1_")
            t.bot_token = token
            tenants.append(t)

    return tenants


# Keep a global singleton for code that hasn't been migrated to DI yet
class _LegacySettings:
    """Backwards-compat shim — reads first tenant or env vars directly."""
    @property
    def BOT_TOKEN(self) -> str:
        return _env("ARIA_BOT_TOKEN")

    @property
    def OWNER_TELEGRAM_ID(self) -> int:
        return _int_env("ARIA_OWNER_TELEGRAM_ID", 0)

    @property
    def ANTHROPIC_API_KEY(self) -> str:
        return _env("ANTHROPIC_API_KEY")

    @property
    def CLAUDE_MODEL(self) -> str:
        return _env("ARIA_CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    @property
    def DATABASE_URL(self) -> str:
        return _env("ARIA_DATABASE_URL", "postgresql://localhost/aria_salon")

    @property
    def SALON_NAME(self) -> str:
        return _env("SALON_NAME", "Our Salon")

    @property
    def OWNER_NAME(self) -> str:
        return _env("SALON_OWNER_NAME", "the manager")

    @property
    def SALON_SERVICES(self) -> str:
        return _env("SALON_SERVICES", "haircut, coloring, manicure")

    @property
    def SALON_HOURS(self) -> str:
        return _env("SALON_HOURS", "Mon–Sat 10:00–20:00")

    @property
    def BOOKING_LINK(self) -> str:
        return _env("SALON_BOOKING_LINK", "")

    @property
    def ESCALATION_HOURS(self) -> int:
        return _int_env("SALON_ESCALATION_HOURS", 2)

    @property
    def SALON_OPEN_HOUR(self) -> int:
        return _int_env("SALON_OPEN_HOUR", 10)

    @property
    def SALON_CLOSE_HOUR(self) -> int:
        return _int_env("SALON_CLOSE_HOUR", 20)

    @property
    def SALON_SLOT_MINUTES(self) -> int:
        return _int_env("SALON_SLOT_MINUTES", 60)

    @property
    def SALON_WORKING_DAYS(self) -> str:
        return _env("SALON_WORKING_DAYS", "1,2,3,4,5,6")

    @property
    def GOOGLE_CALENDAR_CREDENTIALS(self) -> Optional[str]:
        return os.getenv("GOOGLE_CALENDAR_CREDENTIALS")

    @property
    def GOOGLE_CALENDAR_ID(self) -> Optional[str]:
        return os.getenv("GOOGLE_CALENDAR_ID")

    @property
    def UPSELL_PAIRS(self) -> str:
        return _env("SALON_UPSELL_PAIRS", "haircut:coloring,manicure:pedicure")

    @property
    def MAX_SERVICES(self) -> int:
        return _int_env("SALON_MAX_SERVICES", 20)

    @property
    def SALON_AVATAR_URL(self) -> str:
        return _env("SALON_AVATAR_URL", "")

    @property
    def SALON_SERVICES_TREE(self) -> str:
        return _env("SALON_SERVICES_TREE", "")

    @property
    def working_days(self) -> list[int]:
        return [int(d) for d in self.SALON_WORKING_DAYS.split(",") if d.strip()]

    @property
    def services_tree(self) -> dict[str, list[str]]:
        raw = self.SALON_SERVICES_TREE.strip()
        if not raw:
            return {}
        result: dict[str, list[str]] = {}
        for chunk in raw.split(";"):
            chunk = chunk.strip()
            if "[" not in chunk or not chunk.endswith("]"):
                continue
            cat, rest = chunk.split("[", 1)
            subs = [s.strip() for s in rest[:-1].split(",") if s.strip()]
            if cat.strip() and subs:
                result[cat.strip()] = subs
        return result

    def upsell_for(self, service: str) -> Optional[str]:
        for pair in self.UPSELL_PAIRS.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2 and parts[0].strip().lower() == service.lower():
                return parts[1].strip()
        return None


settings = _LegacySettings()
