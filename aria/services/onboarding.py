"""Auto-onboarding after successful Stripe payment (Sprint 013 v1).

v1 behaviour: creates aria_subscriptions row, notifies admin via Telegram.
Full bot-token pool provisioning is Sprint 013 v2.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import requests

from aria.config import settings
from aria.db import repo

log = logging.getLogger(__name__)


def _send_telegram(chat_id: int, text: str) -> None:
    bot_token = settings.MANAGEMENT_BOT_TOKEN or settings.BOT_TOKEN
    if not bot_token:
        log.warning("No bot token configured — cannot send Telegram notification")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        resp.raise_for_status()
    except Exception:
        log.exception("Failed to send Telegram admin notification")


async def provision_bot(
    customer_email: str,
    plan: str,
    stripe_subscription_id: str,
    stripe_customer_id: str = "",
    stripe_price_id: str = "",
    tenant_id: Optional[int] = None,
) -> int:
    sub_id = await repo.create_subscription(
        plan=plan,
        customer_email=customer_email,
        stripe_subscription_id=stripe_subscription_id or None,
        stripe_customer_id=stripe_customer_id or None,
        stripe_price_id=stripe_price_id or None,
        tenant_id=tenant_id,
    )
    log.info("Created subscription id=%s plan=%s email=%s tenant_id=%s", sub_id, plan, customer_email, tenant_id)

    admin_id = settings.ADMIN_TELEGRAM_ID
    if admin_id:
        source = f"Telegram Payment (tenant #{tenant_id})" if tenant_id else f"Stripe sub: {stripe_subscription_id}"
        msg = (
            f"Новый клиент: {customer_email or '—'} / {plan}\n"
            f"{source}\n"
            "Добавь бот токен через /add_bot"
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_telegram, admin_id, msg)

    return sub_id
