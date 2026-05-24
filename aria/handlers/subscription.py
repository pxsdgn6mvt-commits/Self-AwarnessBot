"""Subscription menu — shows status and links to pricing page."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import aria.db.repo as repo
from aria.filters import SetupDone
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()

_PRICING_URL = "https://web-production-54417.up.railway.app/pricing"

_PLANS = {
    "starter": "Starter",
    "pro":     "Pro",
    "agency":  "Agency",
}


def _plan_selector_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Starter — €49/мес", callback_data="sub:plan:starter")],
        [InlineKeyboardButton(text="⭐ Pro — €89/мес",     callback_data="sub:plan:pro")],
        [InlineKeyboardButton(text="🏢 Agency — €179/мес", callback_data="sub:plan:agency")],
    ])


def _active_sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продлить",          callback_data="sub:renew")],
        [InlineKeyboardButton(text="❌ Отменить подписку", callback_data="sub:cancel_info")],
    ])


def _pay_link_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить на сайте", url=_PRICING_URL)],
    ])


async def show_subscription_menu(message: Message, tenant: TenantConfig) -> None:
    sub = await repo.get_active_subscription(tenant.id)
    if sub:
        plan_name = _PLANS.get(sub["plan"], sub["plan"].capitalize())
        since = sub["created_at"].strftime("%-d %b %Y")
        await message.answer(
            f"💳 <b>Подписка</b>\n\n"
            f"Тариф: <b>{plan_name}</b>\n"
            f"Статус: ✅ Активна\n"
            f"С: {since}",
            reply_markup=_active_sub_kb(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "💳 <b>Подписка AIBeautyKit</b>\n\n"
            "🌱 <b>Starter</b> — €49/мес\n  24/7 бот · напоминания · 1 локация\n\n"
            "⭐ <b>Pro</b> — €89/мес\n  Starter + CRM · аналитика · маркетинг AI\n\n"
            "🏢 <b>Agency</b> — €179/мес\n  Pro + до 10 локаций · персональная настройка · SLA\n\n"
            "Выбери тариф ниже — откроем страницу оплаты:",
            reply_markup=_plan_selector_kb(),
            parse_mode="HTML",
        )


@router.message(F.text == "💳 Подписка", SetupDone())
async def btn_subscribe(message: Message, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return
    await show_subscription_menu(message, tenant)


@router.message(Command("subscribe"), SetupDone())
async def cmd_subscribe(message: Message, tenant: TenantConfig) -> None:
    if not tenant.is_owner(message.from_user.id):
        return
    await show_subscription_menu(message, tenant)


@router.callback_query(F.data.startswith("sub:plan:"), SetupDone())
async def cb_select_plan(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    plan_key = callback.data[len("sub:plan:"):]
    plan_label = _PLANS.get(plan_key, plan_key.capitalize())
    await callback.answer()
    await callback.message.answer(
        f"Оплата тарифа <b>{plan_label}</b> — перейди на сайт и завершите оформление:",
        reply_markup=_pay_link_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "sub:renew", SetupDone())
async def cb_sub_renew(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "Для продления перейди на страницу тарифов:",
        reply_markup=_pay_link_kb(),
    )


@router.callback_query(F.data == "sub:cancel_info", SetupDone())
async def cb_sub_cancel_info(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "Для отмены подписки свяжитесь с поддержкой.\n"
        "Подписка продолжит действовать до конца оплаченного периода."
    )
