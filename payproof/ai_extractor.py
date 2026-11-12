"""AI document understanding for RAGKRIX PayProof.

Uses Google Gemini (multimodal) to read a payment screenshot, invoice or
confirmation email and return structured payment details. When no
GEMINI_API_KEY is set, a rule-based fallback extracts details from text so
the app still works in demo mode.
"""
import base64
import json
import os
import re

import requests

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You are a payment-fraud analyst. Read the attached payment proof
(screenshot, invoice or email) and extract the claimed payment details.
Also list any visual or textual warning signs that the proof may be fake or
misleading (edited numbers, mismatched fonts, odd sender domains, urgency or
pressure, requests for refunds of "overpayments", missing transaction IDs,
inconsistent dates or currencies).

Return ONLY JSON with this shape:
{"amount": number|null, "currency": "USD"|"INR"|...|null,
 "sender_name": string|null, "sender_email": string|null,
 "recipient_email": string|null, "transaction_id": string|null,
 "date": "YYYY-MM-DD"|null, "payment_platform": string|null,
 "ai_warning_signs": [string, ...]}"""

FIELDS = ["amount", "currency", "sender_name", "sender_email", "recipient_email",
          "transaction_id", "date", "payment_platform"]


def _empty():
    d = {k: None for k in FIELDS}
    d["ai_warning_signs"] = []
    return d


def extract(text: str = "", file_bytes: bytes | None = None, mime_type: str | None = None) -> dict:
    """Return extracted payment details plus which engine produced them."""
    key = os.getenv("GEMINI_API_KEY")
    if key:
        try:
            data = _extract_gemini(key, text, file_bytes, mime_type)
            data["engine"] = f"gemini:{GEMINI_MODEL}"
            return data
        except Exception as exc:  # fall back rather than fail the whole check
            data = _extract_rules(text)
            data["engine"] = "rules (Gemini error: %s)" % type(exc).__name__
            return data
    data = _extract_rules(text)
    data["engine"] = "rules (demo mode, no GEMINI_API_KEY)"
    return data


def _extract_gemini(key, text, file_bytes, mime_type):
    parts = [{"text": PROMPT}]
    if text:
        parts.append({"text": "Submitted text:\n" + text[:20000]})
    if file_bytes:
        parts.append({"inline_data": {"mime_type": mime_type or "image/png",
                                      "data": base64.b64encode(file_bytes).decode()}})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0}}
    r = requests.post(GEMINI_URL.format(model=GEMINI_MODEL), params={"key": key}, json=body, timeout=60)
    r.raise_for_status()
    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(raw)
    out = _empty()
    out.update({k: parsed.get(k) for k in FIELDS})
    out["ai_warning_signs"] = list(parsed.get("ai_warning_signs") or [])
    if out["amount"] is not None:
        out["amount"] = float(out["amount"])
    return out


CURRENCY_SYMBOLS = {"$": "USD", "₹": "INR", "€": "EUR", "£": "GBP", "Rs": "INR", "Rs.": "INR"}


def _extract_rules(text: str) -> dict:
    out = _empty()
    t = text or ""
    m = re.search(r"(USD|INR|EUR|GBP|\$|₹|€|£|Rs\.?)\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)", t)
    if not m:
        m2 = re.search(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s?(USD|INR|EUR|GBP)", t)
        if m2:
            out["amount"], out["currency"] = float(m2.group(1).replace(",", "")), m2.group(2)
    else:
        sym = m.group(1)
        out["currency"] = CURRENCY_SYMBOLS.get(sym, sym)
        out["amount"] = float(m.group(2).replace(",", ""))
    tid = re.search(r"(?:transaction|txn|capture|reference)\s*(?:id|no\.?|number|#)?\s*[:#]?\s*([A-Z0-9-]{8,})", t, re.I)
    if tid:
        out["transaction_id"] = tid.group(1).upper()
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", t)
    if emails:
        out["sender_email"] = emails[0]
    if len(emails) > 1:
        out["recipient_email"] = emails[1]
    d = re.search(r"(20\d\d-\d\d-\d\d)", t)
    if d:
        out["date"] = d.group(1)
    if re.search(r"paypal", t, re.I):
        out["payment_platform"] = "PayPal"
    return out
