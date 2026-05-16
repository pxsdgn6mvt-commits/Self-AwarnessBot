"""Owner-only admin panel for managing the service catalogue."""

from __future__ import annotations

import logging

from aiogram import F, Router
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
from aria.config import TenantConfig
from aria.handlers.start import resolve_owner

log = logging.getLogger(__name__)
router = Router()


class AdminSG(StatesGroup):
    add_category = State()
    add_item     = State()


async def _is_owner(user_id: int, tenant: TenantConfig) -> bool:
    owner_id = await resolve_owner(user_id, tenant)
    return owner_id is not None and user_id == owner_id


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
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _items_kb(category_id: int, tenant_id: int) -> InlineKeyboardMarkup:
    items = await repo.get_items(category_id)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=it["name"], callback_data="adm:noop"),
            InlineKeyboardButton(text="🗑", callback_data=f"adm:dsub:{it['id']}:{category_id}"),
        ]
        for it in items
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить услугу", callback_data=f"adm:addsub:{category_id}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:services")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(message.from_user.id, tenant):
        return
    await state.clear()
    await message.answer(
        "👩‍💼 <b>Управление услугами</b>\n\n"
        "Нажмите на категорию для управления услугами внутри.\n"
        "🗑 — удалить категорию со всеми услугами.",
        parse_mode="HTML",
        reply_markup=await _categories_kb(tenant.tenant_id),
    )


@router.callback_query(F.data == "adm:services")
async def show_services(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(
        "👩‍💼 <b>Управление услугами</b>\n\nНажмите на категорию или добавьте новую.",
        parse_mode="HTML",
        reply_markup=await _categories_kb(tenant.tenant_id),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:addcat")
async def prompt_add_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    await state.set_state(AdminSG.add_category)
    await state.update_data(tenant_id=tenant.tenant_id)
    await callback.message.answer("Введите название новой категории:")
    await callback.answer()


@router.message(AdminSG.add_category)
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


@router.callback_query(F.data.startswith("adm:dcat:"))
async def delete_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    await repo.delete_category(int(callback.data.split(":")[-1]))
    await state.clear()
    await callback.message.edit_text(
        "🗑 Категория удалена.",
        reply_markup=await _categories_kb(tenant.tenant_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cat:"))
async def show_category(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    await state.clear()
    cat_id = int(callback.data.split(":")[-1])
    cats = await repo.get_categories(tenant.tenant_id)
    cat = next((c for c in cats if c["id"] == cat_id), None)
    if not cat:
        await callback.answer("Категория не найдена.")
        return
    items = await repo.get_items(cat_id)
    await callback.message.edit_text(
        f"📂 <b>{cat['name']}</b> — {len(items)} услуг(а)\n\nНажмите 🗑 рядом с услугой, чтобы удалить.",
        parse_mode="HTML",
        reply_markup=await _items_kb(cat_id, tenant.tenant_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:addsub:"))
async def prompt_add_item(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    cat_id = int(callback.data.split(":")[-1])
    cats = await repo.get_categories(tenant.tenant_id)
    cat = next((c for c in cats if c["id"] == cat_id), None)
    cat_name = cat["name"] if cat else "?"
    await state.set_state(AdminSG.add_item)
    await state.update_data(category_id=cat_id, category_name=cat_name, tenant_id=tenant.tenant_id)
    await callback.message.answer(f"Введите название услуги для «{cat_name}»:")
    await callback.answer()


@router.message(AdminSG.add_item)
async def save_item(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return
    data = await state.get_data()
    await repo.add_item(data["category_id"], name)
    await state.clear()
    await message.answer(
        f"✅ Услуга «{name}» добавлена в «{data['category_name']}».",
        reply_markup=await _items_kb(data["category_id"], data.get("tenant_id", 1)),
    )


@router.callback_query(F.data.startswith("adm:dsub:"))
async def delete_item(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    parts = callback.data.split(":")
    await repo.delete_item(int(parts[2]))
    await callback.message.edit_reply_markup(
        reply_markup=await _items_kb(int(parts[3]), tenant.tenant_id)
    )
    await callback.answer("Услуга удалена")


@router.callback_query(F.data == "adm:noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
