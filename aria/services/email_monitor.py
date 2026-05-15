"""IMAP email monitoring — polls inbox and forwards new messages to Telegram."""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
from email.header import decode_header as _decode_hdr
from typing import Any

import aria.db.repo as repo

log = logging.getLogger(__name__)


# ── Header / body helpers ─────────────────────────────────────────────────────

def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for raw, enc in _decode_hdr(value):
        if isinstance(raw, bytes):
            parts.append(raw.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(str(raw))
    return "".join(parts)


def _get_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


# ── IMAP sync helpers (run in thread) ─────────────────────────────────────────

def _get_highest_uid(imap: imaplib.IMAP4_SSL, folder: str) -> str | None:
    imap.select(folder, readonly=True)
    status, data = imap.uid("SEARCH", None, "ALL")
    uids = data[0].split() if data and data[0] else []
    return uids[-1].decode() if uids else None


def _fetch_since_uid(
    host: str, port: int, user: str, password: str, folder: str, last_uid: str
) -> list[tuple[str, str, str, str]]:
    """Return list of (uid, sender, subject, body) for emails with UID > last_uid."""
    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
        imap.select(folder, readonly=True)
        next_uid = int(last_uid) + 1
        status, data = imap.uid("SEARCH", None, f"UID {next_uid}:*")
        raw_uids = data[0].split() if data and data[0] else []
        # Guard: IMAP may return last_uid itself when range is empty
        raw_uids = [u for u in raw_uids if u.decode() != last_uid]
        results = []
        for uid_bytes in raw_uids[-10:]:  # max 10 per poll
            status2, msg_data = imap.uid("FETCH", uid_bytes, "(RFC822)")
            if not msg_data or not isinstance(msg_data[0], tuple):
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            results.append((
                uid_bytes.decode(),
                _decode_header(msg.get("From", "?")),
                _decode_header(msg.get("Subject", "(без темы)")),
                _get_body(msg)[:400].strip(),
            ))
        return results
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def _init_uid(
    host: str, port: int, user: str, password: str, folder: str
) -> str | None:
    """Login and return the current highest UID without fetching messages."""
    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
        return _get_highest_uid(imap, folder)
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ── Public API ────────────────────────────────────────────────────────────────

async def check_email(tenant_id: int, bot: Any) -> int:
    """Poll inbox and forward new emails to owner. Returns count forwarded."""
    import html as _html

    row = await repo.get_tenant(tenant_id)
    if not row:
        return 0

    host      = row.get("email_host")
    port      = int(row.get("email_port") or 993)
    user      = row.get("email_user")
    password  = row.get("email_password")
    folder    = row.get("email_folder") or "INBOX"
    owner_id  = row.get("owner_tg_id")
    last_uid  = row.get("email_last_uid")

    if not (host and user and password and owner_id):
        return 0

    # First poll: record current state, send nothing
    if last_uid is None:
        try:
            uid = await asyncio.to_thread(_init_uid, host, port, user, password, folder)
            if uid:
                await repo.update_tenant(tenant_id, email_last_uid=uid)
        except Exception as exc:
            log.warning("Email init failed for tenant %d: %s", tenant_id, exc)
        return 0

    try:
        messages = await asyncio.to_thread(
            _fetch_since_uid, host, port, user, password, folder, last_uid
        )
    except Exception as exc:
        log.warning("Email poll failed for tenant %d: %s", tenant_id, exc)
        return 0

    if not messages:
        return 0

    new_uid = None
    for uid_str, sender, subject, body in messages:
        text = (
            f"📧 <b>Новое письмо</b>\n\n"
            f"<b>От:</b> {_html.escape(sender[:120])}\n"
            f"<b>Тема:</b> {_html.escape(subject[:200])}\n\n"
            f"{_html.escape(body) if body else '<i>письмо без текста</i>'}"
        )
        try:
            await bot.send_message(chat_id=owner_id, text=text)
        except Exception as exc:
            log.warning("Failed to deliver email to %d: %s", owner_id, exc)
        new_uid = uid_str

    if new_uid:
        await repo.update_tenant(tenant_id, email_last_uid=new_uid)

    log.info("Forwarded %d email(s) for tenant %d", len(messages), tenant_id)
    return len(messages)


async def _poll_job(tenant_id: int, bot: Any) -> None:
    try:
        await check_email(tenant_id, bot)
    except Exception:
        log.exception("Email poll job failed for tenant %d", tenant_id)


def start_email_job(tenant_id: int, bot: Any) -> None:
    from apscheduler.triggers.interval import IntervalTrigger
    from aria.services.scheduler import get_scheduler
    get_scheduler().add_job(
        _poll_job,
        trigger=IntervalTrigger(minutes=5),
        id=f"email_{tenant_id}",
        replace_existing=True,
        args=[tenant_id, bot],
    )
    log.info("Email polling started for tenant %d (every 5 min)", tenant_id)


def stop_email_job(tenant_id: int) -> None:
    from aria.services.scheduler import get_scheduler
    try:
        get_scheduler().remove_job(f"email_{tenant_id}")
        log.info("Email polling stopped for tenant %d", tenant_id)
    except Exception:
        pass


def detect_imap_host(email_addr: str) -> str:
    domain = email_addr.split("@")[-1].lower()
    return {
        "gmail.com":        "imap.gmail.com",
        "googlemail.com":   "imap.gmail.com",
        "yandex.ru":        "imap.yandex.ru",
        "yandex.com":       "imap.yandex.ru",
        "ya.ru":            "imap.yandex.ru",
        "mail.ru":          "imap.mail.ru",
        "bk.ru":            "imap.mail.ru",
        "list.ru":          "imap.mail.ru",
        "inbox.ru":         "imap.mail.ru",
        "outlook.com":      "outlook.office365.com",
        "hotmail.com":      "outlook.office365.com",
        "live.com":         "outlook.office365.com",
        "icloud.com":       "imap.mail.me.com",
    }.get(domain, "")
