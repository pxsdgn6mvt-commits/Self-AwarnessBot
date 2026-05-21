import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import date as _date, datetime, timezone
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, Response

from aria.utils.notify_admin import notify_admin as _notify_admin

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


@app.route("/health")
def health():
    return jsonify({"ok": True})


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
def healthz():
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


# ── Mini App API ──────────────────────────────────────────────────────────────
# Allowed origin for CORS. Set MINIAPP_ORIGIN in Railway Variables once the
# Cloudflare Pages URL is known. Default "*" is fine during development.
_MINIAPP_ORIGIN = os.getenv("MINIAPP_ORIGIN", "*")


def _tg_notify(bot_token: str, chat_id: int, text: str) -> None:
    """Fire-and-forget: send a Telegram message via Bot API using stdlib only."""
    import urllib.request as _ur
    import json as _j
    try:
        payload = _j.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = _ur.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        _ur.urlopen(req, timeout=5)
    except Exception as exc:
        log.warning("Owner TG notification failed: %s", exc)


@app.after_request
def _add_cors(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = _MINIAPP_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/services", methods=["OPTIONS"])
@app.route("/api/slots", methods=["OPTIONS"])
@app.route("/api/bookings", methods=["OPTIONS"])
@app.route("/api/my-bookings", methods=["OPTIONS"])
def _api_preflight():
    return jsonify({}), 204


def _run(coro):
    """Run an async coroutine from a Flask sync handler."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


async def _connect():
    import asyncpg  # available because aria/requirements.txt is installed
    dsn = os.getenv("DATABASE_URL") or os.getenv("ARIA_DATABASE_URL", "")
    return await asyncpg.connect(dsn)


def _verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram WebApp initData. Returns parsed user dict or None."""
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    check_hash = params.pop("hash", None)
    if not check_hash:
        return None
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, check_hash):
        return None
    return json.loads(params.get("user", "{}"))


# ── GET /api/services?tenant_id=X ─────────────────────────────────────────────

@app.route("/api/services")
def api_services():
    tenant_id = request.args.get("tenant_id", type=int)
    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    async def _fetch():
        conn = await _connect()
        try:
            tenant_row = await conn.fetchrow(
                "SELECT working_days FROM aria_tenants WHERE id=$1", tenant_id
            )
            rows = await conn.fetch(
                """
                SELECT sc.id AS cat_id, sc.name AS cat_name,
                       si.id, si.name, si.price, si.duration_minutes
                FROM aria_service_items si
                JOIN aria_service_categories sc ON si.category_id = sc.id
                WHERE sc.tenant_id = $1
                ORDER BY sc.position, sc.id, si.position, si.id
                """,
                tenant_id,
            )
        finally:
            await conn.close()
        cats: dict[int, dict] = {}
        for r in rows:
            cid = r["cat_id"]
            if cid not in cats:
                cats[cid] = {"id": cid, "name": r["cat_name"], "items": []}
            cats[cid]["items"].append({
                "id": r["id"],
                "name": r["name"],
                "price": float(r["price"]) if r["price"] is not None else None,
                "duration_minutes": r["duration_minutes"],
            })
        raw = (tenant_row["working_days"] if tenant_row else None) or "1,2,3,4,5,6"
        working_days = [int(d) for d in raw.split(",") if d.strip().isdigit()]
        return {"categories": list(cats.values()), "working_days": working_days}

    try:
        return jsonify(_run(_fetch()))
    except Exception as exc:
        log.exception("api_services error")
        return jsonify({"error": str(exc)}), 500


# ── GET /api/slots?tenant_id=X&date=YYYY-MM-DD ────────────────────────────────

@app.route("/api/slots")
def api_slots():
    tenant_id = request.args.get("tenant_id", type=int)
    date_str = request.args.get("date", "")
    if not tenant_id or not date_str:
        return jsonify({"error": "tenant_id and date required"}), 400
    try:
        target_date = _date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400

    async def _fetch():
        conn = await _connect()
        try:
            tenant_row = await conn.fetchrow(
                "SELECT * FROM aria_tenants WHERE id=$1", tenant_id
            )
            if not tenant_row:
                return None, None
            booked_rows = await conn.fetch(
                """
                SELECT scheduled_at FROM aria_bookings
                WHERE tenant_id=$1 AND scheduled_at::date=$2 AND status='confirmed'
                """,
                tenant_id, target_date,
            )
        finally:
            await conn.close()
        return tenant_row, {r["scheduled_at"] for r in booked_rows}

    try:
        tenant_row, booked = _run(_fetch())
    except Exception as exc:
        log.exception("api_slots error")
        return jsonify({"error": str(exc)}), 500

    if tenant_row is None:
        return jsonify({"error": "tenant not found"}), 404

    working_days = [int(d) for d in (tenant_row["working_days"] or "1,2,3,4,5,6").split(",")]
    if target_date.isoweekday() not in working_days:
        return jsonify([])

    tz = ZoneInfo(tenant_row["timezone"] or "UTC")
    open_h  = tenant_row["open_hour"]    or 10
    close_h = tenant_row["close_hour"]   or 20
    step    = tenant_row["slot_minutes"] or 60
    now_utc = datetime.now(timezone.utc)

    slots = []
    h, m = open_h, 0
    while h < close_h:
        slot_utc = datetime(target_date.year, target_date.month, target_date.day,
                            h, m, tzinfo=tz).astimezone(timezone.utc)
        if slot_utc > now_utc and slot_utc not in booked:
            slots.append(f"{h:02d}:{m:02d}")
        h, m = divmod(h * 60 + m + step, 60)

    return jsonify(slots)


# ── POST /api/bookings ────────────────────────────────────────────────────────
# Body: {tenant_id, initData, client_name, service, date, time}

@app.route("/api/bookings", methods=["POST"])
def api_create_booking():
    body = request.get_json(silent=True) or {}
    tenant_id   = body.get("tenant_id")
    init_data   = body.get("initData", "")
    client_name = (body.get("client_name") or "").strip()
    service     = (body.get("service") or "").strip()
    date_str    = body.get("date", "")
    time_str    = body.get("time", "")

    if not all([tenant_id, client_name, service, date_str, time_str]):
        return jsonify({"error": "tenant_id, client_name, service, date, time required"}), 400

    async def _get_tenant():
        conn = await _connect()
        try:
            return await conn.fetchrow("SELECT * FROM aria_tenants WHERE id=$1", tenant_id)
        finally:
            await conn.close()

    try:
        tenant_row = _run(_get_tenant())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if not tenant_row:
        return jsonify({"error": "tenant not found"}), 404

    tg_user = _verify_init_data(init_data, tenant_row["bot_token"])
    if tg_user is None:
        return jsonify({"error": "invalid initData"}), 403

    client_tg_id = tg_user.get("id")

    try:
        d = _date.fromisoformat(date_str)
        h, m = map(int, time_str.split(":"))
        tz = ZoneInfo(tenant_row["timezone"] or "UTC")
        dt_utc = datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(timezone.utc)
    except Exception:
        return jsonify({"error": "invalid date or time"}), 400

    if dt_utc <= datetime.now(timezone.utc):
        return jsonify({"error": "slot is in the past"}), 400

    async def _create():
        conn = await _connect()
        try:
            conflict = await conn.fetch(
                """
                SELECT id FROM aria_bookings
                WHERE tenant_id=$1 AND scheduled_at=$2 AND status='confirmed'
                """,
                tenant_id, dt_utc,
            )
            if conflict:
                return None, "slot already taken"
            row = await conn.fetchrow(
                """
                INSERT INTO aria_bookings
                    (tenant_id, user_id, client_name, service, scheduled_at, client_tg_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                tenant_id, client_tg_id or 0, client_name, service, dt_utc, client_tg_id,
            )
            return row["id"], None
        finally:
            await conn.close()

    try:
        booking_id, err = _run(_create())
    except Exception as exc:
        log.exception("api_create_booking error")
        _notify_admin("api_create_booking", exc)
        return jsonify({"error": str(exc)}), 500

    if err:
        return jsonify({"error": err}), 409

    owner_tg_id = tenant_row["owner_tg_id"]
    bot_token   = tenant_row["bot_token"]
    if owner_tg_id and bot_token:
        tz   = ZoneInfo(tenant_row["timezone"] or "UTC")
        local = dt_utc.astimezone(tz)
        _tg_notify(
            bot_token,
            owner_tg_id,
            f"📅 <b>Новая запись через Mini App</b>\n\n"
            f"Клиент: {client_name}\n"
            f"Услуга: {service}\n"
            f"Дата:   {local.strftime('%d.%m.%Y')} в {local.strftime('%H:%M')}\n"
            f"Запись: #{booking_id}",
        )

    return jsonify({"booking_id": booking_id, "confirmed": True}), 201


# ── GET /api/my-bookings?tenant_id=X&user_id=Y ───────────────────────────────

@app.route("/api/my-bookings")
def api_my_bookings():
    tenant_id = request.args.get("tenant_id", type=int)
    user_id   = request.args.get("user_id",   type=int)
    if not tenant_id or not user_id:
        return jsonify({"error": "tenant_id and user_id required"}), 400

    async def _fetch():
        conn = await _connect()
        try:
            tenant_row = await conn.fetchrow(
                "SELECT timezone FROM aria_tenants WHERE id=$1", tenant_id
            )
            tz_str = (tenant_row["timezone"] if tenant_row else None) or "UTC"
            rows = await conn.fetch(
                """
                SELECT id, client_name, service, scheduled_at, status, paid
                FROM aria_bookings
                WHERE tenant_id=$1 AND client_tg_id=$2
                  AND status IN ('confirmed', 'pending')
                ORDER BY scheduled_at ASC
                """,
                tenant_id, user_id,
            )
        finally:
            await conn.close()
        tz = ZoneInfo(tz_str)
        return [
            {
                "id": r["id"],
                "client_name": r["client_name"],
                "service": r["service"],
                "date": r["scheduled_at"].astimezone(tz).strftime("%Y-%m-%d"),
                "time": r["scheduled_at"].astimezone(tz).strftime("%H:%M"),
                "status": r["status"],
                "paid": r["paid"],
            }
            for r in rows
        ]

    try:
        return jsonify(_run(_fetch()))
    except Exception as exc:
        log.exception("api_my_bookings error")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    log.info("Starting on port %s", port)
    app.run(host="0.0.0.0", port=port)
