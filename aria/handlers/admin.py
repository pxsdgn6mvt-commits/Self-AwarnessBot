"""
Owner-only admin panel for managing the service catalogue.

Access: only ARIA_OWNER_TELEGRAM_ID can use /admin.
Flow:
  /admin → category list
    [+ Добавить категорию] → type name → saved
    [category row] → item list
      [+ Добавить услугу] → type name → saved
      [🗑 item]          → deleted
    [🗑 category]        → deleted (cascades to items)
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
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

log = logging.getLogger(__name__)
router = Router()


# ── FSM ───────────────────────────────────────────────────────────────────────

class AdminSG(StatesGroup):
    add_category = State()
    add_item     = State()   # data: {"category_id": int, "category_name": str}


# ── Guards ────────────────────────────────────────────────────────────────────

def _is_owner(user_id: int) -> bool:
    return bool(settings.OWNER_TELEGRAM_ID) and user_id == settings.OWNER_TELEGRAM_ID


# ── Keyboard builders ─────────────────────────────────────────────────────────

async def _categories_kb() -> InlineKeyboardMarkup:
    cats = await repo.get_categories()
    rows: list[list[InlineKeyboardButton]] = []
    for cat in cats:
        rows.append([
            InlineKeyboardButton(text=cat["name"], callback_data=f"adm:cat:{cat['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"adm:dcat:{cat['id']}"),
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить категорию", callback_data="adm:addcat")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _items_kb(category_id: int) -> InlineKeyboardMarkup:
    items = await repo.get_items(category_id)
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        rows.append([
            InlineKeyboardButton(text=item["name"], callback_data="adm:noop"),
            InlineKeyboardButton(text="🗑", callback_data=f"adm:dsub:{item['id']}:{category_id}"),
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить услугу", callback_data=f"adm:addsub:{category_id}")
    ])
    rows.append([
        InlineKeyboardButton(text="← Назад", callback_data="adm:services")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Entry point ───────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "👩‍💼 <b>Управление услугами</b>\n\n"
        "Нажмите на категорию, чтобы управлять услугами внутри неё.\n"
        "🗑 — удалить категорию со всеми услугами.",
        parse_mode="HTML",
        reply_markup=await _categories_kb(),
    )


# ── Category list ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:services")
async def show_services(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(
        "👩‍💼 <b>Управление услугами</b>\n\n"
        "Нажмите на категорию или добавьте новую.",
        parse_mode="HTML",
        reply_markup=await _categories_kb(),
    )
    await callback.answer()


# ── Add category ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:addcat")
async def prompt_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminSG.add_category)
    await callback.message.answer("Введите название новой категории:")
    await callback.answer()


@router.message(AdminSG.add_category)
async def save_category(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return
    await repo.add_category(name)
    await state.clear()
    await message.answer(
        f"✅ Категория «{name}» добавлена.",
        reply_markup=await _categories_kb(),
    )


# ── Delete category ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:dcat:"))
async def delete_category(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    cat_id = int(callback.data.split(":")[-1])
    await repo.delete_category(cat_id)
    await state.clear()
    await callback.message.edit_text(
        "🗑 Категория удалена.",
        reply_markup=await _categories_kb(),
    )
    await callback.answer()


# ── View category items ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:cat:"))
async def show_category(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    cat_id = int(callback.data.split(":")[-1])
    cats = await repo.get_categories()
    cat = next((c for c in cats if c["id"] == cat_id), None)
    if not cat:
        await callback.answer("Категория не найдена.")
        return
    items = await repo.get_items(cat_id)
    count = len(items)
    await callback.message.edit_text(
        f"📂 <b>{cat['name']}</b> — {count} услуг(а)\n\n"
        "Нажмите 🗑 рядом с услугой, чтобы удалить её.",
        parse_mode="HTML",
        reply_markup=await _items_kb(cat_id),
    )
    await callback.answer()


# ── Add item ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:addsub:"))
async def prompt_add_item(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    cat_id = int(callback.data.split(":")[-1])
    cats = await repo.get_categories()
    cat = next((c for c in cats if c["id"] == cat_id), None)
    cat_name = cat["name"] if cat else "?"
    await state.set_state(AdminSG.add_item)
    await state.update_data(category_id=cat_id, category_name=cat_name)
    await callback.message.answer(f"Введите название услуги для категории «{cat_name}»:")
    await callback.answer()


@router.message(AdminSG.add_item)
async def save_item(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return
    data = await state.get_data()
    cat_id: int = data["category_id"]
    cat_name: str = data["category_name"]
    await repo.add_item(cat_id, name)
    await state.clear()
    await message.answer(
        f"✅ Услуга «{name}» добавлена в «{cat_name}».",
        reply_markup=await _items_kb(cat_id),
    )


# ── Delete item ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:dsub:"))
async def delete_item(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    # format: adm:dsub:{item_id}:{cat_id}
    parts = callback.data.split(":")
    item_id = int(parts[2])
    cat_id  = int(parts[3])
    await repo.delete_item(item_id)
    await callback.message.edit_reply_markup(reply_markup=await _items_kb(cat_id))
    await callback.answer("Услуга удалена")


# ── Noop (item label button — no action) ─────────────────────────────────────

@router.callback_query(F.data == "adm:noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
