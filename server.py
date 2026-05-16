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


@app.route("/gcal/callback")
def gcal_callback():
    code      = request.args.get("code")
    state_val = request.args.get("state")
    error     = request.args.get("error")

    if error:
        return f"<h1>Ошибка авторизации: {error}</h1>", 400
    if not code or not state_val:
        return "<h1>Ошибка: не получен код авторизации.</h1>", 400

    try:
        tenant_id = int(state_val)
    except ValueError:
        return "<h1>Неверный параметр state.</h1>", 400

    import requests as req

    client_id     = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    public_url    = os.getenv("ARIA_PUBLIC_URL", "").rstrip("/")
    redirect_uri  = f"{public_url}/gcal/callback"

    resp = req.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "code":          code,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        },
        timeout=10,
    )
    if not resp.ok:
        log.error("GCal token exchange: %s %s", resp.status_code, resp.text)
        return f"<h1>Ошибка обмена токена ({resp.status_code})</h1>", 500

    token_data    = resp.json()
    access_token  = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in    = token_data.get("expires_in", 3600)

    if not refresh_token:
        return (
            "<h1>Ошибка: Google не вернул refresh_token.</h1>"
            "<p>Попробуйте снова — нажмите «Переподключить» в боте.</p>"
        ), 400

    import asyncio
    import asyncpg
    from datetime import datetime, timedelta, timezone

    async def _save() -> int | None:
        db_url = os.getenv("ARIA_DATABASE_URL", "")
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=1)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE aria_tenant_settings
                    SET gcal_access_token=$2, gcal_refresh_token=$3,
                        gcal_token_expiry=$4
                    WHERE tenant_id=$1
                    """,
                    tenant_id, access_token, refresh_token, expiry,
                )
                row = await conn.fetchrow(
                    "SELECT owner_telegram_id FROM aria_tenant_settings"
                    " WHERE tenant_id=$1",
                    tenant_id,
                )
            return row["owner_telegram_id"] if row else None
        finally:
            await pool.close()

    try:
        owner_id = asyncio.run(_save())
    except Exception:
        log.exception("Failed to save GCal tokens for tenant %d", tenant_id)
        return "<h1>Ошибка сохранения токенов.</h1>", 500

    if owner_id:
        bot_token = (
            os.getenv(f"ARIA_BOT_{tenant_id}_TOKEN")
            or os.getenv("ARIA_BOT_TOKEN", "")
        )
        if bot_token:
            try:
                req.get(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    params={
                        "chat_id":    owner_id,
                        "text": (
                            "✅ <b>Google Calendar подключён!</b>\n\n"
                            "Теперь при создании записи событие автоматически "
                            "добавляется в ваш Google Calendar."
                        ),
                        "parse_mode": "HTML",
                    },
                    timeout=5,
                )
            except Exception:
                pass

    return (
        "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
        "<h1>✅ Google Calendar подключён!</h1>"
        "<p>Можете закрыть это окно и вернуться в бот.</p>"
        "</body></html>"
    )


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
