import asyncio
import os
import logging
from flask import Flask, request, jsonify, Response

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

SALES_SYSTEM_PROMPT = (
    "You are an AIBeautyKit sales assistant. "
    "You help beauty salon owners understand how AIBeautyKit's 6 AI specialists "
    "can save them time. "
    "You speak Russian, Finnish, English, German — match the language the user writes in. "
    "Be concise and friendly. "
    "Always guide the conversation toward the free audit (#audit on the page) "
    "or one of the pricing plans (Starter €49, Pro €89, Agency €149). "
    "Never make up specific numbers or statistics."
)


def _read_html(filename):
    path = os.path.join(BASE_DIR, filename)
    with open(path, "rb") as f:
        return Response(f.read(), mimetype="text/html; charset=utf-8")


@app.route("/")
def index():
    return _read_html("index.html")


@app.route("/thank-you")
@app.route("/thank-you.html")
def thank_you():
    return _read_html("thank-you.html")


@app.route("/how-it-works")
def how_it_works():
    return _read_html("how-it-works.html")


@app.route("/faq")
def faq():
    return _read_html("faq.html")


@app.route("/healthz")
def health():
    return "ok", 200


@app.route("/pricing")
def pricing():
    from aria.config import settings
    path = os.path.join(BASE_DIR, "pricing.html")
    with open(path, "rb") as f:
        html = f.read().decode("utf-8")
    html = html.replace("__STRIPE_PRICE_ID_STARTER__", settings.STRIPE_PRICE_ID_STARTER)
    html = html.replace("__STRIPE_PRICE_ID_PRO__",     settings.STRIPE_PRICE_ID_PRO)
    html = html.replace("__STRIPE_PRICE_ID_AGENCY__",  settings.STRIPE_PRICE_ID_AGENCY)
    return Response(html.encode("utf-8"), mimetype="text/html; charset=utf-8")


@app.route("/pricing/success")
def pricing_success():
    return _read_html("pricing_success.html")


@app.route("/pricing/cancel")
def pricing_cancel():
    return _read_html("pricing_cancel.html")


@app.route("/api/stripe/checkout", methods=["POST"])
def stripe_checkout():
    from aria.services.stripe_service import create_checkout_session
    from aria.config import settings

    data = request.get_json(silent=True) or {}
    price_id = data.get("price_id", "")
    if not price_id:
        return jsonify({"error": "price_id required"}), 400

    valid_ids = {
        settings.STRIPE_PRICE_ID_STARTER,
        settings.STRIPE_PRICE_ID_PRO,
        settings.STRIPE_PRICE_ID_AGENCY,
    }
    if price_id not in valid_ids:
        return jsonify({"error": "invalid price_id"}), 400

    base = request.host_url.rstrip("/")
    try:
        url = create_checkout_session(
            price_id,
            success_url=f"{base}/pricing/success",
            cancel_url=f"{base}/pricing/cancel",
        )
        return jsonify({"url": url})
    except Exception as exc:
        log.exception("Stripe checkout error")
        return jsonify({"error": str(exc)}), 502


@app.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    from aria.services.stripe_service import parse_webhook_event
    from aria.services.onboarding import provision_bot
    import stripe

    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")

    _SigError = getattr(stripe, "SignatureVerificationError",
                        getattr(stripe.error, "SignatureVerificationError", Exception))
    try:
        event = parse_webhook_event(payload, sig)
    except _SigError:
        log.warning("Stripe webhook signature verification failed")
        return jsonify({"error": "invalid signature"}), 400
    except Exception as exc:
        log.exception("Stripe webhook parse error")
        return jsonify({"error": str(exc)}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email    = session.get("customer_details", {}).get("email") or session.get("customer_email", "")
        stripe_sub_id     = session.get("subscription", "")
        stripe_customer   = session.get("customer", "")
        metadata          = session.get("metadata", {})
        plan              = metadata.get("plan", "unknown")
        line_items_data   = session.get("line_items")
        stripe_price_id   = ""
        if line_items_data and line_items_data.get("data"):
            stripe_price_id = line_items_data["data"][0].get("price", {}).get("id", "")

        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                provision_bot(
                    customer_email=customer_email,
                    plan=plan,
                    stripe_subscription_id=stripe_sub_id,
                    stripe_customer_id=stripe_customer,
                    stripe_price_id=stripe_price_id,
                )
            )
            loop.close()
        except Exception:
            log.exception("Onboarding provision_bot failed")

    return jsonify({"status": "ok"}), 200


@app.route("/api/chat", methods=["POST"])
def chat():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY is not set")
        return jsonify({"error": "API key not configured"}), 500

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])

    if not isinstance(messages, list) or len(messages) == 0:
        return jsonify({"error": "messages must be a non-empty list"}), 400

    messages = messages[-20:]

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=SALES_SYSTEM_PROMPT,
            messages=messages,
        )
        return jsonify({"content": response.content[0].text})
    except Exception as exc:
        log.exception("Anthropic API error")
        return jsonify({"error": str(exc)}), 502


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    log.info("Starting on port %s", port)
    app.run(host="0.0.0.0", port=port)
