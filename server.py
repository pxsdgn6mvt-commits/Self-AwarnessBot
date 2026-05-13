"""
Flask web server for AIBeautyKit landing page.
Serves static HTML files and provides the /api/chat endpoint
that proxies requests to the Claude API for the chat widget.

Environment variables required:
  PORT              — HTTP port (Railway sets this automatically)
  ANTHROPIC_API_KEY — Your Anthropic API key
"""

import os
import logging
from flask import Flask, request, jsonify, send_from_directory

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder=".")

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


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/thank-you")
@app.route("/thank-you.html")
def thank_you():
    return send_from_directory(".", "thank-you.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY is not set")
        return jsonify({"error": "API key not configured"}), 500

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])

    # Basic validation — reject obviously bad payloads
    if not isinstance(messages, list) or len(messages) == 0:
        return jsonify({"error": "messages must be a non-empty list"}), 400

    # Keep at most the last 20 turns to avoid runaway token costs
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
        reply = response.content[0].text
        return jsonify({"content": reply})

    except Exception as exc:
        log.exception("Anthropic API error")
        return jsonify({"error": str(exc)}), 502


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    log.info("Starting AIBeautyKit server on port %s", port)
    app.run(host="0.0.0.0", port=port)
