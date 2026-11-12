"""RAGKRIX PayProof web app (Flask)."""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

from payproof import verifier  # noqa: E402  (load .env before reading config)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB uploads

ALLOWED = {"image/png", "image/jpeg", "image/webp", "application/pdf", "text/plain", "message/rfc822"}


@app.get("/")
def index():
    return render_template("index.html", paypal_mode=verifier.client().mode,
                           ai_on=bool(os.getenv("GEMINI_API_KEY")))


@app.get("/health")
def health():
    return {"status": "ok", "paypal_mode": verifier.client().mode}


@app.post("/api/verify")
def api_verify():
    text = request.form.get("text", "")
    f = request.files.get("file")
    file_bytes = mime = None
    if f and f.filename:
        mime = f.mimetype
        if mime not in ALLOWED:
            return jsonify({"error": f"Unsupported file type {mime}. Use PNG, JPG, WEBP, PDF, TXT or EML."}), 400
        file_bytes = f.read()
        if f.filename.lower().endswith(".eml"):
            mime = "message/rfc822"
        if mime.startswith("text/") or mime == "message/rfc822":
            text += "\n" + file_bytes.decode(errors="ignore")
            file_bytes = None
    if not text.strip() and not file_bytes:
        return jsonify({"error": "Upload a file or paste the payment message."}), 400
    amt = request.form.get("expected_amount", "").strip()
    try:
        expected = float(amt) if amt else None
    except ValueError:
        return jsonify({"error": "Expected amount must be a number."}), 400
    result = verifier.verify(text=text, file_bytes=file_bytes, mime_type=mime,
                             transaction_id=request.form.get("transaction_id", ""),
                             expected_amount=expected,
                             expected_currency=request.form.get("expected_currency", ""))
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG") == "1")
