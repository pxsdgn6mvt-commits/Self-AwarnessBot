import os
import logging
import threading
from datetime import datetime, timezone
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


def _db_connect():
    import psycopg2
    db_url = os.getenv("ARIA_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    return conn


def _gcal_sync_thread(booking_id, tenant_id, credentials_json, calendar_id, booking):
    try:
        from aria.services.gcal import _insert_event_sync
        event_id = _insert_event_sync(credentials_json, calendar_id, booking)
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE aria_bookings SET gcal_event_id=%s WHERE id=%s",
            (event_id, booking_id),
        )
        cur.close()
        conn.close()
        log.info("Tenant %d: GCal event %s for booking %d", tenant_id, event_id, booking_id)
    except Exception as exc:
        log.warning(
            "Tenant %d: GCal sync failed for booking %d: %s", tenant_id, booking_id, exc
        )


@app.route("/api/booking", methods=["POST"])
def booking():
    from aria.utils.telegram_auth import verify_telegram_webapp

    bot_token = os.getenv("ARIA_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    if not verify_telegram_webapp(init_data, bot_token):
        return jsonify({"error": "unauthorized"}), 403

    data = request.get_json(silent=True) or {}

    tenant_id_raw = data.get("tenant_id")
    client_name = str(data.get("client_name") or "").strip()
    service = str(data.get("service") or "").strip()
    scheduled_at_raw = data.get("scheduled_at")

    if not tenant_id_raw or not client_name or not service or not scheduled_at_raw:
        return jsonify({"error": "tenant_id, client_name, service, scheduled_at are required"}), 400

    try:
        tenant_id = int(tenant_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "tenant_id must be an integer"}), 400

    try:
        scheduled_at = datetime.fromisoformat(str(scheduled_at_raw))
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid scheduled_at, use ISO 8601"}), 400

    phone = str(data.get("phone") or "").strip()
    duration_minutes = int(data.get("duration_minutes") or 60)

    try:
        conn = _db_connect()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, google_cal_credentials, google_cal_id, timezone FROM aria_tenants WHERE id=%s",
            (tenant_id,),
        )
        tenant_row = cur.fetchone()
        if tenant_row is None:
            cur.close()
            conn.close()
            return jsonify({"error": "tenant not found"}), 404

        _, credentials_json, calendar_id, tenant_tz = tenant_row
        tenant_tz = tenant_tz or "UTC"

        cur.execute(
            """
            INSERT INTO aria_bookings
                (tenant_id, user_id, client_name, service, scheduled_at, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (tenant_id, 0, client_name, service, scheduled_at, "miniapp"),
        )
        booking_id = cur.fetchone()[0]

        if phone:
            cur.execute(
                "UPDATE aria_bookings SET notes=%s WHERE id=%s",
                (f"Телефон: {phone}", booking_id),
            )

        cur.close()
        conn.close()
    except Exception as exc:
        log.exception("DB error in POST /api/booking")
        return jsonify({"error": "database error"}), 500

    if credentials_json and calendar_id:
        t = threading.Thread(
            target=_gcal_sync_thread,
            args=(booking_id, tenant_id, credentials_json, calendar_id, {
                "client_name": client_name,
                "phone": phone,
                "service": service,
                "scheduled_at": scheduled_at,
                "duration_minutes": duration_minutes,
                "timezone": tenant_tz,
            }),
            daemon=True,
        )
        t.start()

    return jsonify({"ok": True, "booking_id": booking_id}), 201


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    log.info("Starting on port %s", port)
    app.run(host="0.0.0.0", port=port)
