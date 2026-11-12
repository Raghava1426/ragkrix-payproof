"""Combine AI extraction, warning signs and PayPal records into one verdict."""
from . import ai_extractor, risk
from .paypal_client import PayPalClient

VERIFIED, MISMATCH, UNVERIFIED = "VERIFIED", "MISMATCH", "UNABLE_TO_VERIFY"

_client = PayPalClient()


def client() -> PayPalClient:
    return _client


def verify(text: str = "", file_bytes=None, mime_type=None, transaction_id: str = "",
           expected_amount: float | None = None, expected_currency: str = "") -> dict:
    details = ai_extractor.extract(text, file_bytes, mime_type)
    if transaction_id:
        details["transaction_id"] = transaction_id.strip().upper()

    signs = list(details.get("ai_warning_signs") or []) + risk.warning_signs(text, details)
    record, error = None, None
    try:
        record = _client.find_transaction(details.get("transaction_id"))
    except Exception as exc:
        error = f"PayPal lookup failed: {type(exc).__name__}"

    checks, verdict = [], UNVERIFIED
    if record:
        claimed_amt = expected_amount if expected_amount is not None else details.get("amount")
        claimed_cur = (expected_currency or details.get("currency") or "").upper()
        checks.append(("Transaction found in PayPal", True))
        checks.append(("Status is COMPLETED", record["status"] == "COMPLETED"))
        if claimed_amt is not None:
            checks.append((f"Amount matches ({claimed_amt:.2f} vs {record['amount']:.2f})",
                           abs(float(claimed_amt) - record["amount"]) < 0.01))
        if claimed_cur:
            checks.append((f"Currency matches ({claimed_cur} vs {record['currency']})",
                           claimed_cur == record["currency"]))
        verdict = VERIFIED if all(ok for _, ok in checks) else MISMATCH

    explanation = {
        VERIFIED: "PayPal records confirm this payment and the details match. It is safe to proceed.",
        MISMATCH: "A PayPal transaction exists but the details do not match the proof. Do not ship yet.",
        UNVERIFIED: "No matching PayPal transaction could be found. Treat this proof as unconfirmed "
                    "and do not ship until the money appears in your PayPal account.",
    }[verdict]
    if error:
        explanation += f" ({error})"

    return {"verdict": verdict, "explanation": explanation, "extracted": details,
            "paypal_record": record, "checks": [{"check": c, "passed": ok} for c, ok in checks],
            "warning_signs": list(dict.fromkeys(signs)), "paypal_mode": _client.mode}
