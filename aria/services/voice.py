"""Voice message transcription via OpenAI Whisper."""
from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger(__name__)

_LANG_MAP = {"ru": "ru", "en": "en", "fi": "fi"}


async def transcribe(bot: "Bot", file_id: str, lang: str = "ru") -> Optional[str]:
    """Download a Telegram voice message and transcribe it with Whisper.

    Returns transcribed text, or None if disabled / failed.
    """
    from aria.config import settings

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        log.warning("OPENAI_API_KEY not set — voice transcription disabled")
        return None

    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, buf)
        buf.seek(0)
        buf.name = "voice.ogg"
    except Exception as exc:
        log.error("Failed to download voice file %s: %s", file_id, exc)
        return None

    import openai

    client = openai.AsyncOpenAI(api_key=api_key)
    try:
        result = await client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            language=_LANG_MAP.get(lang, "ru"),
        )
        text = result.text.strip()
        return text or None
    except Exception as exc:
        log.error("Whisper transcription failed: %s", exc)
        return None
