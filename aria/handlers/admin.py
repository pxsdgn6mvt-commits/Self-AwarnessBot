"""
Admin commands — platform administrator + salon service catalogue (categories/subcategories).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import aria.db.repo as repo
from aria.config import settings
from aria.filters import SetupDone
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_TELEGRAM_ID


class AddBot(StatesGroup):
    waiting_token = State()


class AdminBroadcast(StatesGroup):
    waiting_text = State()


class CatalogueSG(StatesGroup):
    add_category  = State()
    add_item      = State()
    add_price     = State()
    add_duration  = State()
    edit_price    = State()
    edit_duration = State()


# ── Service catalogue (categories / subcategories) ────────────────────────────

async def _categories_kb(tenant_id: int) -> InlineKeyboardMarkup:
    cats = await repo.get_categories(tenant_id)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=c["name"], callback_data=f"adm:cat:{c['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"adm:dcat:{c['id']}"),
        ]
        for c in cats
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить категорию", callback_data="adm:addcat")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _items_kb(category_id: int, tenant_id: int) -> InlineKeyboardMarkup:
    items = await repo.get_items(category_id)
    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        parts = [it["name"]]
        if it["price"] is not None:
            parts.append(f"{int(it['price'])}€")
        if it["duration_minutes"] is not None:
            parts.append(f"{it['duration_minutes']}мин")
        label = " · ".join(parts)
        rows.append([
            InlineKeyboardButton(text=label,  callback_data="adm:noop"),
            InlineKeyboardButton(text="✏️",   callback_data=f"adm:eitem:{it['id']}:{category_id}"),
            InlineKeyboardButton(text="🗑",   callback_data=f"adm:dsub:{it['id']}:{category_id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить услугу", callback_data=f"adm:addsub:{category_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:services")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:services", SetupDone())
async def show_services(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "👩‍💼 <b>Управление услугами</b>\n\nНажмите на категорию или добавьте новую.",
        reply_markup=await _categories_kb(tenant.id),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:addcat", SetupDone())
async def prompt_add_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(CatalogueSG.add_category)
    await state.update_data(tenant_id=tenant.id)
    await callback.message.answer("Введите название новой категории:")
    await callback.answer()


@router.message(CatalogueSG.add_category)
async def save_category(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return
    data = await state.get_data()
    tenant_id = data.get("tenant_id", 1)
    await repo.add_category(tenant_id, name)
    await state.clear()
    await message.answer(
        f"✅ Категория «{name}» добавлена.",
        reply_markup=await _categories_kb(tenant_id),
    )


@router.callback_query(F.data.startswith("adm:dcat:"), SetupDone())
async def delete_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await repo.delete_category(int(callback.data.split(":")[-1]))
    await state.clear()
    await callback.message.edit_text(
        "🗑 Категория удалена.",
        reply_markup=await _categories_kb(tenant.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cat:"), SetupDone())
async def show_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    cat_id = int(callback.data.split(":")[-1])
    cats = await repo.get_categories(tenant.id)
    cat = next((c for c in cats if c["id"] == cat_id), None)
    if not cat:
        await callback.answer("Категория не найдена.")
        return
    items = await repo.get_items(cat_id)
    await callback.message.edit_text(
        f"📂 <b>{cat['name']}</b> — {len(items)} услуг(а)\n\nНажмите 🗑 рядом с услугой, чтобы удалить.",
        reply_markup=await _items_kb(cat_id, tenant.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:addsub:"), SetupDone())
async def prompt_add_item(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[-1])
    cats = await repo.get_categories(tenant.id)
    cat = next((c for c in cats if c["id"] == cat_id), None)
    cat_name = cat["name"] if cat else "?"
    await state.set_state(CatalogueSG.add_item)
    await state.update_data(category_id=cat_id, category_name=cat_name, tenant_id=tenant.id)
    await callback.message.answer(f"Введите название услуги для «{cat_name}»:")
    await callback.answer()


@router.message(CatalogueSG.add_item, F.text.func(lambda x: not x.startswith("/")))
async def save_item_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return
    await state.update_data(item_name=name)
    await state.set_state(CatalogueSG.add_price)
    await message.answer(
        f"💰 Цена услуги «{name}» (например: <code>50</code>)\n"
        "Или /skip чтобы не указывать.",
        parse_mode="HTML",
    )


@router.message(CatalogueSG.add_price, Command("skip"))
async def skip_price(message: Message, state: FSMContext) -> None:
    await state.update_data(item_price=None)
    await state.set_state(CatalogueSG.add_duration)
    await message.answer(
        "⏱ Длительность в минутах (например: <code>60</code>)\n"
        "Или /skip чтобы не указывать.",
        parse_mode="HTML",
    )


@router.message(CatalogueSG.add_price, F.text.func(lambda x: not x.startswith("/")))
async def save_item_price(message: Message, state: FSMContext) -> None:
    text = message.text.strip().replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите число, например <code>50</code>, или /skip:", parse_mode="HTML")
        return
    await state.update_data(item_price=price)
    await state.set_state(CatalogueSG.add_duration)
    await message.answer(
        "⏱ Длительность в минутах (например: <code>60</code>)\n"
        "Или /skip чтобы не указывать.",
        parse_mode="HTML",
    )


@router.message(CatalogueSG.add_duration, Command("skip"))
async def skip_duration(message: Message, state: FSMContext) -> None:
    await _finish_add_item(message, state, duration=None)


@router.message(CatalogueSG.add_duration, F.text.func(lambda x: not x.startswith("/")))
async def save_item_duration(message: Message, state: FSMContext) -> None:
    try:
        duration = int(message.text.strip())
        if duration <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число минут, например <code>60</code>, или /skip:", parse_mode="HTML")
        return
    await _finish_add_item(message, state, duration=duration)


async def _finish_add_item(message: Message, state: FSMContext, duration: int | None) -> None:
    data = await state.get_data()
    name  = data["item_name"]
    price = data.get("item_price")
    await repo.add_item(data["category_id"], name, price=price, duration_minutes=duration)
    await state.clear()
    parts = [f"✅ Услуга «{name}» добавлена"]
    if price is not None:
        parts.append(f"Цена: {int(price)}€")
    if duration is not None:
        parts.append(f"Длительность: {duration} мин")
    await message.answer(
        "\n".join(parts),
        reply_markup=await _items_kb(data["category_id"], data.get("tenant_id", 1)),
    )


@router.callback_query(F.data.startswith("adm:dsub:"), SetupDone())
async def delete_item(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = callback.data.split(":")
    await repo.delete_item(int(parts[2]))
    await callback.message.edit_reply_markup(
        reply_markup=await _items_kb(int(parts[3]), tenant.id)
    )
    await callback.answer("Услуга удалена")


@router.callback_query(F.data.startswith("adm:eitem:"), SetupDone())
async def prompt_edit_item(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = callback.data.split(":")
    item_id, cat_id = int(parts[2]), int(parts[3])
    items = await repo.get_items(cat_id)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        await callback.answer("Услуга не найдена.")
        return
    label_parts = [item["name"]]
    if item["price"] is not None:
        label_parts.append(f"цена: {int(item['price'])}€")
    if item["duration_minutes"] is not None:
        label_parts.append(f"{item['duration_minutes']} мин")
    info = ", ".join(label_parts)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Цена",   callback_data=f"adm:eprice:{item_id}:{cat_id}"),
            InlineKeyboardButton(text="⏱ Длит.",   callback_data=f"adm:edur:{item_id}:{cat_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"adm:cat:{cat_id}")],
    ])
    await callback.message.edit_text(f"✏️ <b>{info}</b>\n\nЧто редактировать?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:eprice:"), SetupDone())
async def prompt_edit_price(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = callback.data.split(":")
    item_id, cat_id = int(parts[2]), int(parts[3])
    await state.set_state(CatalogueSG.edit_price)
    await state.update_data(edit_item_id=item_id, edit_cat_id=cat_id, tenant_id=tenant.id)
    await callback.message.answer(
        "💰 Введи новую цену (например: <code>50</code>)\n"
        "Или /skip чтобы убрать цену.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CatalogueSG.edit_price, Command("skip"))
async def skip_edit_price(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await repo.update_item_price(data["edit_item_id"], None)
    await state.clear()
    await message.answer(
        "✅ Цена удалена.",
        reply_markup=await _items_kb(data["edit_cat_id"], data.get("tenant_id", 1)),
    )


@router.message(CatalogueSG.edit_price, F.text.func(lambda x: not x.startswith("/")))
async def save_edit_price(message: Message, state: FSMContext) -> None:
    text = message.text.strip().replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите число, например <code>50</code>, или /skip:", parse_mode="HTML")
        return
    data = await state.get_data()
    await repo.update_item_price(data["edit_item_id"], price)
    await state.clear()
    await message.answer(
        f"✅ Цена обновлена: {int(price)}€",
        reply_markup=await _items_kb(data["edit_cat_id"], data.get("tenant_id", 1)),
    )


@router.callback_query(F.data.startswith("adm:edur:"), SetupDone())
async def prompt_edit_duration(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = callback.data.split(":")
    item_id, cat_id = int(parts[2]), int(parts[3])
    await state.set_state(CatalogueSG.edit_duration)
    await state.update_data(edit_item_id=item_id, edit_cat_id=cat_id, tenant_id=tenant.id)
    await callback.message.answer(
        "⏱ Введи длительность в минутах (например: <code>60</code>)\n"
        "Или /skip чтобы убрать.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CatalogueSG.edit_duration, Command("skip"))
async def skip_edit_duration(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await repo.update_item_duration(data["edit_item_id"], None)
    await state.clear()
    await message.answer(
        "✅ Длительность удалена.",
        reply_markup=await _items_kb(data["edit_cat_id"], data.get("tenant_id", 1)),
    )


@router.message(CatalogueSG.edit_duration, F.text.func(lambda x: not x.startswith("/")))
async def save_edit_duration(message: Message, state: FSMContext) -> None:
    try:
        duration = int(message.text.strip())
        if duration <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число минут, например <code>60</code>, или /skip:", parse_mode="HTML")
        return
    data = await state.get_data()
    await repo.update_item_duration(data["edit_item_id"], duration)
    await state.clear()
    await message.answer(
        f"✅ Длительность обновлена: {duration} мин",
        reply_markup=await _items_kb(data["edit_cat_id"], data.get("tenant_id", 1)),
    )


@router.callback_query(F.data == "adm:noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "adm:main", SetupDone())
async def show_main_admin(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    from aria.handlers.menu import _admin_inline_kb, _owner_settings_kb, _is_admin_bot
    if _is_admin_bot(tenant, callback.from_user.id):
        kb = _admin_inline_kb()
        text = "👑 <b>Управление платформой</b>"
    else:
        kb = _owner_settings_kb()
        text = "⚙️ <b>Настройки</b>"
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Keyboard button handlers (ADMIN_KB) ───────────────────────────────────────

@router.message(F.text == "📋 Список ботов")
async def kb_list_bots(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return
    tenants = await repo.list_active_tenants()
    if not tenants:
        await message.answer("Нет активных ботов.")
        return
    lines = []
    for t in tenants:
        status = "✅" if t["setup_complete"] else "⏳ ожидает настройки"
        cal = "📅" if t["google_cal_id"] else "💾"
        tz = t.get("timezone") or "UTC"
        owner = t["owner_tg_id"] or "—"
        lines.append(
            f"#{t['id']} <b>{t['salon_name']}</b> {cal}\n"
            f"  {status} | tz: {tz} | owner: {owner}"
        )
    await message.answer("Активные боты:\n\n" + "\n\n".join(lines))


@router.message(F.text == "➕ Добавить бота")
async def kb_add_bot(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AddBot.waiting_token)
    await message.answer(
        "Пришли токен нового бота (получить у @BotFather).\n\n"
        "После добавления владелец салона откроет бот и пройдёт настройку за 1 минуту."
    )


@router.message(F.text == "📣 Рассылка")
async def kb_broadcast(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminBroadcast.waiting_text)
    await message.answer("Введи текст рассылки. /cancel чтобы отменить.")


@router.message(AdminBroadcast.waiting_text)
async def process_broadcast_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    await state.clear()

    from aria import runtime
    tenants = await repo.list_active_owner_bots()
    sent = failed = 0
    for t in tenants:
        bot = runtime.bots.get(t["id"])
        if not bot:
            failed += 1
            continue
        try:
            await bot.send_message(chat_id=t["owner_tg_id"], text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:
            log.warning("Broadcast failed for tenant %d: %s", t["id"], exc)
            failed += 1

    await message.answer(f"✅ Отправлено: {sent}, ошибок: {failed}")


# ── /add_bot ──────────────────────────────────────────────────────────────────

@router.message(Command("add_bot"))
async def cmd_add_bot(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AddBot.waiting_token)
    await message.answer(
        "Пришли токен нового бота (получить у @BotFather).\n\n"
        "После добавления владелец салона откроет бот и пройдёт настройку за 1 минуту."
    )


@router.message(AddBot.waiting_token, F.text.func(lambda x: not x.startswith("/")))
async def process_new_token(message: Message, state: FSMContext) -> None:
    token = message.text.strip()

    if ":" not in token or len(token) < 30:
        await message.answer("Это не похоже на токен Telegram. Попробуй ещё раз или /cancel.")
        return

    existing = await repo.get_tenant_by_token(token)
    if existing:
        await state.clear()
        await message.answer(
            f"Этот токен уже есть в системе (салон #{existing['id']}: {existing['salon_name']})."
        )
        return

    tenant_id = await repo.create_tenant(bot_token=token, setup_complete=False)
    await state.clear()

    await message.answer(
        f"✅ Добавлен новый бот (ID #{tenant_id}).\n\n"
        f"Бот запустится в течение 60 секунд.\n"
        f"Скажи владельцу: открой бот и отправь /start — Aria проведёт настройку."
    )
    log.info("Admin added new tenant #%d", tenant_id)


# ── /list_bots ────────────────────────────────────────────────────────────────

@router.message(Command("list_bots"))
async def cmd_list_bots(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return

    tenants = await repo.list_active_tenants()
    if not tenants:
        await message.answer("Нет активных ботов.")
        return

    lines = []
    for t in tenants:
        status = "✅" if t["setup_complete"] else "⏳ ожидает настройки"
        cal = "📅" if t["google_cal_id"] else "💾"
        tz = t.get("timezone") or "UTC"
        owner = t["owner_tg_id"] or "—"
        lines.append(
            f"#{t['id']} <b>{t['salon_name']}</b> {cal}\n"
            f"  {status} | tz: {tz} | owner: {owner}"
        )

    await message.answer("Активные боты:\n\n" + "\n\n".join(lines))


# ── /reset_bot ────────────────────────────────────────────────────────────────

@router.message(Command("reset_bot"))
async def cmd_reset_bot(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /reset_bot <id>\nСбрасывает setup — владелец пройдёт настройку заново.")
        return

    tid = int(parts[1])
    t = await repo.get_tenant(tid)
    if not t:
        await message.answer(f"Бот #{tid} не найден.")
        return

    await repo.update_tenant(tid, setup_complete=False, owner_tg_id=None)
    from aria.middleware import TenantMiddleware
    from aria.services.booking import invalidate_adapter
    TenantMiddleware.invalidate(t["bot_token"])
    invalidate_adapter(tid)
    await message.answer(
        f"✅ Бот #{tid} ({t['salon_name']}) сброшен.\n"
        "Владелец снова пройдёт настройку при /start."
    )
    log.info("Admin reset setup for tenant #%d", tid)


# ── /deactivate_bot ───────────────────────────────────────────────────────────

@router.message(Command("deactivate_bot"))
async def cmd_deactivate_bot(message: Message, tenant: TenantConfig) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /deactivate_bot <id>")
        return

    tid = int(parts[1])
    t = await repo.get_tenant(tid)
    if not t:
        await message.answer(f"Бот #{tid} не найден.")
        return

    await repo.set_tenant_active(tid, False)
    await message.answer(f"✅ Бот #{tid} ({t['salon_name']}) деактивирован.")
    log.info("Admin deactivated tenant #%d", tid)


# ── /cancel (clears any FSM state) ───────────────────────────────────────────

@router.message(StateFilter("*"), Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("Отменено.")
    else:
        await message.answer("Нечего отменять.")


# ── /broadcast ────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.answer("Использование: /broadcast <текст>")
        return

    text = parts[1]
    from aria import runtime
    tenants = await repo.list_active_owner_bots()
    sent = failed = 0
    for t in tenants:
        bot = runtime.bots.get(t["id"])
        if not bot:
            failed += 1
            continue
        try:
            await bot.send_message(chat_id=t["owner_tg_id"], text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:
            log.warning("Broadcast failed for tenant %d: %s", t["id"], exc)
            failed += 1

    await message.answer(f"✅ Отправлено: {sent}, ошибок: {failed}")


# ── /set_vip / /revoke_vip ────────────────────────────────────────────────────

@router.message(Command("set_vip"))
async def cmd_set_vip(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "Использование: /set_vip <tenant_id> <user_id> [дней]\n"
            "Пример: /set_vip 1 123456789 30"
        )
        return

    try:
        tid     = int(parts[1])
        user_id = int(parts[2])
        days    = int(parts[3]) if len(parts) > 3 else None
    except ValueError:
        await message.answer("Неверный формат. Пример: /set_vip 1 123456789 30")
        return

    vip_until = datetime.now(timezone.utc) + timedelta(days=days) if days else None
    await repo.set_client_vip(tid, user_id, True, vip_until)

    until_str = vip_until.strftime("%d.%m.%Y") if vip_until else "бессрочно"
    await message.answer(
        f"✅ VIP назначен: user {user_id} в тенанте #{tid}, действует до {until_str}"
    )
    log.info("Admin set VIP: tenant %d user %d until %s", tid, user_id, until_str)


@router.message(Command("revoke_vip"))
async def cmd_revoke_vip(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Использование: /revoke_vip <tenant_id> <user_id>")
        return

    try:
        tid     = int(parts[1])
        user_id = int(parts[2])
    except ValueError:
        await message.answer("Неверный формат.")
        return

    await repo.set_client_vip(tid, user_id, False, None)
    await message.answer(f"✅ VIP отозван: user {user_id} в тенанте #{tid}")
    log.info("Admin revoked VIP: tenant %d user %d", tid, user_id)
