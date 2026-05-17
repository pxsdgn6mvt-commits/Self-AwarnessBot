"""Filters based on per-tenant setup state."""

from __future__ import annotations

from aiogram.filters import BaseFilter


class SetupRequired(BaseFilter):
    """Passes only when the tenant's setup wizard is not yet complete."""
    async def __call__(self, event=None, **kwargs) -> bool:
        tenant = kwargs.get("tenant")
        return tenant is not None and not tenant.setup_complete


class SetupDone(BaseFilter):
    """Passes only when the tenant is fully configured."""
    async def __call__(self, event=None, **kwargs) -> bool:
        tenant = kwargs.get("tenant")
        return tenant is not None and tenant.setup_complete
