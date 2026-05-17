import logging
import asyncio
import io
import json
from datetime import datetime, timezone, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, ConversationHandler, filters,
    ContextTypes, TypeHandler, ApplicationHandlerStop,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
import crypto
import utils
import payments as pay
from config import (
    BOT_TOKEN, OWNER_ID, CATEGORIES,
    PLAN_FREE, PLAN_ONETIME, PLAN_PREMIUM,
    FREE_ENTRY_LIMIT, FREE_CATEGORIES,
    SECRET_DELETE_SECONDS,
)
from locales import t

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Состояния ConversationHandler ───────────────────────────────────────────

(
    ST_LANG, ST_MASTER_NEW, ST_MASTER_CONFIRM,
    ST_MASTER_ENTER, ST_PIN_ENTER,
    ST_ADD_CAT, ST_ADD_NAME, ST_ADD_CONTENT, ST_ADD_TAGS,
    ST_SEARCH, ST_PIN_NEW, ST_PIN_CONFIRM,
    ST_RESTORE,
    ST_ADMIN_ADD_ID, ST_ADMIN_ADD_NAME, ST_ADMIN_RENAME, ST_ADMIN_NOTES,
) = range(17)


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _plan_label(user: dict, lang: str) -> str:
    plan = user["plan"]
    if plan == PLAN_ONETIME:
        return t(lang, "plan_onetime")
    if plan == PLAN_PREMIUM and pay.is_plan_active(user):
        return t(lang, "plan_premium")
    return t(lang, "plan_free")


def _cat_label(cat: str, lang: str) -> str:
    names = {
        "passwords": ("Пароли"     if lang == "ru" else "Passwords"),
        "seeds":     ("Seed-фразы" if lang == "ru" else "Seeds"),
        "wallets":   ("Кошельки"   if lang == "ru" else "Wallets"),
        "exchanges": ("Биржи"      if lang == "ru" else "Exchanges"),
        "twofa":     ("2FA"        if lang == "ru" else "2FA"),
        "documents": ("Документы"  if lang == "ru" else "Documents"),
        "contacts":  ("Контакты"   if lang == "ru" else "Contacts"),
        "notes":     ("Заметки"    if lang == "ru" else "Notes"),
    }
    emoji = CATEGORIES.get(cat, "📁")
    return f"{emoji} {names.get(cat, cat)}"


async def _get_user_or_create(update: Update) -> dict:
    tg = update.effective_user
    user = await db.get_user(tg.id)
    if not user:
        lang = utils.detect_lang(tg.language_code or "")
        await db.create_user(tg.id, tg.username or "", lang)
        user = await db.get_user(tg.id)
    return dict(user)


async def _require_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if utils.is_locked(user_id):
        user = await db.get_user(user_id)
        lang = user["lang"] if user else "en"
        await update.effective_message.reply_text(t(lang, "locked"))
        return False
    utils.touch(user_id)
    return True


async def _check_rate_limit(update: Update, lang: str) -> bool:
    if utils.is_rate_limited(update.effective_user.id):
        await update.effective_message.reply_text(t(lang, "rate_limit"))
        return True
    return False


def _main_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_add"), callback_data="menu_add")],
        [
            InlineKeyboardButton(t(lang, "btn_list"),      callback_data="menu_list"),
            InlineKeyboardButton(t(lang, "btn_search"),    callback_data="menu_search"),
        ],
        [
            InlineKeyboardButton(t(lang, "btn_favorites"), callback_data="menu_fav"),
            InlineKeyboardButton(t(lang, "btn_backup"),    callback_data="menu_backup"),
        ],
        [
            InlineKeyboardButton(t(lang, "btn_generate"),  callback_data="menu_gen"),
            InlineKeyboardButton(t(lang, "btn_subscribe"), callback_data="menu_subscribe"),
        ],
        [InlineKeyboardButton(t(lang, "btn_settings"), callback_data="menu_settings")],
    ])


async def _send_main_menu(update: Update, user: dict):
    lang = user["lang"]
    count = await db.count_entries(user["user_id"])
    plan_label = _plan_label(user, lang)

    tg_user = update.effective_user
    name = (tg_user.first_name if tg_user and tg_user.first_name
            else (tg_user.username if tg_user else "—"))

    locked = utils.is_locked(user["user_id"])
    if lang == "ru":
        lock_icon, lock_status = ("🔒", "Заблокировано") if locked else ("🔓", "Открыто")
    else:
        lock_icon, lock_status = ("🔒", "Locked") if locked else ("🔓", "Unlocked")

    text = t(lang, "menu",
             plan=plan_label, count=count,
             name=name, lock_icon=lock_icon, lock_status=lock_status)
    kb = _main_keyboard(lang)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


# ─── /start — онбординг ──────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    args = context.args or []

    referrer_id = None
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0][4:])
        except ValueError:
            pass

    user = await db.get_user(tg.id)

    if user and user["master_hash"]:
        lang = user["lang"]
        if utils.is_locked(tg.id):
            # Есть PIN — просим его, иначе мастер-пароль
            if user["pin_hash"]:
                await update.message.reply_text(t(lang, "enter_pin"))
                return ST_PIN_ENTER
            await update.message.reply_text(t(lang, "enter_master"))
            return ST_MASTER_ENTER
        await _send_main_menu(update, dict(user))
        return ConversationHandler.END

    # Новый пользователь
    lang = utils.detect_lang(tg.language_code or "")
    if referrer_id and referrer_id != tg.id:
        context.user_data["referrer_id"] = referrer_id

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ])
    await update.message.reply_text(t(lang, "welcome"), reply_markup=kb, parse_mode="Markdown")
    return ST_LANG


async def cb_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = "ru" if query.data == "lang_ru" else "en"
    context.user_data["lang"] = lang

    tg = update.effective_user
    referrer_id = context.user_data.get("referrer_id")
    await db.create_user(tg.id, tg.username or "", lang, referrer_id)

    if referrer_id:
        await db.add_referral(referrer_id, tg.id)

    await query.edit_message_text(t(lang, "lang_set"))
    await query.message.reply_text(t(lang, "set_master"), parse_mode="Markdown")
    return ST_MASTER_NEW


async def rcv_master_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    lang = context.user_data.get("lang", "en")
    if len(pwd) < 8:
        await update.message.reply_text(t(lang, "master_too_short"))
        return ST_MASTER_NEW
    context.user_data["master_pwd"] = pwd
    await update.message.reply_text(t(lang, "confirm_master"))
    return ST_MASTER_CONFIRM


async def rcv_master_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    lang = context.user_data.get("lang", "en")
    if pwd != context.user_data.get("master_pwd"):
        await update.message.reply_text(t(lang, "master_mismatch"))
        return ST_MASTER_CONFIRM

    user_id = update.effective_user.id
    master_hash = crypto.hash_password(pwd, user_id)
    await db.set_master_hash(user_id, master_hash)

    key = crypto.derive_key(pwd, user_id)
    utils.set_key(user_id, key)

    user = await db.get_user(user_id)
    await update.message.reply_text(
        t(lang, "master_set") + t(lang, "tutorial"),
        parse_mode="Markdown",
    )
    await _send_main_menu(update, dict(user))
    return ConversationHandler.END


async def rcv_master_enter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    lang = user["lang"] if user else "en"

    if crypto.hash_password(pwd, user_id) != user["master_hash"]:
        await update.message.reply_text(t(lang, "wrong_master"))
        return ST_MASTER_ENTER

    key = crypto.derive_key(pwd, user_id)
    utils.set_key(user_id, key)

    if user["pin_hash"]:
        await update.message.reply_text(t(lang, "enter_pin"))
        return ST_PIN_ENTER

    await update.message.reply_text(t(lang, "unlocked"))
    await _send_main_menu(update, dict(user))
    return ConversationHandler.END


async def rcv_pin_enter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pin = update.message.text.strip()
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    lang = user["lang"] if user else "en"

    if crypto.hash_pin(pin, user_id) != user["pin_hash"]:
        await update.message.reply_text(t(lang, "wrong_pin"))
        return ST_PIN_ENTER

    utils.touch(user_id)
    await update.message.reply_text(t(lang, "unlocked"))
    await _send_main_menu(update, dict(user))
    return ConversationHandler.END


# ─── Меню (CallbackQuery) ─────────────────────────────────────────────────────

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if await _check_rate_limit(update, lang):
        return

    action = query.data
    if action == "menu_add":
        await cmd_add(update, context)
    elif action == "menu_list":
        await cmd_list(update, context)
    elif action == "menu_search":
        await cmd_search(update, context)
    elif action == "menu_fav":
        await cmd_favorites(update, context)
    elif action == "menu_gen":
        await cmd_generate(update, context)
    elif action == "menu_backup":
        await cmd_backup(update, context)
    elif action == "menu_subscribe":
        await cmd_subscribe(update, context)
    elif action == "menu_settings":
        await _show_settings(update, user)
    elif action == "menu_home":
        await _send_main_menu(update, user)


async def _show_settings(update: Update, user: dict):
    lang = user["lang"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔢 PIN", callback_data="settings_pin")],
        [
            InlineKeyboardButton(t(lang, "btn_ru"), callback_data="settings_lang_ru"),
            InlineKeyboardButton(t(lang, "btn_en"), callback_data="settings_lang_en"),
        ],
        [InlineKeyboardButton("🔙", callback_data="menu_home")],
    ])
    title = "⚙️ Настройки" if lang == "ru" else "⚙️ Settings"
    await update.callback_query.edit_message_text(title, reply_markup=kb)


async def cb_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if query.data == "settings_pin":
        await query.edit_message_text(t(lang, "pin_prompt"))
        return ST_PIN_NEW

    if query.data in ("settings_lang_ru", "settings_lang_en"):
        new_lang = "ru" if query.data == "settings_lang_ru" else "en"
        await db.set_lang(user["user_id"], new_lang)
        user["lang"] = new_lang
        await query.edit_message_text(t(new_lang, "lang_set"))
        await _send_main_menu(update, user)

    return ConversationHandler.END


# ─── /add ─────────────────────────────────────────────────────────────────────

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if not await _require_unlock(update, context):
        return ConversationHandler.END

    # Paywall по количеству
    effective_plan = user["plan"] if pay.is_plan_active(user) else PLAN_FREE
    if effective_plan == PLAN_FREE:
        count = await db.count_entries(user["user_id"])
        if count >= FREE_ENTRY_LIMIT:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_buy_onetime"), callback_data="buy_onetime")],
                [InlineKeyboardButton(t(lang, "btn_buy_premium"), callback_data="buy_premium")],
            ])
            msg = t(lang, "paywall")
            if update.callback_query:
                await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
            else:
                await update.effective_message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")
            return ConversationHandler.END

    cats = FREE_CATEGORIES if effective_plan == PLAN_FREE else list(CATEGORIES.keys())
    buttons = [[InlineKeyboardButton(_cat_label(c, lang), callback_data=f"addcat_{c}")] for c in cats]
    buttons.append([InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="cancel_add")])
    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(t(lang, "add_choose_cat"), reply_markup=kb)
    else:
        await update.effective_message.reply_text(t(lang, "add_choose_cat"), reply_markup=kb)

    return ST_ADD_CAT


async def cb_add_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_add":
        user = await _get_user_or_create(update)
        await query.edit_message_text(t(user["lang"], "add_cancelled"))
        return ConversationHandler.END

    cat = query.data.replace("addcat_", "")
    user = await _get_user_or_create(update)
    lang = user["lang"]

    effective_plan = user["plan"] if pay.is_plan_active(user) else PLAN_FREE
    if effective_plan == PLAN_FREE and cat not in FREE_CATEGORIES:
        await query.edit_message_text(
            t(lang, "paywall_cat", cat=_cat_label(cat, lang)), parse_mode="Markdown"
        )
        return ConversationHandler.END

    context.user_data["add_cat"] = cat
    await query.edit_message_text(t(lang, "add_name"))
    return ST_ADD_NAME


async def rcv_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    context.user_data["add_name"] = update.message.text.strip()
    await update.message.reply_text(t(user["lang"], "add_content"))
    return ST_ADD_CONTENT


async def rcv_add_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    context.user_data["add_content"] = update.message.text.strip()
    await update.message.reply_text(t(user["lang"], "add_tags"))
    return ST_ADD_TAGS


async def rcv_add_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    user_id = user["user_id"]

    raw_tags = update.message.text.strip()
    tags = "" if raw_tags == "/skip" else raw_tags

    key = utils.get_key(user_id)
    if key is None:
        await update.message.reply_text(t(lang, "locked"))
        return ConversationHandler.END

    encrypted = crypto.encrypt(context.user_data.get("add_content", ""), key)
    cat = context.user_data.get("add_cat", "notes")
    name = context.user_data.get("add_name", "")

    await db.add_entry(user_id, cat, name, encrypted, tags)
    await update.message.reply_text(
        t(lang, "add_done", name=name, cat=_cat_label(cat, lang)), parse_mode="Markdown"
    )
    return ConversationHandler.END


# ─── /list ────────────────────────────────────────────────────────────────────

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if not await _require_unlock(update, context):
        return

    effective_plan = user["plan"] if pay.is_plan_active(user) else PLAN_FREE
    cats = FREE_CATEGORIES if effective_plan == PLAN_FREE else list(CATEGORIES.keys())

    buttons = [[InlineKeyboardButton(_cat_label(c, lang), callback_data=f"listcat_{c}")] for c in cats]
    buttons.append([InlineKeyboardButton("🔙", callback_data="menu_home")])
    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(t(lang, "list_choose_cat"), reply_markup=kb)
    else:
        await update.effective_message.reply_text(t(lang, "list_choose_cat"), reply_markup=kb)


async def cb_list_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("listcat_", "")
    user = await _get_user_or_create(update)
    lang = user["lang"]

    entries = await db.get_entries_by_category(user["user_id"], cat)
    cat_label = _cat_label(cat, lang)

    if not entries:
        await query.edit_message_text(t(lang, "list_empty", cat=cat_label), parse_mode="Markdown")
        return

    lines = [t(lang, "list_header", cat=cat_label, count=len(entries))]
    for e in entries:
        fav = "⭐ " if e["is_favorite"] else ""
        tags_str = f" [{e['tags']}]" if e["tags"] else ""
        lines.append(t(lang, "entry_line", fav=fav, name=e["name"], tags=tags_str, id=e["id"]))

    await query.edit_message_text("\n".join(lines), parse_mode="Markdown")


# ─── Inline-команды /get_N, /del_N, /fav_N ───────────────────────────────────

async def handle_inline_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = await _get_user_or_create(update)
    lang = user["lang"]
    user_id = user["user_id"]

    if not await _require_unlock(update, context):
        return

    if text.startswith("/get_"):
        try:
            entry_id = int(text[5:])
        except ValueError:
            return
        key = utils.get_key(user_id)
        if not key:
            await update.message.reply_text(t(lang, "locked"))
            return
        entry = await db.get_entry(entry_id, user_id)
        if not entry:
            await update.message.reply_text(t(lang, "entry_not_found"))
            return
        try:
            content = crypto.decrypt(entry["content_encrypted"], key)
        except Exception:
            await update.message.reply_text(t(lang, "error"))
            return
        cat_label = _cat_label(entry["category"], lang)
        msg = await update.message.reply_text(
            t(lang, "entry_view",
              name=entry["name"], cat=cat_label,
              tags=entry["tags"] or "—", content=content),
            parse_mode="Markdown",
        )
        asyncio.create_task(
            utils.schedule_delete(context.bot, msg.chat_id, msg.message_id, SECRET_DELETE_SECONDS)
        )

    elif text.startswith("/del_"):
        try:
            entry_id = int(text[5:])
        except ValueError:
            return
        entry = await db.get_entry(entry_id, user_id)
        if not entry:
            await update.message.reply_text(t(lang, "entry_not_found"))
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "btn_yes_delete"), callback_data=f"confirm_del_{entry_id}"),
            InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="cancel_del"),
        ]])
        await update.message.reply_text(
            t(lang, "delete_confirm", name=entry["name"]),
            reply_markup=kb, parse_mode="Markdown",
        )

    elif text.startswith("/fav_"):
        try:
            entry_id = int(text[5:])
        except ValueError:
            return
        await db.toggle_favorite(entry_id, user_id)
        await update.message.reply_text(t(lang, "fav_toggled"))


async def cb_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if query.data.startswith("confirm_del_"):
        entry_id = int(query.data[12:])
        await db.delete_entry(entry_id, user["user_id"])
        await query.edit_message_text(t(lang, "deleted"))
    else:
        await query.edit_message_text(t(lang, "cancelled"))


# ─── /search ─────────────────────────────────────────────────────────────────

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    if not await _require_unlock(update, context):
        return ConversationHandler.END
    if update.callback_query:
        await update.callback_query.edit_message_text(t(lang, "search_prompt"))
    else:
        await update.effective_message.reply_text(t(lang, "search_prompt"))
    return ST_SEARCH


async def rcv_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    query_str = update.message.text.strip()

    results = await db.search_entries(user["user_id"], query_str)

    if not results:
        await update.message.reply_text(
            t(lang, "search_empty", query=query_str), parse_mode="Markdown"
        )
        return ConversationHandler.END

    lines = [t(lang, "search_results", query=query_str, count=len(results))]
    for e in results:
        fav = "⭐ " if e["is_favorite"] else ""
        tags_str = f" [{e['tags']}]" if e["tags"] else ""
        lines.append(t(lang, "entry_line", fav=fav, name=e["name"], tags=tags_str, id=e["id"]))

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    return ConversationHandler.END


# ─── /favorites ───────────────────────────────────────────────────────────────

async def cmd_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    if not await _require_unlock(update, context):
        return

    entries = await db.get_favorites(user["user_id"])
    if not entries:
        msg = t(lang, "fav_empty")
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.effective_message.reply_text(msg)
        return

    lines = [t(lang, "fav_header", count=len(entries))]
    for e in entries:
        tags_str = f" [{e['tags']}]" if e["tags"] else ""
        lines.append(t(lang, "entry_line", fav="⭐ ", name=e["name"], tags=tags_str, id=e["id"]))

    text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown")


# ─── /generate ────────────────────────────────────────────────────────────────

async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]

    effective_plan = user["plan"] if pay.is_plan_active(user) else PLAN_FREE
    if effective_plan == PLAN_FREE:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_buy_onetime"), callback_data="buy_onetime")],
            [InlineKeyboardButton(t(lang, "btn_buy_premium"), callback_data="buy_premium")],
        ])
        msg = t(lang, "paywall")
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_gen_pass"),   callback_data="gen_pass")],
        [InlineKeyboardButton(t(lang, "btn_gen_seed12"), callback_data="gen_seed12")],
        [InlineKeyboardButton(t(lang, "btn_gen_seed24"), callback_data="gen_seed24")],
        [InlineKeyboardButton("🔙", callback_data="menu_home")],
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(
            t(lang, "gen_menu"), reply_markup=kb, parse_mode="Markdown"
        )
    else:
        await update.effective_message.reply_text(
            t(lang, "gen_menu"), reply_markup=kb, parse_mode="Markdown"
        )


async def cb_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if query.data == "gen_pass":
        value = utils.generate_password(16)
        msg = await query.message.reply_text(
            t(lang, "gen_result_pass", value=value), parse_mode="Markdown"
        )
    elif query.data == "gen_seed12":
        value = utils.generate_seed_phrase(12)
        msg = await query.message.reply_text(
            t(lang, "gen_result_seed", words=12, value=value), parse_mode="Markdown"
        )
    elif query.data == "gen_seed24":
        value = utils.generate_seed_phrase(24)
        msg = await query.message.reply_text(
            t(lang, "gen_result_seed", words=24, value=value), parse_mode="Markdown"
        )
    else:
        return

    asyncio.create_task(
        utils.schedule_delete(context.bot, msg.chat_id, msg.message_id, SECRET_DELETE_SECONDS)
    )


# ─── /backup ──────────────────────────────────────────────────────────────────

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if not await _require_unlock(update, context):
        return ConversationHandler.END

    key = utils.get_key(user["user_id"])
    if not key:
        if update.callback_query:
            await update.callback_query.edit_message_text(t(lang, "locked"))
        else:
            await update.effective_message.reply_text(t(lang, "locked"))
        return ConversationHandler.END

    if update.callback_query:
        await update.callback_query.edit_message_text(t(lang, "backup_start"))
    else:
        await update.effective_message.reply_text(t(lang, "backup_start"))

    raw_json = await db.export_entries_encrypted(user["user_id"])
    encrypted_backup = crypto.encrypt(raw_json, key)
    file_bytes = json.dumps({"vault_backup": True, "data": encrypted_backup}, ensure_ascii=False).encode()

    buf = io.BytesIO(file_bytes)
    buf.name = f"vault_backup_{user['user_id']}.json"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=buf,
        caption=t(lang, "backup_done"),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ─── /restore ─────────────────────────────────────────────────────────────────

async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    if not await _require_unlock(update, context):
        return ConversationHandler.END
    await update.effective_message.reply_text(t(lang, "restore_prompt"))
    return ST_RESTORE


async def rcv_restore_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    user_id = user["user_id"]

    key = utils.get_key(user_id)
    if not key:
        await update.message.reply_text(t(lang, "locked"))
        return ConversationHandler.END

    doc = update.message.document
    if not doc:
        await update.message.reply_text(t(lang, "restore_error"))
        return ConversationHandler.END

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        wrapper = json.loads(file_bytes.decode())
        raw_json = crypto.decrypt(wrapper["data"], key)
        before = await db.count_entries(user_id)
        await db.import_entries_from_backup(user_id, raw_json)
        after = await db.count_entries(user_id)
        await update.message.reply_text(t(lang, "restore_done", count=after - before))
    except Exception as e:
        logger.warning(f"Restore failed for {user_id}: {e}")
        await update.message.reply_text(t(lang, "restore_error"))

    return ConversationHandler.END


# ─── /setpin ──────────────────────────────────────────────────────────────────

async def cmd_setpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    if not await _require_unlock(update, context):
        return ConversationHandler.END
    await update.effective_message.reply_text(t(lang, "pin_prompt"))
    return ST_PIN_NEW


async def rcv_pin_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    pin = update.message.text.strip()
    if not pin.isdigit() or len(pin) != 4:
        await update.message.reply_text(t(lang, "pin_invalid"))
        return ST_PIN_NEW
    context.user_data["pin_new"] = pin
    await update.message.reply_text(t(lang, "pin_confirm"))
    return ST_PIN_CONFIRM


async def rcv_pin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    pin = update.message.text.strip()
    if pin != context.user_data.get("pin_new"):
        await update.message.reply_text(t(lang, "pin_mismatch"))
        return ST_PIN_CONFIRM
    await db.set_pin_hash(user["user_id"], crypto.hash_pin(pin, user["user_id"]))
    await update.message.reply_text(t(lang, "pin_set"))
    return ConversationHandler.END


# ─── /subscribe ───────────────────────────────────────────────────────────────

async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    plan_label = _plan_label(user, lang)

    kb_buttons = []
    if user["plan"] != PLAN_ONETIME:
        kb_buttons.append([InlineKeyboardButton(t(lang, "btn_buy_onetime"), callback_data="buy_onetime")])
    if not (user["plan"] == PLAN_PREMIUM and pay.is_plan_active(user)):
        kb_buttons.append([InlineKeyboardButton(t(lang, "btn_buy_premium"), callback_data="buy_premium")])
    kb_buttons.append([InlineKeyboardButton("🔙", callback_data="menu_home")])
    kb = InlineKeyboardMarkup(kb_buttons)

    text = t(lang, "subscribe_menu", plan=plan_label)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


async def cb_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await _get_user_or_create(update)
    lang = user["lang"]

    if query.data == "buy_onetime":
        if user["plan"] == PLAN_ONETIME:
            await query.message.reply_text(t(lang, "already_onetime"))
            return
        await pay.send_onetime_invoice(update, context, lang)
    elif query.data == "buy_premium":
        if user["plan"] == PLAN_PREMIUM and pay.is_plan_active(user):
            await query.message.reply_text(t(lang, "already_premium"))
            return
        await pay.send_premium_invoice(update, context, lang)


# ─── /refer ───────────────────────────────────────────────────────────────────

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user['user_id']}"
    count = await db.get_referral_count(user["user_id"])
    await update.effective_message.reply_text(
        t(lang, "refer_text", link=link, count=count), parse_mode="Markdown"
    )


# ─── /language ────────────────────────────────────────────────────────────────

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _get_user_or_create(update)
    lang = user["lang"]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_ru"), callback_data="setlang_ru"),
        InlineKeyboardButton(t(lang, "btn_en"), callback_data="setlang_en"),
    ]])
    await update.effective_message.reply_text(t(lang, "lang_menu"), reply_markup=kb)


async def cb_setlang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await _get_user_or_create(update)
    new_lang = "ru" if query.data == "setlang_ru" else "en"
    await db.set_lang(user["user_id"], new_lang)
    await query.edit_message_text(t(new_lang, "lang_set"))


# ─── Middleware: блокировка пользователей ────────────────────────────────────

async def _blocked_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id != OWNER_ID:
        if await db.is_user_blocked(user.id):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Ваш доступ к боту заблокирован. Обратитесь к администратору."
                )
            elif update.callback_query:
                await update.callback_query.answer("⛔ Доступ заблокирован.", show_alert=True)
            raise ApplicationHandlerStop()


# ─── Admin: вспомогательные функции ──────────────────────────────────────────

def _build_users_kb(managed: list) -> tuple[str, InlineKeyboardMarkup]:
    if not managed:
        text = "👥 *Управление пользователями*\n\nСписок пуст. Нажмите «➕ Добавить»."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить пользователя", callback_data="admin_add")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")],
        ])
        return text, kb

    lines = [f"👥 *Управление пользователями* — {len(managed)}\n"]
    buttons = []
    for m in managed:
        icon = "⛔" if m["is_blocked"] else "✅"
        notes_mark = " 📝" if m["notes"] else ""
        lines.append(f"{icon} #{m['id']} {m['custom_name']}{notes_mark}")
        buttons.append([InlineKeyboardButton(
            f"{icon} #{m['id']}  {m['custom_name']}{notes_mark}",
            callback_data=f"admin_view_{m['id']}",
        )])
    buttons.append([InlineKeyboardButton("➕ Добавить пользователя", callback_data="admin_add")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _build_user_detail(mu) -> tuple[str, InlineKeyboardMarkup]:
    status = "⛔ Заблокирован" if mu["is_blocked"] else "✅ Активен"
    toggle_label = "✅ Разблокировать" if mu["is_blocked"] else "⛔ Заблокировать"
    notes = mu["notes"] or "—"
    text = (
        f"👤 *Пользователь \\#{mu['id']}*\n\n"
        f"Имя: {mu['custom_name']}\n"
        f"Telegram ID: `{mu['telegram_id']}`\n"
        f"Статус: {status}\n"
        f"📝 Заметка: {notes}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=f"admin_toggle_{mu['id']}")],
        [
            InlineKeyboardButton("✏️ Переименовать", callback_data=f"admin_rename_{mu['id']}"),
            InlineKeyboardButton("📝 Заметка",        callback_data=f"admin_setnotes_{mu['id']}"),
        ],
        [InlineKeyboardButton("🗑️ Удалить из списка", callback_data=f"admin_del_{mu['id']}")],
        [InlineKeyboardButton("🔙 К списку",          callback_data="admin_tolist")],
    ])
    return text, kb


_CANCEL_KB = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_conv_cancel")]])


# ─── /admin ───────────────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(t("en", "not_admin"))
        return
    stats = await db.get_stats()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
    ])
    await update.message.reply_text(
        t("ru", "admin_stats", **stats), reply_markup=kb, parse_mode="Markdown"
    )


async def cb_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return

    data = query.data

    if data in ("admin_users", "admin_tolist"):
        managed = await db.get_all_managed_users()
        text, kb = _build_users_kb(managed)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("admin_view_"):
        custom_id = int(data[11:])
        mu = await db.get_managed_user_by_id(custom_id)
        if not mu:
            await query.edit_message_text("❌ Пользователь не найден.")
            return
        text, kb = _build_user_detail(mu)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("admin_toggle_"):
        custom_id = int(data[13:])
        await db.toggle_managed_user_blocked(custom_id)
        mu = await db.get_managed_user_by_id(custom_id)
        text, kb = _build_user_detail(mu)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("admin_del_") and not data.startswith("admin_delconfirm_"):
        custom_id = int(data[10:])
        mu = await db.get_managed_user_by_id(custom_id)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Да, удалить",  callback_data=f"admin_delconfirm_{custom_id}"),
            InlineKeyboardButton("❌ Нет",          callback_data=f"admin_view_{custom_id}"),
        ]])
        await query.edit_message_text(
            f"🗑️ Удалить *\\#{custom_id} {mu['custom_name']}* из списка?\n"
            "Это не разблокирует пользователя — удаляет только запись.",
            reply_markup=kb, parse_mode="MarkdownV2",
        )

    elif data.startswith("admin_delconfirm_"):
        custom_id = int(data[17:])
        await db.delete_managed_user(custom_id)
        managed = await db.get_all_managed_users()
        text, kb = _build_users_kb(managed)
        await query.edit_message_text(
            f"🗑️ Пользователь \\#{custom_id} удалён\\.\n\n" + text,
            reply_markup=kb, parse_mode="MarkdownV2",
        )

    elif data == "admin_back":
        stats = await db.get_stats()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        ])
        await query.edit_message_text(
            t("ru", "admin_stats", **stats), reply_markup=kb, parse_mode="Markdown"
        )


# ─── Admin conversation: добавить / переименовать / заметка ──────────────────

async def cb_admin_start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    await query.edit_message_text(
        "➕ *Новый пользователь*\n\nВведите Telegram ID\n_(числовой, например: `123456789`)_",
        reply_markup=_CANCEL_KB,
        parse_mode="Markdown",
    )
    return ST_ADMIN_ADD_ID


async def rcv_admin_add_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    raw = update.message.text.strip()
    try:
        telegram_id = int(raw)
    except ValueError:
        await update.message.reply_text(
            "❌ Должно быть число. Введите Telegram ID ещё раз:",
            reply_markup=_CANCEL_KB,
        )
        return ST_ADMIN_ADD_ID
    context.user_data["admin_add_tg_id"] = telegram_id
    await update.message.reply_text(
        f"ID: `{telegram_id}`\n\nВведите имя или метку для этого пользователя:",
        reply_markup=_CANCEL_KB,
        parse_mode="Markdown",
    )
    return ST_ADMIN_ADD_NAME


async def rcv_admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    telegram_id = context.user_data.pop("admin_add_tg_id", None)
    custom_name = update.message.text.strip()
    custom_id = await db.add_managed_user(telegram_id, custom_name)
    managed = await db.get_all_managed_users()
    text, kb = _build_users_kb(managed)
    await update.message.reply_text(
        f"✅ *Добавлен \\#{custom_id} {custom_name}*\n\n" + text,
        reply_markup=kb, parse_mode="MarkdownV2",
    )
    return ConversationHandler.END


async def cb_admin_start_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    custom_id = int(query.data.split("_")[-1])
    mu = await db.get_managed_user_by_id(custom_id)
    context.user_data["admin_edit_id"] = custom_id
    await query.edit_message_text(
        f"✏️ *Переименование \\#{custom_id}*\n\nТекущее: {mu['custom_name']}\n\nВведите новое имя:",
        reply_markup=_CANCEL_KB,
        parse_mode="MarkdownV2",
    )
    return ST_ADMIN_RENAME


async def rcv_admin_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    custom_id = context.user_data.pop("admin_edit_id", None)
    new_name = update.message.text.strip()
    await db.update_managed_user_name(custom_id, new_name)
    mu = await db.get_managed_user_by_id(custom_id)
    text, kb = _build_user_detail(mu)
    await update.message.reply_text(
        f"✅ Переименован: *#{custom_id} {new_name}*\n\n" + text,
        reply_markup=kb, parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cb_admin_start_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    custom_id = int(query.data.split("_")[-1])
    mu = await db.get_managed_user_by_id(custom_id)
    context.user_data["admin_edit_id"] = custom_id
    current = mu["notes"] or "—"
    await query.edit_message_text(
        f"📝 *Заметка для \\#{custom_id} {mu['custom_name']}*\n\n"
        f"Текущая: {current}\n\nВведите новую заметку \\(платёж, дата и т\\.д\\.\\):",
        reply_markup=_CANCEL_KB,
        parse_mode="MarkdownV2",
    )
    return ST_ADMIN_NOTES


async def rcv_admin_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    custom_id = context.user_data.pop("admin_edit_id", None)
    notes_text = update.message.text.strip()
    await db.update_managed_user_notes(custom_id, notes_text)
    mu = await db.get_managed_user_by_id(custom_id)
    text, kb = _build_user_detail(mu)
    await update.message.reply_text(
        f"📝 Заметка сохранена.\n\n" + text,
        reply_markup=kb, parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cb_admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("admin_add_tg_id", None)
    context.user_data.pop("admin_edit_id", None)
    managed = await db.get_all_managed_users()
    text, kb = _build_users_kb(managed)
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    return ConversationHandler.END


def _build_admin_conv_handler() -> ConversationHandler:
    cancel = [CallbackQueryHandler(cb_admin_conv_cancel, pattern="^admin_conv_cancel$")]
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_admin_start_add,    pattern="^admin_add$"),
            CallbackQueryHandler(cb_admin_start_rename, pattern=r"^admin_rename_\d+$"),
            CallbackQueryHandler(cb_admin_start_notes,  pattern=r"^admin_setnotes_\d+$"),
        ],
        states={
            ST_ADMIN_ADD_ID:   cancel + [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_admin_add_id)],
            ST_ADMIN_ADD_NAME: cancel + [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_admin_add_name)],
            ST_ADMIN_RENAME:   cancel + [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_admin_rename)],
            ST_ADMIN_NOTES:    cancel + [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_admin_notes)],
        },
        fallbacks=[
            CallbackQueryHandler(cb_admin_conv_cancel, pattern="^admin_conv_cancel$"),
            CommandHandler("admin", cmd_admin),
        ],
        per_message=False,
    )


# ─── Автобэкап ────────────────────────────────────────────────────────────────

async def auto_backup_job(bot):
    users = await db.get_premium_users_for_backup()
    for row in users:
        user_id = row["user_id"]
        key = utils.get_key(user_id)
        if key is None:
            continue
        try:
            user = await db.get_user(user_id)
            lang = user["lang"]
            raw_json = await db.export_entries_encrypted(user_id)
            encrypted_backup = crypto.encrypt(raw_json, key)
            file_bytes = json.dumps(
                {"vault_backup": True, "data": encrypted_backup}, ensure_ascii=False
            ).encode()
            buf = io.BytesIO(file_bytes)
            buf.name = f"vault_backup_{user_id}.json"
            await bot.send_document(
                chat_id=user_id,
                document=buf,
                caption=t(lang, "backup_done"),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Auto-backup failed for {user_id}: {e}")


# ─── Сборка приложения ────────────────────────────────────────────────────────

def _build_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            ST_LANG:           [CallbackQueryHandler(cb_lang, pattern="^lang_")],
            ST_MASTER_NEW:     [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_master_new)],
            ST_MASTER_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_master_confirm)],
            ST_MASTER_ENTER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_master_enter)],
            ST_PIN_ENTER:      [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_pin_enter)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )


def _build_add_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", cmd_add),
            CallbackQueryHandler(cmd_add, pattern="^menu_add$"),
        ],
        states={
            ST_ADD_CAT:     [CallbackQueryHandler(cb_add_cat, pattern="^(addcat_|cancel_add)")],
            ST_ADD_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_add_name)],
            ST_ADD_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_add_content)],
            ST_ADD_TAGS:    [MessageHandler(filters.TEXT, rcv_add_tags)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )


def _build_search_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("search", cmd_search),
            CallbackQueryHandler(cmd_search, pattern="^menu_search$"),
        ],
        states={
            ST_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_search)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
    )


def _build_pin_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("setpin", cmd_setpin),
            CallbackQueryHandler(cb_settings, pattern="^settings_pin$"),
        ],
        states={
            ST_PIN_NEW:     [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_pin_new)],
            ST_PIN_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, rcv_pin_confirm)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
    )


def _build_restore_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("restore", cmd_restore)],
        states={
            ST_RESTORE: [MessageHandler(filters.Document.ALL, rcv_restore_file)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
    )


async def post_init(application: Application):
    await db.init_db()
    await application.bot.set_my_commands([
        BotCommand("start",     "🔐 Start / Главное меню"),
        BotCommand("add",       "➕ Add entry / Добавить запись"),
        BotCommand("list",      "📋 List / Список"),
        BotCommand("search",    "🔍 Search / Поиск"),
        BotCommand("favorites", "⭐ Favorites / Избранное"),
        BotCommand("generate",  "⚙️ Generator / Генератор"),
        BotCommand("backup",    "💾 Backup / Бэкап"),
        BotCommand("restore",   "📂 Restore / Восстановить"),
        BotCommand("setpin",    "🔢 Set PIN"),
        BotCommand("subscribe", "💎 Subscribe / Подписка"),
        BotCommand("refer",     "👥 Referral / Реферал"),
        BotCommand("language",  "🌐 Language / Язык"),
        BotCommand("admin",     "📊 Панель администратора"),
    ])


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Middleware: блокировка пользователей (группа -1 — выполняется первой)
    app.add_handler(TypeHandler(Update, _blocked_middleware), group=-1)

    # ConversationHandlers (порядок важен — от частного к общему)
    app.add_handler(_build_conv_handler())
    app.add_handler(_build_add_handler())
    app.add_handler(_build_search_handler())
    app.add_handler(_build_pin_handler())
    app.add_handler(_build_restore_handler())
    app.add_handler(_build_admin_conv_handler())  # admin inline-flow

    # Обычные команды
    app.add_handler(CommandHandler("list",      cmd_list))
    app.add_handler(CommandHandler("favorites", cmd_favorites))
    app.add_handler(CommandHandler("generate",  cmd_generate))
    app.add_handler(CommandHandler("backup",    cmd_backup))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("refer",     cmd_refer))
    app.add_handler(CommandHandler("language",  cmd_language))
    app.add_handler(CommandHandler("admin",     cmd_admin))

    # Inline /get_N /del_N /fav_N
    app.add_handler(MessageHandler(
        filters.Regex(r"^/(get|del|fav)_\d+$"), handle_inline_cmd
    ))

    # CallbackQuery (admin_conv_handler выше перехватывает admin_add/rename/setnotes)
    app.add_handler(CallbackQueryHandler(cb_admin_panel,    pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(cb_menu,           pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(cb_list_cat,       pattern="^listcat_"))
    app.add_handler(CallbackQueryHandler(cb_generate,       pattern="^gen_"))
    app.add_handler(CallbackQueryHandler(cb_buy,            pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(cb_confirm_delete, pattern="^(confirm_del_|cancel_del)"))
    app.add_handler(CallbackQueryHandler(cb_setlang,        pattern="^setlang_"))
    app.add_handler(CallbackQueryHandler(cb_settings,       pattern="^settings_lang_"))

    # Telegram Stars
    app.add_handler(PreCheckoutQueryHandler(pay.precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, pay.successful_payment_handler))

    # Автобэкап каждое воскресенье 10:00 UTC
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        auto_backup_job,
        trigger="cron",
        day_of_week="sun",
        hour=10, minute=0,
        args=[app.bot],
    )
    scheduler.start()

    logger.info("Vault Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
