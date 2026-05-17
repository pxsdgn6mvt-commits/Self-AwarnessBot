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


# ── Email settings ─────────────────────────────────────────────────────────────

class EmailSG(StatesGroup):
    address  = State()
    password = State()
    senders  = State()


_TIMEZONES = [
    ("Москва (UTC+3)",      "Europe/Moscow"),
    ("Киев (UTC+3)",        "Europe/Kiev"),
    ("Минск (UTC+3)",       "Europe/Minsk"),
    ("Тбилиси (UTC+4)",    "Asia/Tbilisi"),
    ("Баку (UTC+4)",        "Asia/Baku"),
    ("Ереван (UTC+4)",      "Asia/Yerevan"),
    ("Алматы (UTC+5)",      "Asia/Almaty"),
    ("Ташкент (UTC+5)",     "Asia/Tashkent"),
    ("Берлин (UTC+1/2)",    "Europe/Berlin"),
    ("Лондон (UTC+0/1)",    "Europe/London"),
    ("UTC+0",               "UTC"),
]


def _main_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Услуги и категории", callback_data="adm:services")],
        [InlineKeyboardButton(text="📧 Email мониторинг",   callback_data="adm:email")],
        [InlineKeyboardButton(text="⏰ Часовой пояс",       callback_data="adm:timezone")],
    ])


async def _email_status_kb(tenant_id: int) -> InlineKeyboardMarkup:
    row = await repo.get_email_settings(tenant_id)
    has_email = row and row["email_address"]
    rows = []
    if has_email:
        rows.append([InlineKeyboardButton(text="✏️ Изменить", callback_data="adm:email:setup")])
        rows.append([InlineKeyboardButton(text="🗑 Отключить", callback_data="adm:email:clear")])
    else:
        rows.append([InlineKeyboardButton(text="➕ Подключить email", callback_data="adm:email:setup")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("admin"))
async def cmd_admin_v2(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(message.from_user.id, tenant):
        return
    await state.clear()
    await message.answer(
        "⚙️ <b>Панель управления</b>",
        parse_mode="HTML",
        reply_markup=_main_admin_kb(),
    )


@router.callback_query(F.data == "adm:main")
async def show_main_admin(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Панель управления</b>",
        parse_mode="HTML",
        reply_markup=_main_admin_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:email")
async def show_email_menu(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    row = await repo.get_email_settings(tenant.tenant_id)
    has_email = row and row["email_address"]
    if has_email:
        senders = row["email_allowed_senders"] or "все"
        text = (
            f"📧 <b>Email мониторинг</b>\n\n"
            f"Адрес: <code>{row['email_address']}</code>\n"
            f"Сервер: {row['email_imap_server']}:{row['email_imap_port']}\n"
            f"Разрешённые отправители: {senders}\n"
            f"Опрос каждые: {row['email_poll_seconds']} сек"
        )
    else:
        text = (
            "📧 <b>Email мониторинг</b>\n\n"
            "Не настроен.\n\n"
            "Бот будет проверять входящие письма от нужных отправителей "
            "и уведомлять вас в Telegram."
        )
    await callback.message.edit_text(text, parse_mode="HTML",
                                     reply_markup=await _email_status_kb(tenant.tenant_id))
    await callback.answer()


@router.callback_query(F.data == "adm:email:clear")
async def clear_email(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    await repo.clear_email_settings(tenant.tenant_id)
    await callback.message.edit_text(
        "📧 Email мониторинг отключён.",
        reply_markup=await _email_status_kb(tenant.tenant_id),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:email:setup")
async def start_email_setup(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    await state.set_state(EmailSG.address)
    await state.update_data(tenant_id=tenant.tenant_id)
    await callback.message.answer(
        "📧 <b>Шаг 1 из 3 — Email адрес</b>\n\n"
        "Введите email-адрес для мониторинга:\n"
        "<i>Пример: salon@gmail.com</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EmailSG.address)
async def email_got_address(message: Message, state: FSMContext) -> None:
    addr = message.text.strip()
    if "@" not in addr:
        await message.answer("Введите корректный email-адрес:")
        return
    await state.update_data(email_address=addr)
    await state.set_state(EmailSG.password)

    is_gmail = "gmail" in addr.lower()
    hint = (
        "\n\n⚠️ <b>Gmail:</b> обычный пароль не подойдёт!\n"
        "Нужен App Password:\n"
        "1. Аккаунт Google → Безопасность\n"
        "2. Двухэтапная верификация → включить\n"
        "3. Пароли приложений → создать → скопировать 16 символов"
        if is_gmail else ""
    )
    await message.answer(
        f"📧 <b>Шаг 2 из 3 — Пароль</b>\n\nВведите пароль от почты:{hint}",
        parse_mode="HTML",
    )


@router.message(EmailSG.password)
async def email_got_password(message: Message, state: FSMContext) -> None:
    password = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(email_password=password)
    await state.set_state(EmailSG.senders)
    await message.answer(
        "📧 <b>Шаг 3 из 3 — Разрешённые отправители</b>\n\n"
        "Введите email-адреса через запятую, от которых принимать письма.\n"
        "Или напишите <b>все</b> чтобы принимать от любых отправителей.\n\n"
        "<i>Пример: client@mail.ru, booking@platform.com</i>",
        parse_mode="HTML",
    )


@router.message(EmailSG.senders)
async def email_got_senders(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    senders = "" if raw.lower() in ("все", "all", "*") else raw
    data = await state.get_data()
    await repo.save_email_settings(
        data["tenant_id"],
        email_address=data["email_address"],
        email_password=data["email_password"],
        email_allowed_senders=senders,
    )
    await state.clear()
    senders_display = senders or "все"
    await message.answer(
        f"✅ Email мониторинг настроен!\n\n"
        f"Адрес: <code>{data['email_address']}</code>\n"
        f"Отправители: {senders_display}\n\n"
        f"Бот начнёт проверять почту в течение минуты.",
        parse_mode="HTML",
    )


# ── Timezone settings ──────────────────────────────────────────────────────────

def _tz_kb(current_tz: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=("✅ " if tz == current_tz else "") + label,
            callback_data=f"adm:tz:{tz}",
        )]
        for label, tz in _TIMEZONES
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:timezone")
async def show_timezone_menu(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    current_tz = await repo.get_tenant_timezone(tenant.tenant_id)
    await callback.message.edit_text(
        "⏰ <b>Часовой пояс</b>\n\n"
        "Выберите часовой пояс вашего салона.\n"
        "Он используется для правильного отображения времени записей.",
        parse_mode="HTML",
        reply_markup=_tz_kb(current_tz),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:tz:"))
async def set_timezone(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not await _is_owner(callback.from_user.id, tenant):
        await callback.answer()
        return
    tz_name = callback.data[len("adm:tz:"):]
    await repo.save_tenant_timezone(tenant.tenant_id, tz_name)
    label = next((l for l, t in _TIMEZONES if t == tz_name), tz_name)
    await callback.answer(f"✅ Часовой пояс: {label}", show_alert=True)
    await callback.message.edit_text(
        "⏰ <b>Часовой пояс</b>\n\n"
        "Выберите часовой пояс вашего салона.\n"
        "Он используется для правильного отображения времени записей.",
        parse_mode="HTML",
        reply_markup=_tz_kb(tz_name),
    )
