"""TenantConfig — per-salon configuration loaded from aria_tenants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TenantConfig:
    id: int
    bot_token: str
    owner_tg_id: Optional[int]
    salon_name: str
    owner_name: str
    services: str
    hours: str
    open_hour: int
    close_hour: int
    slot_minutes: int
    working_days: str
    timezone: str
    google_cal_credentials: Optional[str]
    google_cal_id: Optional[str]
    anthropic_api_key: Optional[str]
    setup_complete: bool
    active: bool
    master_percent: Optional[float]
    tax_percent: Optional[float]
    reminder_hours_before: int
    daily_summary_hour: int

    @classmethod
    def from_record(cls, r: dict) -> "TenantConfig":
        return cls(
            id=r["id"],
            bot_token=r["bot_token"],
            owner_tg_id=r["owner_tg_id"],
            salon_name=r["salon_name"],
            owner_name=r["owner_name"],
            services=r["services"],
            hours=r["hours"],
            open_hour=r["open_hour"],
            close_hour=r["close_hour"],
            slot_minutes=r["slot_minutes"],
            working_days=r["working_days"],
            timezone=r.get("timezone", "UTC"),
            google_cal_credentials=r["google_cal_credentials"],
            google_cal_id=r["google_cal_id"],
            anthropic_api_key=r["anthropic_api_key"],
            setup_complete=r["setup_complete"],
            active=r["active"],
            master_percent=float(r["master_percent"]) if r.get("master_percent") is not None else None,
            tax_percent=float(r["tax_percent"]) if r.get("tax_percent") is not None else None,
            reminder_hours_before=int(r.get("reminder_hours_before") or 2),
            daily_summary_hour=int(r.get("daily_summary_hour") or 20),
        )

    @property
    def effective_api_key(self) -> str:
        from aria.config import settings
        return self.anthropic_api_key or settings.ANTHROPIC_API_KEY

    @property
    def working_days_list(self) -> list[int]:
        return [int(d) for d in self.working_days.split(",") if d.strip()]

    def is_owner(self, user_id: int) -> bool:
        return self.owner_tg_id is not None and self.owner_tg_id == user_id
