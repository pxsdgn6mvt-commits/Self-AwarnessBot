"""IMAP email monitoring — polls inbox and forwards new messages to Telegram."""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
from email.header import decode_header as _decode_hdr
from typing import Any

log = logging.getLogger(__name__)

import aria.db.repo as repo


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

def _imap_connect(host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
    """Open IMAP SSL connection with UTF-8-safe authentication."""
    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
    except (UnicodeEncodeError, UnicodeDecodeError):
        # imaplib.login() only supports ASCII; fall back to AUTHENTICATE PLAIN
        auth_data = b"\0" + user.encode("utf-8") + b"\0" + password.encode("utf-8")
        imap.authenticate("PLAIN", lambda _: auth_data)
    return imap


def _get_highest_uid(imap: imaplib.IMAP4_SSL, folder: str) -> str | None:
    imap.select(folder, readonly=True)
    status, data = imap.uid("SEARCH", None, "ALL")
    uids = data[0].split() if data and data[0] else []
    return uids[-1].decode() if uids else None


def _fetch_since_uid(
    host: str, port: int, user: str, password: str, folder: str, last_uid: str
) -> list[tuple[str, str, str, str]]:
    """Return list of (uid, sender, subject, body) for emails with UID > last_uid."""
    imap = _imap_connect(host, port, user, password)
    try:
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
    imap = _imap_connect(host, port, user, password)
    try:
        return _get_highest_uid(imap, folder)
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ── Filter ────────────────────────────────────────────────────────────────────

def passes_filter(
    filter_type: str, filter_value: str | None,
    sender: str, subject: str, body: str,
) -> bool:
    if not filter_type or filter_type == "all" or not filter_value:
        return True
    terms = [t.strip().lower() for t in filter_value.split(",") if t.strip()]
    if not terms:
        return True
    if filter_type == "keywords":
        haystack = (subject + " " + body).lower()
        return any(t in haystack for t in terms)
    if filter_type == "senders":
        sender_lower = sender.lower()
        return any(t in sender_lower for t in terms)
    return True


# ── Public API ────────────────────────────────────────────────────────────────

async def check_email(tenant_id: int, bot: Any) -> int:
    """Poll inbox and forward new emails to owner. Returns count forwarded."""
    import html as _html

    row = await repo.get_tenant(tenant_id)
    if not row:
        return 0

    host         = row.get("email_host")
    port         = int(row.get("email_port") or 993)
    user         = row.get("email_user")
    password     = row.get("email_password")
    folder       = row.get("email_folder") or "INBOX"
    owner_id     = row.get("owner_tg_id")
    last_uid     = row.get("email_last_uid")
    filter_type  = row.get("email_filter_type") or "all"
    filter_value = row.get("email_filter_value")

    if not (host and user and password and owner_id):
        return 0

    # First poll: record current state, send nothing (raises on connection error)
    if last_uid is None:
        uid = await asyncio.to_thread(_init_uid, host, port, user, password, folder)
        if uid:
            await repo.update_tenant(tenant_id, email_last_uid=uid)
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

    forwarded = 0
    highest_uid = None
    for uid_str, sender, subject, body in messages:
        highest_uid = uid_str  # always advance UID pointer, even for filtered messages
        if not passes_filter(filter_type, filter_value, sender, subject, body):
            continue
        text = (
            f"📧 <b>Новое письмо</b>\n\n"
            f"<b>От:</b> {_html.escape(sender[:120])}\n"
            f"<b>Тема:</b> {_html.escape(subject[:200])}\n\n"
            f"{_html.escape(body) if body else '<i>письмо без текста</i>'}"
        )
        try:
            await bot.send_message(chat_id=owner_id, text=text)
            forwarded += 1
        except Exception as exc:
            log.warning("Failed to deliver email to %d: %s", owner_id, exc)

    if highest_uid:
        await repo.update_tenant(tenant_id, email_last_uid=highest_uid)

    log.info("Polled %d email(s), forwarded %d for tenant %d", len(messages), forwarded, tenant_id)
    return forwarded


async def _poll_job(tenant_id: int, bot: Any) -> None:
    try:
        await check_email(tenant_id, bot)
    except Exception as exc:
        log.warning("Email poll job error for tenant %d: %s", tenant_id, exc)


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
