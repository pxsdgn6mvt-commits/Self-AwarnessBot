import logging
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
    ContextTypes,
)

import config
import database as db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WAITING_TITLE, WAITING_CONTENT = range(2)
WAITING_SEARCH = 10


def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != config.OWNER_ID:
            logger.warning(f"Попытка доступа от чужого ID: {user_id}")
            await update.effective_message.reply_text(config.ACCESS_DENIED)
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def main_menu_keyboard():
    buttons = []
    for key, label in config.CATEGORIES.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"cat_{key}")])
    buttons.append([
        InlineKeyboardButton("🔍 Поиск", callback_data="search"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
    ])
    return InlineKeyboardMarkup(buttons)


@owner_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        config.WELCOME_MESSAGE,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


@owner_only
async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    label = config.CATEGORIES.get(category, category)
    entries = db.get_entries_by_category(category)
    if not entries:
        buttons = [
            [InlineKeyboardButton(f"➕ Добавить", callback_data=f"add_{category}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
        ]
        await query.edit_message_text(
            f"{label}\n\n_Пусто. Добавь первую запись._",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )
        return
    buttons = []
    for entry in entries:
        buttons.append([
            InlineKeyboardButton(f"📌 {entry['title']}", callback_data=f"view_{entry['id']}")
        ])
    buttons.append([
        InlineKeyboardButton("➕ Добавить", callback_data=f"add_{category}"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
    ])
    await query.edit_message_text(
        f"{label} — {len(entries)} записей:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@owner_only
async def view_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    entry_id = int(query.data.replace("view_", ""))
    entry = db.get_entry_by_id(entry_id)
    if not entry:
        await query.edit_message_text("❌ Запись не найдена.")
        return
    category = entry["category"]
    label = config.CATEGORIES.get(category, category)
    created = entry["created_at"][:10]
    text = (
        f"*{entry['title']}*\n"
        f"_{label} · {created}_\n\n"
        f"`{entry['content']}`"
    )
    buttons = [
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"del_{entry_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"cat_{category}")],
    ]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


@owner_only
async def delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    entry_id = int(query.data.replace("del_", ""))
    buttons = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{entry_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"view_{entry_id}"),
        ]
    ]
    await query.edit_message_text(
        "⚠️ Удалить эту запись? Это действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@owner_only
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    entry_id = int(query.data.replace("confirm_del_", ""))
    entry = db.get_entry_by_id(entry_id)
    category = entry["category"] if entry else None
    db.delete_entry(entry_id)
    buttons = [[InlineKeyboardButton("◀️ К категории", callback_data=f"cat_{category or 'notes'}")]]
    await query.edit_message_text("✅ Запись удалена.", reply_markup=InlineKeyboardMarkup(buttons))


@owner_only
async def add_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("add_", "")
    context.user_data["adding_category"] = category
    label = config.CATEGORIES.get(category, category)
    await query.edit_message_text(
        f"➕ *Новая запись в {label}*\n\n"
        f"Введи название (например: «Gmail», «Паспорт», «Мама»):\n\n"
        f"_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_TITLE


async def add_entry_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if len(title) > 200:
        await update.message.reply_text("⚠️ Название слишком длинное. Попробуй снова:")
        return WAITING_TITLE
    context.user_data["adding_title"] = title
    await update.message.reply_text(
        f"📝 Теперь введи содержимое для *{title}*\n\n"
        f"Текст будет зашифрован.\n\n"
        f"_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_CONTENT


async def add_entry_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text.strip()
    if len(content) > 4000:
        await update.message.reply_text("⚠️ Текст слишком длинный. Попробуй снова:")
        return WAITING_CONTENT
    category = context.user_data.get("adding_category", "notes")
    title = context.user_data.get("adding_title", "Без названия")
    try:
        entry_id = db.add_entry(category, title, content)
        label = config.CATEGORIES.get(category, category)
        buttons = [
            [InlineKeyboardButton(f"📂 К категории", callback_data=f"cat_{category}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")],
        ]
        await update.message.reply_text(
            f"✅ *Сохранено и зашифровано*\n\n"
            f"📌 {title}\n{label} · запись #{entry_id}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await update.message.reply_text("❌ Ошибка при сохранении. Попробуй снова.")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


@owner_only
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 Введи поисковый запрос:\n\n_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_SEARCH


async def search_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    results = db.search_entries(query_text)
    if not results:
        buttons = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]]
        await update.message.reply_text(
            f"🔍 По запросу «{query_text}» ничего не найдено.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return ConversationHandler.END
    buttons = []
    for entry in results[:20]:
        label = config.CATEGORIES.get(entry["category"], entry["category"])
        buttons.append([
            InlineKeyboardButton(f"{label} · {entry['title']}", callback_data=f"view_{entry['id']}")
        ])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")])
    await update.message.reply_text(
        f"🔍 Найдено: {len(results)}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return ConversationHandler.END


@owner_only
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stats = db.get_stats()
    total = sum(stats.values())
    lines = ["📊 *Хранилище*\n"]
    for key, label in config.CATEGORIES.items():
        count = stats.get(key, 0)
        lines.append(f"{label}: {count}")
    lines.append(f"\n*Всего записей: {total}*")
    buttons = [[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


@owner_only
async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        config.WELCOME_MESSAGE,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Что-то пошло не так. Попробуй снова или нажми /start"
        )


def main():
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не установлен в .env")
    if not config.OWNER_ID:
        raise ValueError("OWNER_ID не установлен в .env")
    if not config.MASTER_PASSWORD:
        raise ValueError("MASTER_PASSWORD не установлен в .env")

    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_entry_start, pattern=r"^add_")],
        states={
            WAITING_TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_title)],
            WAITING_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_content)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_start, pattern="^search$")],
        states={
            WAITING_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_execute)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(add_conv)
    app.add_handler(search_conv)
    app.add_handler(CallbackQueryHandler(show_category,  pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(view_entry,     pattern=r"^view_"))
    app.add_handler(CallbackQueryHandler(delete_entry,   pattern=r"^del_"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern=r"^confirm_del_"))
    app.add_handler(CallbackQueryHandler(show_stats,     pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(back_main,      pattern="^back_main$"))
    app.add_error_handler(error_handler)

    logger.info("Vault бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
