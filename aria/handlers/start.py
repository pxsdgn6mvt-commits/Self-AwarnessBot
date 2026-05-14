"""Handlers for /start, /help, /reset commands."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

import aria.db.repo as repo
from aria.config import settings
from aria.services.ai import chat

log = logging.getLogger(__name__)
router = Router()

# Welcome messages per Telegram language_code prefix
_WELCOME: dict[str, str] = {
    "ru": (
        "Привет! Я Aria, ваш персональный помощник в {salon}.\n\n"
        "Помогу записаться на приём, перенести визит, ответить на вопросы "
        "или добавить вас в лист ожидания.\n\n"
        "Чем могу помочь?"
    ),
    "fi": (
        "Hei! Olen Aria, henkilökohtainen assistenttisi {salon}-liikkeessä.\n\n"
        "Voin auttaa ajanvarauksessa, siirtämisessä tai jonotuslistalle lisäämisessä.\n\n"
        "Miten voin auttaa?"
    ),
    "de": (
        "Hallo! Ich bin Aria, Ihre persönliche Assistentin bei {salon}.\n\n"
        "Ich helfe Ihnen bei Buchungen, Umbuchungen oder der Warteliste.\n\n"
        "Wie kann ich helfen?"
    ),
    "fr": (
        "Bonjour! Je suis Aria, votre assistante personnelle chez {salon}.\n\n"
        "Je peux vous aider à prendre rendez-vous, modifier ou rejoindre la liste d'attente.\n\n"
        "Comment puis-je vous aider?"
    ),
    "es": (
        "¡Hola! Soy Aria, tu asistente personal en {salon}.\n\n"
        "Puedo ayudarte a reservar, reprogramar o unirte a la lista de espera.\n\n"
        "¿En qué puedo ayudarte?"
    ),
    "it": (
        "Ciao! Sono Aria, la tua assistente personale da {salon}.\n\n"
        "Posso aiutarti con prenotazioni, riprogrammazioni o lista d'attesa.\n\n"
        "Come posso aiutarti?"
    ),
    "nl": (
        "Hallo! Ik ben Aria, uw persoonlijke assistent bij {salon}.\n\n"
        "Ik help u met boekingen, verzettingen of de wachtlijst.\n\n"
        "Hoe kan ik u helpen?"
    ),
    "sv": (
        "Hej! Jag är Aria, din personliga assistent på {salon}.\n\n"
        "Jag kan hjälpa dig med bokningar, ombokningar eller väntelistan.\n\n"
        "Hur kan jag hjälpa dig?"
    ),
    "pl": (
        "Cześć! Jestem Aria, Twoja osobista asystentka w {salon}.\n\n"
        "Pomogę Ci zarezerwować wizytę, przełożyć lub dołączyć do listy oczekujących.\n\n"
        "Jak mogę pomóc?"
    ),
    "en": (
        "Hi! I'm Aria, your personal assistant at {salon}.\n\n"
        "I can help you book an appointment, reschedule, answer questions "
        "or join the waitlist if we're fully booked.\n\n"
        "Just tell me what you need."
    ),
}


def _welcome_for(lang_code: str | None) -> str:
    code = (lang_code or "en").split("-")[0].lower()
    msg = _WELCOME.get(code, _WELCOME["en"])
    return msg.format(salon=settings.SALON_NAME)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id
    lang_code = message.from_user.language_code or "en"

    await repo.upsert_client(user_id, lang_code)
    await repo.clear_history(user_id)

    # Seed conversation with a silent language hint so Claude knows from message 1
    lang_hint = (
        f"[System note: this client's Telegram language is '{lang_code}'. "
        f"Respond in that language from the very first message.]"
    )
    history = [{"role": "user", "content": lang_hint},
               {"role": "assistant", "content": "Understood."}]
    await repo.save_history(user_id, history)

    await message.answer(_welcome_for(lang_code))


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    await repo.clear_history(message.from_user.id)
    lang_code = message.from_user.language_code or "en"
    replies = {
        "ru": "Начнём заново — чем могу помочь?",
        "fi": "Aloitetaan alusta — miten voin auttaa?",
        "de": "Neu anfangen — wie kann ich helfen?",
    }
    code = lang_code.split("-")[0].lower()
    await message.answer(replies.get(code, "Fresh start — how can I help you?"))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    lang_code = (message.from_user.language_code or "en").split("-")[0].lower()
    texts = {
        "ru": (
            "Просто напишите мне — специальные команды не нужны.\n\n"
            "Вы можете:\n• Записаться на приём\n• Перенести или отменить\n"
            "• Узнать об услугах\n• Встать в лист ожидания\n\n"
            "/reset — начать новый разговор"
        ),
    }
    await message.answer(texts.get(lang_code, (
        "Just write me a message — no special commands needed.\n\n"
        "You can:\n• Book an appointment\n• Reschedule or cancel\n"
        "• Ask about our services\n• Join the waitlist\n\n"
        "/reset — start a new conversation"
    )))
