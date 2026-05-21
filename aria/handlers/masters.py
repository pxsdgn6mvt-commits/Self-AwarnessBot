"""Masters admin UI handlers for the owner-bot Settings panel."""

from __future__ import annotations

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
from aria.filters import SetupDone
from aria.handlers.quick import MAIN_KB_TEXTS
from aria.tenant import TenantConfig

router = Router()


class AddMasterFSM(StatesGroup):
    name  = State()
    phone = State()


class SetMasterBotFSM(StatesGroup):
    waiting_token = State()


def _masters_text_and_kb(masters: list) -> tuple[str, InlineKeyboardMarkup]:
    if not masters:
        text = "👥 <b>Мастера</b>\n\nСписок пуст."
    else:
        lines = ["👥 <b>Мастера</b>\n"]
        for m in masters:
            crown = " 👑" if m["is_owner"] else ""
            status = "✅" if m["is_active"] else "❌"
            phone_str = f" · {m['phone']}" if m.get("phone") else ""
            lines.append(f"{status} <b>{m['name']}</b>{crown}{phone_str}")
        text = "\n".join(lines)

    rows = []
    for m in masters:
        rows.append([InlineKeyboardButton(
            text=f"📅 Расписание {m['name']}",
            callback_data=f"cfg:avail:{m['id']}",
        )])
        if m["is_active"] and not m["is_owner"]:
            rows.append([InlineKeyboardButton(
                text=f"🚫 Деактивировать {m['name']}",
                callback_data=f"cfg:master_off:{m['id']}",
            )])
            rows.append([InlineKeyboardButton(
                text=f"🤖 Выдать бот {m['name']}",
                callback_data=f"cfg:master_token:{m['id']}",
            )])
        elif not m["is_active"]:
            rows.append([InlineKeyboardButton(
                text=f"✅ Реактивировать {m['name']}",
                callback_data=f"cfg:master_on:{m['id']}",
            )])

    rows.append([InlineKeyboardButton(text="➕ Добавить мастера", callback_data="cfg:master_add")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:settings")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "cfg:masters", SetupDone())
async def cb_masters_list(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    masters = await repo.get_masters(tenant.id, active_only=False)
    text, kb = _masters_text_and_kb(masters)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# Registered before cfg:master_off: to win the startswith match for cfg:master_off_yes:
@router.callback_query(F.data.startswith("cfg:master_off_yes:"), SetupDone())
async def cb_master_deactivate_confirmed(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    master = await repo.get_master_by_id(master_id)
    if not master or master["tenant_id"] != tenant.id:
        await callback.answer("Мастер не найден.", show_alert=True)
        return
    if master["is_owner"]:
        await callback.answer("Нельзя деактивировать владельца.", show_alert=True)
        return
    await repo.set_master_active(master_id, False)
    masters = await repo.get_masters(tenant.id, active_only=False)
    text, kb = _masters_text_and_kb(masters)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Мастер деактивирован.")


@router.callback_query(F.data.startswith("cfg:master_off:"), SetupDone())
async def cb_master_deactivate(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    master = await repo.get_master_by_id(master_id)
    if not master or master["tenant_id"] != tenant.id:
        await callback.answer("Мастер не найден.", show_alert=True)
        return
    if master["is_owner"]:
        await callback.answer("Нельзя деактивировать владельца.", show_alert=True)
        return
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Да, деактивировать",
            callback_data=f"cfg:master_off_yes:{master_id}",
        )],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="cfg:masters")],
    ])
    await callback.message.edit_text(
        f"Деактивировать мастера <b>{master['name']}</b>?\n\nОн будет скрыт из расписания.",
        reply_markup=confirm_kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cfg:master_on:"), SetupDone())
async def cb_master_activate(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    master = await repo.get_master_by_id(master_id)
    if not master or master["tenant_id"] != tenant.id:
        await callback.answer("Мастер не найден.", show_alert=True)
        return
    await repo.set_master_active(master_id, True)
    masters = await repo.get_masters(tenant.id, active_only=False)
    text, kb = _masters_text_and_kb(masters)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Мастер реактивирован.")


@router.callback_query(F.data == "cfg:master_add", SetupDone())
async def cb_master_add(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(AddMasterFSM.name)
    await state.update_data(tenant_id=tenant.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "👤 <b>Добавление мастера</b>\n\nВведи имя мастера:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(
    AddMasterFSM.name,
    F.text,
    ~F.text.in_(MAIN_KB_TEXTS),
    F.text.func(lambda x: not x.startswith("/")),
)
async def fsm_master_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    await state.update_data(master_name=name)
    await state.set_state(AddMasterFSM.phone)
    await message.answer(
        f"✅ Имя: <b>{name}</b>\n\nВведи номер телефона\n(или /skip чтобы пропустить):",
        parse_mode="HTML",
    )


@router.message(AddMasterFSM.phone, Command("skip"))
async def fsm_master_phone_skip(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await repo.create_master(data["tenant_id"], data["master_name"])
    await state.clear()
    masters = await repo.get_masters(data["tenant_id"], active_only=False)
    text, kb = _masters_text_and_kb(masters)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(
    AddMasterFSM.phone,
    F.text,
    ~F.text.in_(MAIN_KB_TEXTS),
    F.text.func(lambda x: not x.startswith("/")),
)
async def fsm_master_phone(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    phone = message.text.strip()
    await repo.create_master(data["tenant_id"], data["master_name"], phone=phone)
    await state.clear()
    masters = await repo.get_masters(data["tenant_id"], active_only=False)
    text, kb = _masters_text_and_kb(masters)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ── Assign bot token to master ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cfg:master_token:"), SetupDone())
async def cb_master_token(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    master_id = int(callback.data.split(":")[-1])
    master = await repo.get_master_by_id(master_id)
    if not master or master["tenant_id"] != tenant.id:
        await callback.answer("Мастер не найден.", show_alert=True)
        return
    await state.set_state(SetMasterBotFSM.waiting_token)
    await state.update_data(master_id=master_id, tenant_id=tenant.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"🤖 <b>Бот для мастера {master['name']}</b>\n\n"
        "Создайте бота через @BotFather и введите полученный токен:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SetMasterBotFSM.waiting_token, F.text)
async def fsm_master_bot_token(message: Message, state: FSMContext) -> None:
    from aiogram import Bot as _Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    token = message.text.strip()
    data = await state.get_data()

    temp_bot = _Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        bot_info = await temp_bot.get_me()
        await temp_bot.session.close()
    except Exception:
        await temp_bot.session.close()
        await message.answer(
            "❌ Токен не валиден или бот недоступен. Проверьте токен и попробуйте снова:"
        )
        return

    await repo.set_master_bot_token(data["master_id"], token)
    await state.clear()
    master = await repo.get_master_by_id(data["master_id"])
    masters = await repo.get_masters(data["tenant_id"], active_only=False)
    text, kb = _masters_text_and_kb(masters)
    await message.answer(
        f"✅ Бот <b>@{bot_info.username}</b> привязан к мастеру <b>{master['name']}</b>.\n"
        "Мастер-бот запустится в течение 30 секунд.",
        parse_mode="HTML",
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")
