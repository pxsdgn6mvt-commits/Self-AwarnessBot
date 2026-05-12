import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes

import database as db
from config import PLAN_ONETIME, PLAN_PREMIUM, PRICE_ONETIME, PRICE_PREMIUM, OWNER_ID
from locales import t

logger = logging.getLogger(__name__)

# ─── Инвойсы ──────────────────────────────────────────────────────────────────

async def send_onetime_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="Vault Bot Lifetime" if lang == "en" else "Vault Bot Lifetime доступ",
        description=(
            "Unlimited entries, all 8 categories. Forever."
            if lang == "en"
            else "Безлимитные записи, все 8 категорий. Навсегда."
        ),
        payload="onetime_purchase",
        currency="XTR",
        prices=[LabeledPrice("Lifetime Access", PRICE_ONETIME)],
    )


async def send_premium_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="Vault Bot Premium",
        description=(
            "All features + auto-backup every Sunday."
            if lang == "en"
            else "Все функции + автобэкап каждое воскресенье."
        ),
        payload="premium_subscription",
        currency="XTR",
        prices=[LabeledPrice("Premium / month", PRICE_PREMIUM)],
    )


# ─── Pre-checkout ──────────────────────────────────────────────────────────────

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


# ─── Успешный платёж ──────────────────────────────────────────────────────────

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    stars = payment.total_amount

    user = await db.get_user(user_id)
    lang = user["lang"] if user else "en"

    if payload == "onetime_purchase":
        await db.set_plan(user_id, PLAN_ONETIME, expires=None)
        await db.add_payment(user_id, "onetime", stars)
        await update.message.reply_text(
            t(lang, "payment_success_onetime"), parse_mode="Markdown"
        )
        # Реферальная награда
        await _handle_referral_reward(user_id, context)

    elif payload == "premium_subscription":
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        await db.set_plan(user_id, PLAN_PREMIUM, expires=expires)
        await db.add_payment(user_id, "premium", stars)
        await update.message.reply_text(
            t(lang, "payment_success_premium"), parse_mode="Markdown"
        )

    logger.info(f"Payment: user={user_id} payload={payload} stars={stars}")


# ─── Реферальные награды ─────────────────────────────────────────────────────

async def _handle_referral_reward(referred_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Начисляет рефереру +30 дней Premium после покупки Lifetime другом."""
    ref = await db.get_unrewarded_referral(referred_id)
    if not ref:
        return

    referrer_id = ref["referrer_id"]
    referrer = await db.get_user(referrer_id)
    if not referrer:
        return

    # +30 дней Premium рефереру
    now = datetime.now(timezone.utc)
    current_plan = referrer["plan"]
    current_expires = referrer["plan_expires"]

    if current_plan == PLAN_PREMIUM and current_expires and current_expires > now:
        new_expires = current_expires + timedelta(days=30)
    else:
        new_expires = now + timedelta(days=30)

    await db.set_plan(referrer_id, PLAN_PREMIUM, expires=new_expires)
    await db.mark_referral_rewarded(referred_id)

    lang = referrer["lang"]
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            text=(
                "🎉 Твой реферал купил Lifetime! +30 дней Premium начислено."
                if lang == "ru"
                else "🎉 Your referral bought Lifetime! +30 Premium days added."
            ),
        )
        # Уведомляем владельца о выплате 10%
        stars_reward = int(PRICE_ONETIME * 0.10)
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"💸 Referral reward: send {stars_reward}⭐ to user {referrer_id}",
        )
    except Exception as e:
        logger.warning(f"Referral notification failed: {e}")


# ─── Проверка активности Premium ─────────────────────────────────────────────

def is_plan_active(user: dict) -> bool:
    """True если план активен (onetime — всегда, premium — до expires)."""
    plan = user.get("plan", "free")
    if plan == "free":
        return False
    if plan == PLAN_ONETIME:
        return True
    expires = user.get("plan_expires")
    if expires is None:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)
