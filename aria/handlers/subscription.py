"""Telegram Payments — subscription management for bot owners."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import aria.db.repo as repo
from aria.config import settings
from aria.filters import SetupDone
from aria.tenant import TenantConfig

log = logging.getLogger(__name__)
router = Router()

_PLANS = {
    "starter": {"label": "Starter", "amount": 4900,  "desc": "24/7 бот бронирования · Напоминания · 1 локация"},
    "pro":     {"label": "Pro",     "amount": 8900,  "desc": "Starter + CRM · Аналитика · Маркетинг AI"},
    "agency":  {"label": "Agency",  "amount": 17900, "desc": "Pro + до 10 локаций · Персональная настройка · SLA"},
}


def _plan_selector_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Starter — €49/мес", callback_data="sub:plan:starter")],
        [InlineKeyboardButton(text="⭐ Pro — €89/мес",     callback_data="sub:plan:pro")],
        [InlineKeyboardButton(text="🏢 Agency — €179/мес", callback_data="sub:plan:agency")],
    ])


def _active_sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продлить",  callback_data="sub:renew")],
        [InlineKeyboardButton(text="❌ Отменить подписку", callback_data="sub:cancel_info")],
    ])


async def show_subscription_menu(message: Message, tenant: TenantConfig) -> None:
    sub = await repo.get_active_subscription(tenant.id)
    if sub:
        plan_name = sub["plan"].capitalize()
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
            "Оплати прямо в Telegram — безопасно через Stripe.\n\n"
            "🌱 <b>Starter</b> — €49/мес\n  24/7 бот · напоминания · 1 локация\n\n"
            "⭐ <b>Pro</b> — €89/мес\n  Starter + CRM · аналитика · маркетинг AI\n\n"
            "🏢 <b>Agency</b> — €179/мес\n  Pro + до 10 локаций · персональная настройка · SLA",
            reply_markup=_plan_selector_kb(),
            parse_mode="HTML",
        )


async def _send_invoice(message: Message, plan_key: str) -> None:
    plan = _PLANS.get(plan_key)
    if not plan:
        await message.answer("Неизвестный тариф.")
        return

    provider_token = settings.STRIPE_PROVIDER_TOKEN
    if not provider_token:
        await message.answer(
            "⚠️ Оплата временно недоступна. Обратитесь в поддержку.",
        )
        return

    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title=f"AIBeautyKit {plan['label']}",
        description=plan["desc"],
        payload=f"sub_{plan_key}",
        provider_token=provider_token,
        currency="EUR",
        prices=[LabeledPrice(label=f"AIBeautyKit {plan['label']}", amount=plan["amount"])],
        need_email=True,
        send_email_to_provider=True,
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
    await callback.answer()
    await _send_invoice(callback.message, plan_key)


@router.callback_query(F.data == "sub:renew", SetupDone())
async def cb_sub_renew(callback: CallbackQuery, tenant: TenantConfig) -> None:
    if not tenant.is_owner(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    sub = await repo.get_active_subscription(tenant.id)
    plan_key = sub["plan"] if sub else "pro"
    await callback.answer()
    await _send_invoice(callback.message, plan_key)


@router.callback_query(F.data == "sub:cancel_info", SetupDone())
async def cb_sub_cancel_info(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "Для отмены подписки свяжитесь с поддержкой.\n"
        "Подписка продолжит действовать до конца оплаченного периода."
    )


@router.pre_checkout_query()
async def handle_pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message, tenant: TenantConfig) -> None:
    payment = message.successful_payment
    payload   = payment.invoice_payload or ""
    plan      = payload.replace("sub_", "") if payload.startswith("sub_") else payload
    email     = ""
    if payment.order_info and payment.order_info.email:
        email = payment.order_info.email
    charge_id = payment.provider_payment_charge_id or ""

    if tenant is None:
        log.error("successful_payment: no tenant found for this bot")
        await message.answer("✅ Оплата принята. Свяжитесь с поддержкой для активации.")
        return

    from aria.services.onboarding import provision_bot
    try:
        await provision_bot(
            customer_email=email,
            plan=plan,
            stripe_subscription_id=charge_id,
            tenant_id=tenant.id,
        )
    except Exception:
        log.exception("provision_bot failed after Telegram payment")

    plan_label = _PLANS.get(plan, {}).get("label", plan.capitalize())
    await message.answer(
        f"✅ <b>Оплата прошла!</b>\n\n"
        f"Тариф: <b>{plan_label}</b>\n\n"
        "Подписка активирована. Бот готов к работе.",
        parse_mode="HTML",
    )
