"""PayPal transaction verification.

Looks up the claimed transaction in the merchant's real PayPal records using
the PayPal REST APIs:

1. OAuth 2.0 client-credentials token   POST /v1/oauth2/token
2. Capture lookup by ID                 GET  /v2/payments/captures/{id}
3. Fallback: Transaction Search         GET  /v1/reporting/transactions

Without PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET the client runs in demo mode
against a small set of sample records so the app can be tried end to end.
"""
import os
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = {"sandbox": "https://api-m.sandbox.paypal.com", "live": "https://api-m.paypal.com"}

DEMO_RECORDS = {
    "DEMO-VERIFIED-001": {"amount": 180.00, "currency": "USD", "status": "COMPLETED",
                          "payer_email": "buyer@example.com", "date": "2026-11-10"},
    "DEMO-PARTIAL-002": {"amount": 18.00, "currency": "USD", "status": "COMPLETED",
                         "payer_email": "buyer2@example.com", "date": "2026-11-11"},
    "DEMO-PENDING-003": {"amount": 250.00, "currency": "USD", "status": "PENDING",
                         "payer_email": "buyer3@example.com", "date": "2026-11-11"},
}


class PayPalClient:
    def __init__(self):
        self.client_id = os.getenv("PAYPAL_CLIENT_ID")
        self.secret = os.getenv("PAYPAL_CLIENT_SECRET")
        self.base = BASE.get(os.getenv("PAYPAL_ENV", "sandbox"), BASE["sandbox"])
        self._token, self._exp = None, 0

    @property
    def demo(self) -> bool:
        return not (self.client_id and self.secret)

    @property
    def mode(self) -> str:
        return "demo" if self.demo else os.getenv("PAYPAL_ENV", "sandbox")

    def _auth(self) -> str:
        if self._token and time.time() < self._exp - 60:
            return self._token
        r = requests.post(f"{self.base}/v1/oauth2/token", auth=(self.client_id, self.secret),
                          data={"grant_type": "client_credentials"}, timeout=20)
        r.raise_for_status()
        j = r.json()
        self._token, self._exp = j["access_token"], time.time() + j.get("expires_in", 3000)
        return self._token

    def find_transaction(self, transaction_id: str) -> dict | None:
        """Return a normalised record {amount, currency, status, payer_email, date} or None."""
        if not transaction_id:
            return None
        tid = transaction_id.strip().upper()
        if self.demo:
            return DEMO_RECORDS.get(tid)
        h = {"Authorization": f"Bearer {self._auth()}"}
        r = requests.get(f"{self.base}/v2/payments/captures/{tid}", headers=h, timeout=20)
        if r.status_code == 200:
            c = r.json()
            return {"amount": float(c["amount"]["value"]), "currency": c["amount"]["currency_code"],
                    "status": c.get("status"), "payer_email": None,
                    "date": (c.get("create_time") or "")[:10]}
        return self._search(tid, h)

    def _search(self, tid: str, headers: dict) -> dict | None:
        # Transaction Search allows at most a 31-day window per request.
        end = datetime.now(timezone.utc)
        for _ in range(3):  # look back ~90 days
            start = end - timedelta(days=31)
            r = requests.get(f"{self.base}/v1/reporting/transactions", headers=headers, timeout=30, params={
                "transaction_id": tid, "fields": "transaction_info,payer_info",
                "start_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
            if r.status_code == 200:
                for d in r.json().get("transaction_details", []):
                    ti = d.get("transaction_info", {})
                    amt = ti.get("transaction_amount", {})
                    status = {"S": "COMPLETED", "P": "PENDING", "V": "REVERSED", "D": "DENIED"}.get(
                        ti.get("transaction_status"), ti.get("transaction_status"))
                    return {"amount": float(amt.get("value", 0)), "currency": amt.get("currency_code"),
                            "status": status, "payer_email": d.get("payer_info", {}).get("email_address"),
                            "date": (ti.get("transaction_initiation_date") or "")[:10]}
            end = start
        return None
