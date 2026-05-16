"""
IMAP email monitor for Aria.

Polls a mailbox for new unread messages from allowed senders, passes
them through the AI chat service, and forwards the reply to the owner.

Key design decisions that avoid common failure modes:
  - Uses ssl.create_default_context() — no certificate warnings / MITM risk
  - Short-lived connections — connect → fetch → logout each poll cycle.
    Avoids the "connection gone stale" bug that haunts long-lived IMAP sessions.
  - UID-based fetch — safe to re-run; won't re-process already-read mail.
  - Charset-aware decode for Subject / body — handles UTF-8, KOI8-R, etc.
  - Exponential backoff on failure — won't hammer a broken server.
  - Runs in executor thread — imaplib is blocking; this keeps asyncio healthy.

Gmail setup:
  1. Gmail Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP
  2. Google Account → Security → 2-Step Verification (must be on)
  3. Google Account → Security → App passwords → create one for "Mail"
  4. Use that 16-char app password as ARIA_BOT_N_EMAIL_PASSWORD
     (your regular Google password will NOT work)

Other providers:
  Outlook/Hotmail  imap.outlook.com : 993
  Yahoo Mail       imap.mail.yahoo.com : 993
  Custom / cPanel  ask your host for IMAP server + port
"""

from __future__ import annotations

import asyncio
import email as _email_lib
import imaplib
import logging
import ssl
from email.header import decode_header as _rfc2047_decode
from email.utils import parseaddr
from typing import Optional

from aiogram import Bot

from aria.config import TenantConfig
from aria.services.ai import chat

log = logging.getLogger(__name__)

# Retry delays (seconds) after consecutive failures: 5s → 15s → 30s → 1m → 2m → 5m
_RETRY_DELAYS = (5, 15, 30, 60, 120, 300)


# ── Email parsing helpers ──────────────────────────────────────────────────────

def _safe_decode(fragment: str | bytes | None, charset: str | None) -> str:
    if fragment is None:
        return ""
    if isinstance(fragment, bytes):
        for enc in (charset, "utf-8", "latin-1"):
            if enc:
                try:
                    return fragment.decode(enc, errors="replace")
                except LookupError:
                    continue
        return fragment.decode("utf-8", errors="replace")
    return fragment


def _decode_header(raw: str | None) -> str:
    """Decode RFC 2047-encoded header (Subject, From, …)."""
    if not raw:
        return ""
    return "".join(
        _safe_decode(frag, charset)
        for frag, charset in _rfc2047_decode(raw)
    )


def _extract_text(msg: _email_lib.message.Message) -> str:
    """Return the first text/plain part (handles multipart, attachments, etc.)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return _safe_decode(payload, part.get_content_charset())
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        return _safe_decode(payload, msg.get_content_charset())
    return ""


# ── IMAP operations (blocking — called via run_in_executor) ───────────────────

def _connect(server: str, port: int, address: str, password: str) -> imaplib.IMAP4_SSL:
    """
    Open a fresh SSL connection and login.

    Uses ssl.create_default_context() so:
      - Certificate chain is verified (no MITM risk)
      - Modern TLS version is negotiated automatically
    Raises imaplib.IMAP4.error on bad credentials (distinguishable from
    network errors so callers can decide whether to retry).
    """
    ctx = ssl.create_default_context()
    conn = imaplib.IMAP4_SSL(server, port, ssl_context=ctx)
    conn.login(address, password)   # raises IMAP4.error on wrong password
    return conn


def _fetch_unseen(
    conn: imaplib.IMAP4_SSL,
    allowed: set[str],
    since_str: Optional[str] = None,
) -> list[tuple[bytes, str, str]]:
    """
    Search INBOX for unread messages received on or after *since_str*
    (IMAP date format "16-May-2026"), filter by allowed senders, and
    return [(uid_bytes, subject, body)].

    `since_str` is set to today when the owner configures email, so pre-existing
    inbox messages are never processed — only mail that arrives after setup.

    Emails from disallowed senders have their \\Seen flag reverted so they
    remain visible if the allow-list is widened later.
    """
    conn.select("INBOX", readonly=False)
    criteria = f"UNSEEN SINCE {since_str}" if since_str else "UNSEEN"
    _, data = conn.uid("search", None, criteria)
    if not data or not data[0]:
        return []

    results: list[tuple[bytes, str, str]] = []

    for uid in data[0].split():
        # Fetch only the envelope + text parts, not full message with attachments
        _, msg_data = conn.uid("fetch", uid, "(RFC822)")
        if not msg_data or not isinstance(msg_data[0], tuple):
            continue
        raw = msg_data[0][1]
        if not isinstance(raw, bytes):
            continue

        msg = _email_lib.message_from_bytes(raw)
        _, sender = parseaddr(msg.get("From", ""))
        sender = sender.lower().strip()

        if allowed and sender not in allowed:
            # Revert SEEN flag so we see it again if allow-list changes
            conn.uid("store", uid, "-FLAGS", "(\\Seen)")
            continue

        subject = _decode_header(msg.get("Subject"))
        body = _extract_text(msg)
        results.append((uid, subject, body))

    return results


# ── Single poll cycle ──────────────────────────────────────────────────────────

async def _poll_once(tenant: TenantConfig, bot: Bot, allowed: set[str]) -> None:
    loop = asyncio.get_event_loop()

    conn: Optional[imaplib.IMAP4_SSL] = None
    try:
        conn = await loop.run_in_executor(
            None,
            _connect,
            tenant.email_imap_server,
            tenant.email_imap_port,
            tenant.email_address,
            tenant.email_password,
        )
        messages = await loop.run_in_executor(None, _fetch_unseen, conn, allowed)
    finally:
        if conn:
            try:
                conn.logout()
            except Exception:
                pass

    owner_id = await _get_owner_id(tenant)

    for uid, subject, body in messages:
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        log.info(
            "tenant #%d: new email uid=%s from subject=%r",
            tenant.tenant_id, uid_str, subject,
        )
        text = f"[Email] Тема: {subject}\n\n{body[:2000]}".strip()
        try:
            reply, _ = await chat(
                user_id=owner_id or tenant.tenant_id,
                user_text=text,
                bot=bot,
                tenant=tenant,
            )
            if owner_id:
                await bot.send_message(
                    chat_id=owner_id,
                    text=f"📧 <b>Новое письмо:</b> {subject}\n\n{reply}",
                    parse_mode="HTML",
                )
        except Exception:
            log.exception(
                "tenant #%d: failed to process email uid=%s", tenant.tenant_id, uid_str
            )


async def _get_owner_id(tenant: TenantConfig) -> Optional[int]:
    """Resolve owner Telegram ID from DB or env var."""
    try:
        import aria.db.repo as repo
        db_owner = await repo.get_tenant_owner(tenant.tenant_id)
        if db_owner:
            return db_owner
    except Exception:
        pass
    return tenant.owner_telegram_id or None


# ── Main monitor loop ──────────────────────────────────────────────────────────

async def _load_settings(
    tenant: TenantConfig,
) -> tuple[str, str, str, int, set[str], int, Optional[str]] | None:
    """
    Load email settings from DB first, fall back to env vars.
    Returns (address, password, imap_server, imap_port, allowed_set, poll_seconds, since_str)
    or None if email is not configured.
    """
    import aria.db.repo as repo
    try:
        row = await repo.get_email_settings(tenant.tenant_id)
        if row and row["email_address"] and row["email_password"]:
            allowed = {
                s.strip().lower()
                for s in (row["email_allowed_senders"] or "").split(",")
                if s.strip()
            }
            since_str: Optional[str] = None
            try:
                since_str = row["email_since"] or None
            except (KeyError, IndexError):
                pass
            return (
                row["email_address"],
                row["email_password"],
                row["email_imap_server"] or "imap.gmail.com",
                row["email_imap_port"] or 993,
                allowed,
                row["email_poll_seconds"] or 60,
                since_str,
            )
    except Exception:
        pass

    # Fall back to env-var config (no since_str — process all unseen)
    if tenant.email_address and tenant.email_password:
        allowed = {
            s.strip().lower()
            for s in tenant.email_allowed_senders.split(",")
            if s.strip()
        }
        return (
            tenant.email_address, tenant.email_password,
            tenant.email_imap_server, tenant.email_imap_port,
            allowed, tenant.email_poll_seconds, None,
        )
    return None


async def run_email_monitor(tenant: TenantConfig, bot: Bot) -> None:
    """
    Long-running coroutine started for every tenant at boot.
    Re-reads DB settings on each cycle — picks up /admin changes within one poll interval.
    """
    log.info("tenant #%d: email monitor loop running (waiting for settings)", tenant.tenant_id)
    failure_streak = 0

    while True:
        cfg = await _load_settings(tenant)

        if cfg is None:
            # Not configured yet — check again in 60 s
            await asyncio.sleep(60)
            continue

        address, password, imap_server, imap_port, allowed, poll_seconds, since_str = cfg

        try:
            await _poll_once_with_cfg(tenant, bot, address, password,
                                      imap_server, imap_port, allowed, since_str)
            if failure_streak:
                log.info("tenant #%d: email monitor recovered", tenant.tenant_id)
            failure_streak = 0
        except imaplib.IMAP4.error as exc:
            log.error(
                "tenant #%d: IMAP auth error: %s  "
                "(Gmail needs an App Password, not your account password)",
                tenant.tenant_id, exc,
            )
            failure_streak = min(failure_streak + 2, len(_RETRY_DELAYS) - 1)
        except OSError as exc:
            log.warning("tenant #%d: IMAP network error: %s", tenant.tenant_id, exc)
            failure_streak = min(failure_streak + 1, len(_RETRY_DELAYS) - 1)
        except Exception as exc:
            log.exception("tenant #%d: email monitor error: %s", tenant.tenant_id, exc)
            failure_streak = min(failure_streak + 1, len(_RETRY_DELAYS) - 1)

        delay = _RETRY_DELAYS[failure_streak] if failure_streak else poll_seconds
        await asyncio.sleep(delay)


async def _poll_once_with_cfg(
    tenant: TenantConfig, bot: Bot,
    address: str, password: str,
    imap_server: str, imap_port: int,
    allowed: set[str],
    since_str: Optional[str] = None,
) -> None:
    loop = asyncio.get_event_loop()
    conn: Optional[imaplib.IMAP4_SSL] = None
    try:
        conn = await loop.run_in_executor(
            None, _connect, imap_server, imap_port, address, password
        )
        messages = await loop.run_in_executor(
            None, _fetch_unseen, conn, allowed, since_str
        )
    finally:
        if conn:
            try:
                conn.logout()
            except Exception:
                pass

    owner_id = await _get_owner_id(tenant)
    for uid, subject, body in messages:
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        log.info("tenant #%d: email uid=%s subject=%r", tenant.tenant_id, uid_str, subject)
        text = f"[Email] Тема: {subject}\n\n{body[:2000]}".strip()
        try:
            reply, _ = await chat(
                user_id=owner_id or tenant.tenant_id,
                user_text=text,
                bot=bot,
                tenant=tenant,
            )
            if owner_id:
                await bot.send_message(
                    chat_id=owner_id,
                    text=f"📧 <b>{subject}</b>\n\n{reply}",
                    parse_mode="HTML",
                )
        except Exception:
            log.exception("tenant #%d: failed to process email uid=%s", tenant.tenant_id, uid_str)
