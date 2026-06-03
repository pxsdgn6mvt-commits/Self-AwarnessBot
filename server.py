import os
import io
import re
import uuid
import base64
import shutil
import logging
import subprocess
import mimetypes
from pathlib import Path
from flask import Flask, request, jsonify, Response

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_DIR = Path(BASE_DIR) / "content_tmp"
CONTENT_DIR.mkdir(exist_ok=True)

_SESSION_RE = re.compile(r'^[a-f0-9]{8}$')

app = Flask(__name__)


def _safe_content_path(session_id: str, filename: str) -> Path | None:
    if not _SESSION_RE.match(session_id):
        return None
    candidate = (CONTENT_DIR / session_id / filename).resolve()
    if not str(candidate).startswith(str(CONTENT_DIR.resolve())):
        return None
    return candidate

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


@app.route("/content-editor")
def content_editor():
    return _read_html("content-editor.html")


@app.route("/api/content/download", methods=["POST"])
def content_download():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Нужна ссылка"}), 400

    session_id = uuid.uuid4().hex[:8]
    out_dir = CONTENT_DIR / session_id
    out_dir.mkdir(exist_ok=True)

    try:
        import yt_dlp
        ydl_opts = {
            "outtmpl": str(out_dir / "%(autonumber)03d.%(ext)s"),
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
        VIDEO_EXT = {".mp4", ".mov", ".webm"}
        files = []
        for f in sorted(out_dir.iterdir()):
            ext = f.suffix.lower()
            if ext in IMAGE_EXT or ext in VIDEO_EXT:
                files.append({
                    "name": f.name,
                    "url": f"/api/content/files/{session_id}/{f.name}",
                    "type": "video" if ext in VIDEO_EXT else "image",
                })

        return jsonify({"session_id": session_id, "files": files})
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        log.exception("Download error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/content/files/<session_id>/<filename>")
def content_file(session_id, filename):
    path = _safe_content_path(session_id, filename)
    if not path or not path.exists():
        return "not found", 404
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    with open(path, "rb") as f:
        return Response(f.read(), mimetype=mime)


@app.route("/api/content/rewrite", methods=["POST"])
def content_rewrite():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "API key not configured"}), 500

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=(
                "Ты переписываешь текст для социальных сетей. "
                "Сохраняй тему и смысл, но меняй формулировки — текст не должен быть копией оригинала. "
                "Делай его ёмким и цепляющим. Отвечай на том же языке что и входной текст. "
                "Только переписанный текст, без пояснений."
            ),
            messages=[{"role": "user", "content": text}],
        )
        return jsonify({"rewritten": response.content[0].text})
    except Exception as e:
        log.exception("Rewrite error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/content/process-image", methods=["POST"])
def content_process_image():
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return jsonify({"error": "Pillow не установлен"}), 500

    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "").strip()
    filename = data.get("filename", "").strip()
    logo_b64 = data.get("logo_b64") or ""
    masks = data.get("masks", [])
    color_tint = data.get("color_tint")

    img_path = _safe_content_path(session_id, filename)
    if not img_path or not img_path.exists():
        return jsonify({"error": "Файл не найден"}), 404

    try:
        img = Image.open(img_path).convert("RGBA")
        iw, ih = img.size

        for m in masks:
            x = max(0, int(m["x"] * iw))
            y = max(0, int(m["y"] * ih))
            w = min(int(m["w"] * iw), iw - x)
            h = min(int(m["h"] * ih), ih - y)
            if w > 0 and h > 0:
                region = img.crop((x, y, x + w, y + h))
                img.paste(region.filter(ImageFilter.GaussianBlur(radius=20)), (x, y))

        if color_tint:
            tint = Image.new("RGBA", img.size, (
                int(color_tint.get("r", 0)),
                int(color_tint.get("g", 0)),
                int(color_tint.get("b", 0)),
                int(color_tint.get("opacity", 0.2) * 255),
            ))
            img = Image.alpha_composite(img, tint)

        if logo_b64:
            logo = Image.open(io.BytesIO(base64.b64decode(logo_b64))).convert("RGBA")
            lw = int(iw * 0.15)
            lh = int(logo.height * lw / logo.width)
            logo = logo.resize((lw, lh), Image.LANCZOS)
            img.paste(logo, (iw - lw - 16, ih - lh - 16), logo)

        result_name = f"processed_{uuid.uuid4().hex[:6]}_{filename}"
        result_path = _safe_content_path(session_id, result_name)
        img.convert("RGB").save(result_path, "JPEG", quality=92)

        return jsonify({
            "url": f"/api/content/files/{session_id}/{result_name}",
            "filename": result_name,
        })
    except Exception as e:
        log.exception("Image processing error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/content/process-video", methods=["POST"])
def content_process_video():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "").strip()
    filename = data.get("filename", "").strip()
    logo_b64 = data.get("logo_b64") or ""

    vid_path = _safe_content_path(session_id, filename)
    if not vid_path or not vid_path.exists():
        return jsonify({"error": "Файл не найден"}), 404

    if not logo_b64:
        return jsonify({"error": "Нужен логотип"}), 400

    try:
        logo_tmp = _safe_content_path(session_id, "_logo_tmp.png")
        with open(logo_tmp, "wb") as f:
            f.write(base64.b64decode(logo_b64))

        result_name = f"processed_{filename}"
        result_path = _safe_content_path(session_id, result_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(vid_path),
            "-i", str(logo_tmp),
            "-filter_complex", "overlay=W-w-16:H-h-16",
            "-c:a", "copy",
            str(result_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace")[-300:]
            return jsonify({"error": f"ffmpeg: {err}"}), 500

        return jsonify({
            "url": f"/api/content/files/{session_id}/{result_name}",
            "filename": result_name,
        })
    except Exception as e:
        log.exception("Video processing error")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    log.info("Starting on port %s", port)
    app.run(host="0.0.0.0", port=port)
