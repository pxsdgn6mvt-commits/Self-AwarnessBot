"""Stripe Checkout and webhook handling."""

from __future__ import annotations

import logging
from typing import Any

import stripe

from aria.config import settings

log = logging.getLogger(__name__)

_PLAN_BY_PRICE: dict[str, str] = {}


def _get_plan_map() -> dict[str, str]:
    if not _PLAN_BY_PRICE:
        _PLAN_BY_PRICE.update({
            settings.STRIPE_PRICE_ID_STARTER: "starter",
            settings.STRIPE_PRICE_ID_PRO:     "pro",
            settings.STRIPE_PRICE_ID_AGENCY:  "agency",
        })
    return _PLAN_BY_PRICE


def create_checkout_session(price_id: str, success_url: str, cancel_url: str) -> str:
    stripe.api_key = settings.STRIPE_SECRET_KEY
    plan_map = _get_plan_map()
    plan = plan_map.get(price_id, "unknown")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"plan": plan},
    )
    return session.url


def parse_webhook_event(payload: bytes, sig_header: str) -> Any:
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
