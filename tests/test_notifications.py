"""Tests for aria/notifications.py."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from aria.notifications import (
    notify_owner_cancelled,
    notify_owner_new_booking,
    notify_owner_rescheduled,
)

pytestmark = pytest.mark.asyncio

DT = datetime(2024, 3, 15, 14, 30, tzinfo=timezone.utc)
DT2 = datetime(2024, 3, 16, 10, 0, tzinfo=timezone.utc)


def _mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


async def test_new_booking_sends_message():
    bot = _mock_bot()
    with patch("aria.notifications.get_tenant_bot", return_value=bot):
        await notify_owner_new_booking(1, 999, "Анна", "Стрижка", DT)
    bot.send_message.assert_awaited_once()
    text = bot.send_message.call_args[0][1]
    assert "Анна" in text
    assert "Стрижка" in text
    assert "15.03.2024" in text
    assert "14:30" in text


async def test_no_bot_returns_silently():
    with patch("aria.notifications.get_tenant_bot", return_value=None):
        await notify_owner_new_booking(1, 999, "Анна", "Стрижка", DT)


async def test_telegram_error_is_swallowed():
    from aiogram.exceptions import TelegramAPIError

    class _FakeError(TelegramAPIError):
        def __init__(self):
            self.message = "flood"
            Exception.__init__(self, "flood")

    bot = _mock_bot()
    bot.send_message.side_effect = _FakeError()
    with patch("aria.notifications.get_tenant_bot", return_value=bot):
        await notify_owner_new_booking(1, 999, "Анна", "Стрижка", DT)
    # no exception propagated


async def test_cancelled_message_correct():
    bot = _mock_bot()
    with patch("aria.notifications.get_tenant_bot", return_value=bot):
        await notify_owner_cancelled(1, 999, "Борис", "Маникюр", DT)
    text = bot.send_message.call_args[0][1]
    assert "Борис" in text
    assert "Маникюр" in text
    assert "отменена" in text.lower()
    assert "15.03.2024" in text


async def test_rescheduled_contains_both_datetimes():
    bot = _mock_bot()
    with patch("aria.notifications.get_tenant_bot", return_value=bot):
        await notify_owner_rescheduled(1, 999, "Вера", "Окраска", DT, DT2)
    text = bot.send_message.call_args[0][1]
    assert "15.03.2024" in text
    assert "14:30" in text
    assert "16.03.2024" in text
    assert "10:00" in text
