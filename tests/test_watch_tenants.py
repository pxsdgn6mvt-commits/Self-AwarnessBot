"""Tests for email job resurrection logic in aria/main.py _watch_tenants."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_vip_tenant(has_email: bool = True) -> dict:
    return {
        "id": 1,
        "bot_token": "fake:token",
        "salon_name": "Test Salon",
        "email_user": "owner@gmail.com" if has_email else "",
        "email_host": "imap.gmail.com" if has_email else "",
        "is_vip": True,
        "vip_until": None,
    }


@pytest.mark.asyncio
async def test_email_job_registered_when_missing():
    """start_email_job is called when the scheduler has no job for this tenant."""
    tenant = _make_vip_tenant()
    mock_bot = MagicMock()
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = None  # job is missing

    call_count = 0

    async def mock_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    with patch("aria.main.list_active_tenants", new_callable=AsyncMock, return_value=[tenant]), \
         patch("aria.main.get_scheduler", return_value=mock_scheduler), \
         patch("aria.main.asyncio.sleep", side_effect=mock_sleep), \
         patch("aria.services.email_monitor.start_email_job") as mock_start_job, \
         patch.dict("aria.main._bots", {1: mock_bot}, clear=True), \
         patch.dict("aria.main._tasks", {1: MagicMock(done=MagicMock(return_value=False))}, clear=True):

        from aria.main import _watch_tenants
        try:
            await _watch_tenants(MagicMock())
        except asyncio.CancelledError:
            pass

        mock_start_job.assert_called_once_with(1, mock_bot)


@pytest.mark.asyncio
async def test_email_job_not_duplicated_when_exists():
    """start_email_job is NOT called when the scheduler already has the job."""
    tenant = _make_vip_tenant()
    mock_bot = MagicMock()
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = MagicMock()  # job already exists

    call_count = 0

    async def mock_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    with patch("aria.main.list_active_tenants", new_callable=AsyncMock, return_value=[tenant]), \
         patch("aria.main.get_scheduler", return_value=mock_scheduler), \
         patch("aria.main.asyncio.sleep", side_effect=mock_sleep), \
         patch("aria.services.email_monitor.start_email_job") as mock_start_job, \
         patch.dict("aria.main._bots", {1: mock_bot}, clear=True), \
         patch.dict("aria.main._tasks", {1: MagicMock(done=MagicMock(return_value=False))}, clear=True):

        from aria.main import _watch_tenants
        try:
            await _watch_tenants(MagicMock())
        except asyncio.CancelledError:
            pass

        mock_start_job.assert_not_called()
