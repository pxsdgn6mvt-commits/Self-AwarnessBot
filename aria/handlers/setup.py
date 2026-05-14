"""
Setup wizard — runs when a new tenant bot starts for the first time.
Guides the salon owner through configuring their bot via Telegram.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import json as _json

import aria.db.repo as repo
from aria.filters import SetupRequired
from aria.middleware import TenantMiddleware
from aria.services.booking import invalidate_adapter
from aria.tenant import TenantConfig


def _platform_gcal_email() -> str | None:
    from aria.config import settings
    creds = settings.GOOGLE_CALENDAR_CREDENTIALS
    if not creds:
        return None
    try:
        return _json.loads(creds).get("client_email")
    except Exception:
        return None

log = logging.getLogger(__name__)
router = Router()


class Setup(StatesGroup):
    salon_name   = State()
    owner_name   = State()
    services     = State()
    hours        = State()
    google_cal   = State()


@router.message(Command("ping"))
async def cmd_ping(message: Message, **kwargs) -> None:
    tenant = kwargs.get("tenant")
    if tenant:
        info = f"Tenant #{tenant.id} ({tenant.salon_name}), setup_complete={tenant.setup_complete}"
    else:
        info = "tenant NOT found in data"
    await message.answer(f"pong\n{info}")


@router.message(CommandStart(), SetupRequired())
async def setup_start(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    log.info("setup_start called for tenant #%d user %d", tenant.id, message.from_user.id)
    # First person to /start becomes the owner
    await repo.update_tenant(tenant.id, owner_tg_id=message.from_user.id)

    await state.set_state(Setup.salon_name)
    await message.answer(
        "Привет! Я Aria — твой AI ресепшн. Давай настроим бота.\n\n"
        "Шаг 1/4 — Как называется твой салон?"
    )


@router.message(Setup.salon_name)
async def setup_salon_name(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.update_data(salon_name=message.text.strip())
    await state.set_state(Setup.owner_name)
    await message.answer("Шаг 2/4 — Как тебя зовут? (имя владельца)")


@router.message(Setup.owner_name)
async def setup_owner_name(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.update_data(owner_name=message.text.strip())
    await state.set_state(Setup.services)
    await message.answer(
        "Шаг 3/4 — Какие услуги предлагаешь?\n"
        "Напиши через запятую, например:\n"
        "Наращивание ресниц, Маникюр, Стрижка"
    )


@router.message(Setup.services)
async def setup_services(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.update_data(services=message.text.strip())
    await state.set_state(Setup.hours)
    await message.answer(
        "Шаг 4/4 — Рабочие часы?\n"
        "Например: Пн-Сб 10:00-20:00"
    )


@router.message(Setup.hours)
async def setup_hours(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    await state.update_data(hours=message.text.strip())
    await state.set_state(Setup.google_cal)

    svc_email = _platform_gcal_email()
    if svc_email:
        await message.answer(
            "Почти готово! Подключим Google Calendar?\n\n"
            "Бот будет видеть и создавать записи прямо в твоём календаре.\n\n"
            "<b>3 шага:</b>\n\n"
            "1️⃣ Открой <b>calendar.google.com</b> → ⚙️ Настройки\n"
            "   → выбери нужный календарь слева\n\n"
            "2️⃣ Раздел <b>«Доступ другим людям»</b> → «Добавить людей»\n"
            f"   Введи этот email:\n<code>{svc_email}</code>\n"
            "   Права: <b>«Вносить изменения в мероприятия»</b> → Отправить\n\n"
            "3️⃣ На той же странице найди <b>«Идентификатор календаря»</b>\n"
            "   (выглядит как <code>xxx@group.calendar.google.com</code>\n"
            "   или просто твой Gmail-адрес)\n"
            "   Скопируй и пришли его сюда.\n\n"
            "Или напиши <b>пропустить</b> — расписание будет только в боте."
        )
    else:
        await message.answer(
            "Почти готово!\n\n"
            "Google Calendar сейчас не подключён к платформе.\n"
            "Напиши <b>пропустить</b> — расписание будет храниться в боте."
        )


@router.message(Setup.google_cal)
async def setup_google_cal(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    text = message.text.strip()

    google_cal_id = None if text.lower() in ("пропустить", "skip", "-", "нет", "no") else text

    await repo.update_tenant(
        tenant.id,
        salon_name=data["salon_name"],
        owner_name=data["owner_name"],
        services=data["services"],
        hours=data["hours"],
        google_cal_id=google_cal_id,
        setup_complete=True,
    )
    invalidate_adapter(tenant.id)
    TenantMiddleware.invalidate(tenant.bot_token)
    await state.clear()

    gcal_note = (
        "\n\n⚠️ Не забудь добавить сервисный аккаунт Google в настройки календаря (роль: Редактор)."
        if google_cal_id else ""
    )

    await message.answer(
        f"✅ Готово! Бот настроен для <b>{data['salon_name']}</b>.\n\n"
        f"Теперь просто пиши мне как обычно:\n"
        f"• «что у меня сегодня?»\n"
        f"• «запиши Катю на {data['services'].split(',')[0].strip()} 20 мая в 14:00»\n"
        f"• «что на этой неделе?»"
        f"{gcal_note}"
    )
    log.info("Tenant %d setup complete: %s", tenant.id, data["salon_name"])
