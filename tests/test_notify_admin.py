"""Tests for aria/utils/notify_admin.py

Env vars used by notify_admin():
  ARIA_BOT_TOKEN  (fallback: BOT_TOKEN)
  ARIA_OWNER_TELEGRAM_ID  (fallback: OWNER_ID)
"""
from unittest.mock import patch

from aria.utils.notify_admin import notify_admin


def test_notify_admin_calls_telegram(monkeypatch):
    """urlopen is called when both env vars are present."""
    monkeypatch.setenv("ARIA_BOT_TOKEN", "test_token")
    monkeypatch.setenv("ARIA_OWNER_TELEGRAM_ID", "123456")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("OWNER_ID", raising=False)

    with patch("aria.utils.notify_admin._ur.urlopen") as mock_urlopen:
        notify_admin("test_context", Exception("test error"))
        assert mock_urlopen.called
        call_args = mock_urlopen.call_args[0][0]
        assert "test_token" in call_args.full_url
        assert b"test_context" in call_args.data


def test_notify_admin_no_env_vars(monkeypatch):
    """urlopen is NOT called when env vars are absent."""
    for var in ("ARIA_BOT_TOKEN", "BOT_TOKEN", "ARIA_OWNER_TELEGRAM_ID", "OWNER_ID"):
        monkeypatch.delenv(var, raising=False)

    with patch("aria.utils.notify_admin._ur.urlopen") as mock_urlopen:
        notify_admin("test_context", Exception("test error"))
        assert not mock_urlopen.called


def test_notify_admin_telegram_unavailable(monkeypatch):
    """Does not raise even when urlopen throws."""
    monkeypatch.setenv("ARIA_BOT_TOKEN", "test_token")
    monkeypatch.setenv("ARIA_OWNER_TELEGRAM_ID", "123456")

    with patch("aria.utils.notify_admin._ur.urlopen", side_effect=OSError("timeout")):
        notify_admin("test_context", Exception("test error"))  # must not raise
