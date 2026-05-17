"""Shared runtime state — populated by main.py, readable from handlers."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

# tenant_id → Bot instance; kept in sync by main._watch_tenants
bots: dict[int, "Bot"] = {}
