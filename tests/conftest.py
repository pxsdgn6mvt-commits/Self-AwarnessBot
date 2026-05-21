import sys
from unittest.mock import MagicMock

import pytest


# Stub heavy dependencies that are unavailable in the test environment.
# Must happen before any aria.main import so module-level decorators don't fail.
_STUBS = [
    "aiogram", "aiogram.client", "aiogram.client.default", "aiogram.enums",
    "aiogram.exceptions", "aiogram.types", "aiogram.filters", "aiogram.fsm",
    "aiogram.fsm.context", "aiogram.fsm.state", "aiogram.fsm.storage",
    "aiogram.fsm.storage.base",
    "asyncpg",
    "apscheduler", "apscheduler.schedulers", "apscheduler.schedulers.asyncio",
    "apscheduler.triggers", "apscheduler.triggers.date",
    "apscheduler.triggers.cron", "apscheduler.triggers.interval",
    "aria.handlers", "aria.handlers.admin", "aria.handlers.chat",
    "aria.handlers.email_setup", "aria.handlers.menu", "aria.handlers.quick",
    "aria.handlers.start", "aria.handlers.setup",
    "aria.middleware", "aria.db.fsm_storage",
    "aria.services.commands", "aria.services.scheduler",
]

for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")
