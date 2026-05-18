"""Catch-all message handler — routes to AI service.

Rule-based bypass fires first for simple schedule queries (no tokens spent).
The bypass uses the same adapter as keyboard buttons, so GCal sync is preserved:
events from external booking services (Yclients, Dikidi, etc.) appear correctly.
"""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from typing import Optional

import aria.db.repo as repo
from aria.i18n import t
from aria.services.ai import chat
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()

# in-memory rate limit: user_id → timestamps of last 60 s
_rate_windows: dict[int, list[float]] = {}
_RATE_LIMIT = 20  # messages per minute


# ── Rule-based bypass ─────────────────────────────────────────────────────────

# Words that mean the user wants to ADD/CHANGE a booking — must go to AI
_BOOKING_VERBS = [
    "запис", "добавь", "добавить", "перенес", "отмен",
    "свободн", "проверь", "убери", "удали",
]

# Trigger patterns → (days_offset for _show_schedule)
_DAY_PATTERNS: list[tuple[list[str], int]] = [
    (["сегодня", "сёгодня", "today"], 0),
    (["завтра",  "tomorrow"],         1),
]

_UPCOMING_TRIGGERS  = ["ближайш", "upcoming", "следующ запис"]
_THIS_WEEK_TRIGGERS = ["эта неделя", "эту неделю", "на неделе", "на этой нед", "неделя"]
_NEXT_WEEK_TRIGGERS = ["следующая неделя", "следующую неделю", "след неделя", "на следующей"]


def _has_booking_verb(text: str) -> bool:
    return any(kw in text for kw in _BOOKING_VERBS)


async def _schedule_bypass(message: Message, tenant: TenantConfig) -> bool:
    """
    Try to handle message without calling AI.
    Returns True if handled; caller should return immediately.

    Uses get_adapter(tenant) → GoogleAdapter when configured, so events from
    external booking services synced via GCal are included in the results.
    """
    text  = message.text.strip().lower()
    words = text.split()

    # Never bypass when the owner wants to mutate bookings
    if _has_booking_verb(text):
        return False

    # "сегодня" / "завтра" — short queries only (avoid "запиши на завтра в 14:00")
    if len(words) <= 6:
        for patterns, offset in _DAY_PATTERNS:
            if any(p in text for p in patterns):
                from aria.handlers.quick import _show_schedule
                await _show_schedule(message, tenant, offset)
                return True

    # "ближайшие" — any length (it's unambiguous)
    if any(p in text for p in _UPCOMING_TRIGGERS):
        from aria.handlers.quick import quick_upcoming
        await quick_upcoming(message, tenant)
        return True

    # "следующая неделя" before "эта неделя" (longer match first)
    if any(p in text for p in _NEXT_WEEK_TRIGGERS):
        from aria.handlers.menu import _show_week
        await _show_week(message, tenant, 1)
        return True

    if any(p in text for p in _THIS_WEEK_TRIGGERS):
        from aria.handlers.menu import _show_week
        await _show_week(message, tenant, 0)
        return True

    return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_rate_limit(user_id: int) -> bool:
    now = time.monotonic()
    window = _rate_windows.setdefault(user_id, [])
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= _RATE_LIMIT:
        return False
    window.append(now)
    return True


def _detect_style(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in [" вы ", " вас ", " вам ", "пожалуйста", "будьте добры"]):
        return "formal"
    if len(text.split()) < 5:
        return "terse"
    return "casual"


# ── Main handler ──────────────────────────────────────────────────────────────

@router.message()
async def handle_message(message: Message, bot: Bot, state: FSMContext, tenant: Optional[TenantConfig] = None) -> None:
    if not message.text or not tenant or not tenant.setup_complete:
        return

    try:
        current_state = await state.get_state()
    except Exception:
        current_state = None

    if current_state is not None:
        log.info(
            "FSM state active (%s) but no handler matched — message: %r",
            current_state, message.text[:40] if message.text else "",
        )
        return

    user_id = message.from_user.id

    if not _check_rate_limit(user_id):
        lang = (tenant.owner_lang or "ru") if tenant else "ru"
        await message.answer(t("rate_limit", lang))
        return

    # ── Rule-based bypass: no tokens for simple schedule queries ──────────────
    if await _schedule_bypass(message, tenant):
        log.debug("Bypass handled: %r", message.text[:40])
        return

    # ── AI path ───────────────────────────────────────────────────────────────
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    style = "casual"
    try:
        profile = await repo.get_client_profile(tenant.id, user_id)
        stored_style = (profile["communication_style"] if profile else None) or "casual"
        new_style = _detect_style(message.text)
        style = new_style
        if new_style != stored_style:
            asyncio.create_task(repo.update_client_style(tenant.id, user_id, new_style))
    except Exception:
        pass

    try:
        reply = await chat(
            user_id=user_id,
            user_text=message.text,
            bot=bot,
            tenant=tenant,
            style=style,
        )
    except Exception as exc:
        log.exception("AI error for tenant %d user %d: %s", tenant.id, user_id, exc)
        reply = t("ai_error", tenant.owner_lang or "ru")

    await message.answer(reply)
