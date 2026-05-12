import asyncio
import io
import json
import logging
import random
import string
import time
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
from crypto import encrypt, decrypt

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Состояния ConversationHandler ────────────────────────────────────────
WAITING_TITLE, WAITING_CONTENT, WAITING_TAGS = range(3)
WAITING_SEARCH = 10
WAITING_SEARCH_TAG = 11
WAITING_PIN_SET = 20
WAITING_PIN_UNLOCK = 21
WAITING_EDIT_CONTENT = 30
WAITING_RESTORE_FILE = 40

# ─── Состояние сессии (в памяти) ──────────────────────────────────────────
_last_activity: float = time.time()
_locked: bool = False


def _touch():
    global _last_activity
    _last_activity = time.time()


def _is_locked() -> bool:
    global _locked
    if _locked:
        return True
    if time.time() - _last_activity > config.AUTO_LOCK_SECONDS:
        _locked = True
        return True
    return False


def _unlock():
    global _locked, _last_activity
    _locked = False
    _last_activity = time.time()


# ─── Декораторы ───────────────────────────────────────────────────────────

def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != config.OWNER_ID:
            await update.effective_message.reply_text(config.ACCESS_DENIED)
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def lock_check(func):
    """Проверяет блокировку. Если заблокировано — просит пин-код."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != config.OWNER_ID:
            await update.effective_message.reply_text(config.ACCESS_DENIED)
            return ConversationHandler.END
        if _is_locked():
            if not db.has_pin():
                _unlock()
            else:
                context.user_data["pending_callback"] = None
                msg = update.effective_message
                await msg.reply_text(
                    "🔒 Хранилище заблокировано.\n\nВведи пин-код (4 цифры):"
                )
                return WAITING_PIN_UNLOCK
        _touch()
        return await func(update, context)
    return wrapper


# ─── Клавиатуры ──────────────────────────────────────────────────────────

def main_menu_keyboard():
    buttons = []
    for key, label in config.CATEGORIES.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"cat_{key}")])
    buttons.append([
        InlineKeyboardButton("🔍 Поиск", callback_data="search"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
    ])
    buttons.append([
        InlineKeyboardButton("⭐️ Избранное", callback_data="favorites"),
        InlineKeyboardButton("🔑 Генератор", callback_data="gen_password"),
    ])
    buttons.append([
        InlineKeyboardButton("💾 Бэкап", callback_data="backup"),
    ])
    return InlineKeyboardMarkup(buttons)


def entry_action_keyboard(entry_id: int, is_favorite: bool, category: str):
    star = "★ Убрать из избранного" if is_favorite else "⭐️ В избранное"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{entry_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"del_{entry_id}"),
        ],
        [
            InlineKeyboardButton("📋 Копировать", callback_data=f"copy_{entry_id}"),
            InlineKeyboardButton(star, callback_data=f"fav_{entry_id}"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"cat_{category}")],
    ])


# ─── Автоудаление сообщений ───────────────────────────────────────────────

# Держим сильные ссылки на фоновые задачи, иначе GC удалит их до выполнения
_delete_tasks: set = set()


async def _schedule_delete(bot, chat_id: int, message_id: int, delay: int):
    """Удаляет сообщение через delay секунд."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _send_secret(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Отправляет сообщение с секретом и запускает его автоудаление."""
    delay = config.SECRET_DELETE_SECONDS
    footer = f"\n\n🔐 _Сообщение удалится через {delay} сек_"
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text + footer,
        parse_mode=parse_mode,
    )
    task = asyncio.create_task(_schedule_delete(context.bot, chat_id, msg.message_id, delay))
    _delete_tasks.add(task)
    task.add_done_callback(_delete_tasks.discard)
    return msg


# ─── /start ───────────────────────────────────────────────────────────────

@owner_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch()
    if _is_locked() and db.has_pin():
        await update.message.reply_text("🔒 Хранилище заблокировано.\n\nВведи пин-код (4 цифры):")
        return WAITING_PIN_UNLOCK
    _unlock()
    await update.message.reply_text(
        config.WELCOME_MESSAGE,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


# ─── Пин-код ──────────────────────────────────────────────────────────────

@owner_only
async def cmd_setpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch()
    await update.message.reply_text(
        "🔐 Введи новый пин-код (4 цифры):\n\n_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_PIN_SET


async def pin_set_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pin = update.message.text.strip()
    if not pin.isdigit() or len(pin) != 4:
        await update.message.reply_text("⚠️ Пин-код должен быть 4 цифры. Попробуй снова:")
        return WAITING_PIN_SET
    db.set_pin(pin)
    _touch()
    await update.message.reply_text(
        "✅ Пин-код установлен. Хранилище будет блокироваться через 10 минут бездействия.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def pin_unlock_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pin = update.message.text.strip()
    if db.check_pin(pin):
        _unlock()
        await update.message.reply_text(
            "✅ Разблокировано.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Неверный пин-код. Попробуй снова:")
        return WAITING_PIN_UNLOCK


# ─── Главное меню (callback) ──────────────────────────────────────────────

@owner_only
async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    await query.edit_message_text(
        config.WELCOME_MESSAGE,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


# ─── Категории ────────────────────────────────────────────────────────────

@owner_only
async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if _is_locked() and db.has_pin():
        await query.edit_message_text("🔒 Хранилище заблокировано. Нажми /start и введи пин-код.")
        return
    _touch()
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
        star = "⭐️ " if entry["is_favorite"] else ""
        buttons.append([
            InlineKeyboardButton(f"📌 {star}{entry['title']}", callback_data=f"view_{entry['id']}")
        ])
    buttons.append([
        InlineKeyboardButton("➕ Добавить", callback_data=f"add_{category}"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
    ])
    await query.edit_message_text(
        f"{label} — {len(entries)} записей:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─── Просмотр записи ──────────────────────────────────────────────────────

@owner_only
async def view_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if _is_locked() and db.has_pin():
        await query.edit_message_text("🔒 Хранилище заблокировано. Нажми /start и введи пин-код.")
        return
    _touch()
    entry_id = int(query.data.replace("view_", ""))
    entry = db.get_entry_by_id(entry_id)
    if not entry:
        await query.edit_message_text("❌ Запись не найдена.")
        return
    category = entry["category"]
    label = config.CATEGORIES.get(category, category)
    created = entry["created_at"][:10]
    tags_line = f"\n🏷 _{entry['tags']}_" if entry.get("tags") else ""
    text = (
        f"*{entry['title']}*\n"
        f"_{label} · {created}_{tags_line}\n\n"
        f"`{entry['content']}`"
    )
    # Отправляем секретное сообщение с автоудалением
    await _send_secret(context, query.message.chat_id, text)
    # Редактируем исходное сообщение — оставляем только кнопки управления
    await query.edit_message_text(
        f"*{entry['title']}* — управление записью:",
        reply_markup=entry_action_keyboard(entry_id, entry["is_favorite"], category),
        parse_mode="Markdown",
    )


# ─── Копировать ───────────────────────────────────────────────────────────

@owner_only
async def copy_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    entry_id = int(query.data.replace("copy_", ""))
    entry = db.get_entry_by_id(entry_id)
    if not entry:
        await query.answer("❌ Запись не найдена.", show_alert=True)
        return
    await _send_secret(context, query.message.chat_id, f"`{entry['content']}`")


# ─── Избранное ────────────────────────────────────────────────────────────

@owner_only
async def toggle_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    entry_id = int(query.data.replace("fav_", ""))
    entry = db.get_entry_by_id(entry_id)
    if not entry:
        return
    new_state = db.toggle_favorite(entry_id)
    label = "⭐️ Добавлено в избранное" if new_state else "★ Убрано из избранного"
    await query.answer(label, show_alert=False)
    # Обновляем кнопки
    await query.edit_message_reply_markup(
        reply_markup=entry_action_keyboard(entry_id, new_state, entry["category"])
    )


@owner_only
async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    entries = db.get_favorites()
    if not entries:
        await query.edit_message_text(
            "⭐️ *Избранное*\n\n_Нет избранных записей._",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]),
            parse_mode="Markdown",
        )
        return
    buttons = []
    for e in entries:
        cat_label = config.CATEGORIES.get(e["category"], e["category"])
        buttons.append([InlineKeyboardButton(f"{cat_label} · {e['title']}", callback_data=f"view_{e['id']}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text(
        f"⭐️ *Избранное* — {len(entries)} записей:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


@owner_only
async def cmd_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch()
    entries = db.get_favorites()
    if not entries:
        await update.message.reply_text(
            "⭐️ *Избранное*\n\n_Нет избранных записей._",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return
    buttons = []
    for e in entries:
        cat_label = config.CATEGORIES.get(e["category"], e["category"])
        buttons.append([InlineKeyboardButton(f"{cat_label} · {e['title']}", callback_data=f"view_{e['id']}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await update.message.reply_text(
        f"⭐️ *Избранное* — {len(entries)} записей:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


# ─── Редактирование ───────────────────────────────────────────────────────

@owner_only
async def edit_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    entry_id = int(query.data.replace("edit_", ""))
    entry = db.get_entry_by_id(entry_id)
    if not entry:
        await query.edit_message_text("❌ Запись не найдена.")
        return ConversationHandler.END
    context.user_data["editing_id"] = entry_id
    context.user_data["editing_category"] = entry["category"]
    await query.edit_message_text(
        f"✏️ *Редактирование: {entry['title']}*\n\n"
        f"Введи новое содержимое (старое будет заменено):\n\n"
        f"_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_EDIT_CONTENT


async def edit_entry_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_content = update.message.text.strip()
    entry_id = context.user_data.get("editing_id")
    category = context.user_data.get("editing_category", "notes")
    if not entry_id:
        await update.message.reply_text("❌ Ошибка. Начни заново.")
        return ConversationHandler.END
    db.update_entry(entry_id, new_content)
    _touch()
    buttons = [
        [InlineKeyboardButton("👁 Посмотреть", callback_data=f"view_{entry_id}")],
        [InlineKeyboardButton("◀️ К категории", callback_data=f"cat_{category}")],
    ]
    await update.message.reply_text(
        "✅ *Запись обновлена и перезашифрована.*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


# ─── Удаление ────────────────────────────────────────────────────────────

@owner_only
async def delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    entry_id = int(query.data.replace("del_", ""))
    buttons = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{entry_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"view_{entry_id}"),
        ]
    ]
    await query.edit_message_text(
        "⚠️ Точно удалить эту запись? Действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@owner_only
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    entry_id = int(query.data.replace("confirm_del_", ""))
    entry = db.get_entry_by_id(entry_id)
    category = entry["category"] if entry else "notes"
    db.delete_entry(entry_id)
    buttons = [[InlineKeyboardButton("◀️ К категории", callback_data=f"cat_{category}")]]
    await query.edit_message_text("✅ Удалено.", reply_markup=InlineKeyboardMarkup(buttons))


# ─── Добавление записи ────────────────────────────────────────────────────

@owner_only
async def add_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if _is_locked() and db.has_pin():
        await query.edit_message_text("🔒 Хранилище заблокировано. Нажми /start и введи пин-код.")
        return ConversationHandler.END
    _touch()
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
    context.user_data["adding_content"] = content
    await update.message.reply_text(
        "🏷 Добавь теги через запятую (например: *работа, важное*)\n\n"
        "Или нажми /skip чтобы пропустить:",
        parse_mode="Markdown",
    )
    return WAITING_TAGS


async def add_entry_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tags_raw = update.message.text.strip()
    # Нормализуем теги
    tags = ",".join(t.strip() for t in tags_raw.split(",") if t.strip())
    return await _save_entry(update, context, tags)


async def add_entry_skip_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _save_entry(update, context, "")


async def _save_entry(update, context, tags: str):
    category = context.user_data.get("adding_category", "notes")
    title = context.user_data.get("adding_title", "Без названия")
    content = context.user_data.get("adding_content", "")
    try:
        entry_id = db.add_entry(category, title, content, tags)
        label = config.CATEGORIES.get(category, category)
        buttons = [
            [InlineKeyboardButton(f"📂 К категории", callback_data=f"cat_{category}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")],
        ]
        tags_line = f"\n🏷 Теги: {tags}" if tags else ""
        await update.message.reply_text(
            f"✅ *Сохранено и зашифровано*\n\n"
            f"📌 {title}\n{label} · запись #{entry_id}{tags_line}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await update.message.reply_text("❌ Ошибка при сохранении. Попробуй снова.")
    context.user_data.clear()
    return ConversationHandler.END


# ─── Поиск ────────────────────────────────────────────────────────────────

@owner_only
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    buttons = [
        [InlineKeyboardButton("🔤 По тексту", callback_data="search_text")],
        [InlineKeyboardButton("🏷 По тегам", callback_data="search_tag")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ]
    await query.edit_message_text(
        "🔍 Выбери тип поиска:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@owner_only
async def search_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    await query.edit_message_text(
        "🔍 Введи поисковый запрос:\n\n_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_SEARCH


async def search_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    results = db.search_entries(query_text)
    _touch()
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
        buttons.append([InlineKeyboardButton(f"{label} · {entry['title']}", callback_data=f"view_{entry['id']}")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")])
    await update.message.reply_text(
        f"🔍 Найдено: {len(results)}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return ConversationHandler.END


@owner_only
async def search_tag_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    await query.edit_message_text(
        "🏷 Введи тег для поиска:\n\n_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_SEARCH_TAG


async def search_tag_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = update.message.text.strip()
    results = db.search_by_tag(tag)
    _touch()
    if not results:
        buttons = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]]
        await update.message.reply_text(
            f"🏷 По тегу «{tag}» ничего не найдено.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return ConversationHandler.END
    buttons = []
    for entry in results[:20]:
        label = config.CATEGORIES.get(entry["category"], entry["category"])
        buttons.append([InlineKeyboardButton(f"{label} · {entry['title']}", callback_data=f"view_{entry['id']}")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")])
    await update.message.reply_text(
        f"🏷 По тегу «{tag}» найдено: {len(results)}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return ConversationHandler.END


# ─── Статистика ───────────────────────────────────────────────────────────

@owner_only
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
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


# ─── Генератор паролей ────────────────────────────────────────────────────

def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))


@owner_only
async def gen_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вызывается через callback или команду /generate."""
    _touch()
    pwd = _generate_password()
    context.user_data["generated_password"] = pwd
    buttons = [
        [
            InlineKeyboardButton("🔄 Новый", callback_data="gen_password"),
            InlineKeyboardButton("📋 Копировать", callback_data="gen_copy"),
        ],
        [InlineKeyboardButton("💾 Сохранить в Пароли", callback_data="gen_save")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ]
    text = f"🔑 *Сгенерированный пароль:*\n\n`{pwd}`"
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


@owner_only
async def gen_copy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    pwd = context.user_data.get("generated_password", "")
    if pwd:
        await _send_secret(context, query.message.chat_id, f"`{pwd}`")


@owner_only
async def gen_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    pwd = context.user_data.get("generated_password", "")
    if not pwd:
        await query.answer("❌ Нет пароля для сохранения.", show_alert=True)
        return
    context.user_data["adding_category"] = "passwords"
    context.user_data["adding_content_prefill"] = pwd
    await query.edit_message_text(
        "💾 *Сохранение пароля*\n\nВведи название (например: «Gmail»):\n\n_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_TITLE


# ─── Бэкап и восстановление ──────────────────────────────────────────────

@owner_only
async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch()
    await _do_backup(context, update.effective_chat.id)


@owner_only
async def backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _touch()
    await query.edit_message_text("💾 Создаю бэкап...")
    await _do_backup(context, query.message.chat_id)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="✅ Бэкап отправлен.",
        reply_markup=main_menu_keyboard(),
    )


async def _do_backup(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    records = db.export_all_encrypted()
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    # Шифруем весь JSON мастер-паролем
    encrypted_payload = encrypt(payload, config.MASTER_PASSWORD)
    file_data = encrypted_payload.encode()
    filename = f"vault_backup_{int(time.time())}.enc"
    await context.bot.send_document(
        chat_id=chat_id,
        document=io.BytesIO(file_data),
        filename=filename,
        caption=(
            "💾 *Зашифрованный бэкап хранилища*\n\n"
            "Файл зашифрован мастер-паролем.\n"
            "Для восстановления: /restore"
        ),
        parse_mode="Markdown",
    )


@owner_only
async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch()
    await update.message.reply_text(
        "📥 *Восстановление из бэкапа*\n\n"
        "Отправь файл бэкапа (.enc).\n\n"
        "_/cancel — отмена_",
        parse_mode="Markdown",
    )
    return WAITING_RESTORE_FILE


async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        await update.message.reply_text("⚠️ Отправь файл (.enc). Попробуй снова:")
        return WAITING_RESTORE_FILE
    file = await context.bot.get_file(doc.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    encrypted_payload = buf.getvalue().decode()
    try:
        payload = decrypt(encrypted_payload, config.MASTER_PASSWORD)
        records = json.loads(payload)
        inserted = db.import_from_backup(records)
        await update.message.reply_text(
            f"✅ *Восстановлено {inserted} записей.*",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Ошибка восстановления: {e}")
        await update.message.reply_text(
            "❌ Не удалось расшифровать файл. Убедись что файл верный.",
            reply_markup=main_menu_keyboard(),
        )
    return ConversationHandler.END


# ─── Отмена ───────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ─── Обработчик ошибок ────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Что-то пошло не так. Попробуй снова или нажми /start"
        )


# ─── Автобэкап (каждое воскресенье в 10:00) ──────────────────────────────

async def auto_backup_job(bot):
    logger.info("Автобэкап запущен")
    try:
        records = db.export_all_encrypted()
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        encrypted_payload = encrypt(payload, config.MASTER_PASSWORD)
        file_data = encrypted_payload.encode()
        filename = f"vault_autobackup_{int(time.time())}.enc"
        await bot.send_document(
            chat_id=config.OWNER_ID,
            document=io.BytesIO(file_data),
            filename=filename,
            caption="🔄 *Еженедельный автобэкап*\n\nФайл зашифрован мастер-паролем.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Ошибка автобэкапа: {e}")


# ─── main ─────────────────────────────────────────────────────────────────

def main():
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не установлен в .env")
    if not config.OWNER_ID:
        raise ValueError("OWNER_ID не установлен в .env")
    if not config.MASTER_PASSWORD:
        raise ValueError("MASTER_PASSWORD не установлен в .env")

    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    # ConversationHandler: добавление записи
    add_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_entry_start, pattern=r"^add_"),
            CallbackQueryHandler(gen_save, pattern=r"^gen_save$"),
        ],
        states={
            WAITING_TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_title)],
            WAITING_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_content)],
            WAITING_TAGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_tags),
                CommandHandler("skip", add_entry_skip_tags),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ConversationHandler: поиск по тексту
    search_text_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_text_start, pattern="^search_text$")],
        states={
            WAITING_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_execute)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ConversationHandler: поиск по тегам
    search_tag_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_tag_start, pattern="^search_tag$")],
        states={
            WAITING_SEARCH_TAG: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_tag_execute)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ConversationHandler: установка пин-кода
    setpin_conv = ConversationHandler(
        entry_points=[CommandHandler("setpin", cmd_setpin)],
        states={
            WAITING_PIN_SET: [MessageHandler(filters.TEXT & ~filters.COMMAND, pin_set_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ConversationHandler: разблокировка через /start
    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_PIN_UNLOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, pin_unlock_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ConversationHandler: редактирование записи
    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_entry_start, pattern=r"^edit_")],
        states={
            WAITING_EDIT_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_entry_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ConversationHandler: восстановление из бэкапа
    restore_conv = ConversationHandler(
        entry_points=[CommandHandler("restore", cmd_restore)],
        states={
            WAITING_RESTORE_FILE: [MessageHandler(filters.Document.ALL, restore_receive_file)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(start_conv)
    app.add_handler(setpin_conv)
    app.add_handler(add_conv)
    app.add_handler(search_text_conv)
    app.add_handler(search_tag_conv)
    app.add_handler(edit_conv)
    app.add_handler(restore_conv)

    app.add_handler(CommandHandler("generate", gen_password))
    app.add_handler(CommandHandler("favorites", cmd_favorites))
    app.add_handler(CommandHandler("backup", cmd_backup))

    app.add_handler(CallbackQueryHandler(show_category,   pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(view_entry,      pattern=r"^view_"))
    app.add_handler(CallbackQueryHandler(delete_entry,    pattern=r"^del_"))
    app.add_handler(CallbackQueryHandler(confirm_delete,  pattern=r"^confirm_del_"))
    app.add_handler(CallbackQueryHandler(toggle_favorite, pattern=r"^fav_"))
    app.add_handler(CallbackQueryHandler(copy_entry,      pattern=r"^copy_"))
    app.add_handler(CallbackQueryHandler(show_favorites,  pattern=r"^favorites$"))
    app.add_handler(CallbackQueryHandler(show_stats,      pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(back_main,       pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(gen_password,    pattern="^gen_password$"))
    app.add_handler(CallbackQueryHandler(gen_copy,        pattern="^gen_copy$"))
    app.add_handler(CallbackQueryHandler(search_start,    pattern="^search$"))
    app.add_handler(CallbackQueryHandler(backup_callback, pattern="^backup$"))

    app.add_error_handler(error_handler)

    # Планировщик автобэкапа (каждое воскресенье в 10:00)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        auto_backup_job,
        trigger="cron",
        day_of_week="sun",
        hour=10,
        minute=0,
        args=[app.bot],
    )
    scheduler.start()

    logger.info("Vault бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
