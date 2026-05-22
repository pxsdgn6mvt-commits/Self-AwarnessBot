import os
import logging
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from flask import Flask, request, jsonify, Response, redirect

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


def _get_db_conn():
    import psycopg2
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _init_db():
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS waitlist_entries (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                country TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        log.info("DB init: waitlist_entries table ready")
    except Exception:
        log.exception("DB init failed — DATABASE_URL may not be set")


_init_db()


def _send_admin_email(name: str, email: str, country: str):
    admin_email = os.getenv("ADMIN_EMAIL")
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not all([admin_email, smtp_host, smtp_user, smtp_pass]):
        log.warning("SMTP not configured — skipping waitlist notification email")
        return

    body = f"Name: {name}\nEmail: {email}\nCountry: {country}\nTime: {datetime.utcnow()}"
    msg = MIMEText(body)
    msg["Subject"] = "New waitlist signup — AIBeautyKit"
    msg["From"] = smtp_user
    msg["To"] = admin_email

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, admin_email, msg.as_string())


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


@app.route("/waitlist")
def waitlist():
    return _read_html("waitlist.html")


@app.route("/waitlist/thanks")
def waitlist_thanks():
    return _read_html("waitlist-thanks.html")


@app.route("/guides/<path:filename>")
def guides(filename):
    return _read_html(f"guides/{filename}")


@app.route("/api/waitlist", methods=["POST"])
def api_waitlist():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    country = (request.form.get("country") or "").strip()

    if not name or not email or not country:
        return "Missing required fields: name, email, country", 400

    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO waitlist_entries (name, email, country) VALUES (%s, %s, %s)",
            (name, email, country),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        log.exception("Failed to insert waitlist entry")
        return "Database error", 500

    try:
        _send_admin_email(name, email, country)
    except Exception:
        log.exception("Failed to send waitlist notification email")

    return redirect("/waitlist/thanks")


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
