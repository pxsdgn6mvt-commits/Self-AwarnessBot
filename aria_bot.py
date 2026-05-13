"""
Aria — AI administrator Telegram bot for beauty salons.
Powered by Claude API. Handles appointment reminders,
cancellations, and waitlist management.

Environment variables required:
  ARIA_BOT_TOKEN    — Telegram bot token (from @BotFather)
  ANTHROPIC_API_KEY — Anthropic API key

Deploy on Railway:
  1. Add this as a new Service in the same Railway project
  2. Start command: python aria_bot.py
  3. Set the two env variables above in Railway → Variables
"""

import os
import logging
import anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("aria_bot")

ARIA_SYSTEM_PROMPT = (
    "You are Aria, an AI administrator for a beauty salon. "
    "You help clients with: "
    "appointment scheduling and reminders, "
    "handling cancellations and rescheduling, "
    "waitlist management. "
    "Speak the language the client uses — Russian, Finnish, English, or German. "
    "Be warm, professional, and efficient. "
    "Keep replies concise. "
    "If you do not know the salon's specific schedule or prices, "
    "politely say you will check and ask the client to hold on."
)

# In-memory conversation store — maps user_id → list of message dicts
# Each message: {"role": "user"|"assistant", "content": "..."}
_conversations: dict[int, list[dict]] = {}

MAX_HISTORY = 20  # keep last 20 turns per user


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    _conversations.pop(user_id, None)  # fresh session on /start

    name = update.effective_user.first_name or "там"
    await update.message.reply_text(
        f"Привет, {name}! 👋 Я Ария — ваш AI-администратор салона красоты. 💅\n\n"
        "Я могу помочь с:\n"
        "• Записью на приём\n"
        "• Напоминаниями о визитах\n"
        "• Отменой и переносом записей\n"
        "• Листом ожидания\n\n"
        "Чем могу помочь?"
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _conversations.pop(update.effective_user.id, None)
    await update.message.reply_text("История диалога очищена. Начнём сначала! 😊")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — начать новый диалог\n"
        "/reset — очистить историю разговора\n"
        "/help  — это сообщение\n\n"
        "Просто напишите мне сообщение, и я отвечу!"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text    = update.message.text

    if user_id not in _conversations:
        _conversations[user_id] = []

    history = _conversations[user_id]
    history.append({"role": "user", "content": text})

    # Trim to avoid runaway costs
    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]

    # Show typing indicator while waiting for Claude
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=ARIA_SYSTEM_PROMPT,
            messages=history,
        )
        reply = response.content[0].text
        history.append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

    except RuntimeError as exc:
        log.error("Config error: %s", exc)
        await update.message.reply_text(
            "⚠️ Бот настроен неправильно. Пожалуйста, сообщите владельцу салона."
        )
    except Exception as exc:
        log.exception("Anthropic API error for user %s", user_id)
        await update.message.reply_text(
            "Извините, произошла техническая ошибка. "
            "Пожалуйста, попробуйте ещё раз через несколько секунд."
        )


def main() -> None:
    token = os.getenv("ARIA_BOT_TOKEN")
    if not token:
        raise SystemExit("ARIA_BOT_TOKEN environment variable is not set — exiting.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Aria bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
