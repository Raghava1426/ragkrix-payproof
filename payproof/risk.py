"""Rule-based warning signs that complement the AI's own findings."""
import re

URGENCY = ["urgent", "immediately", "asap", "within 1 hour", "account will be", "suspended",
           "limited time", "act now", "final notice"]
OVERPAY = ["overpaid", "overpayment", "refund the difference", "send back", "extra amount"]
SUSPICIOUS_DOMAINS = re.compile(r"@(?!paypal\.com\b)[\w.-]*paypal[\w.-]*\.", re.I)
PENDING = ["pending", "on hold", "will be released", "once you ship", "upon shipment",
           "tracking number to release"]


def warning_signs(text: str, details: dict) -> list[str]:
    t = (text or "").lower()
    signs = []
    if any(w in t for w in URGENCY):
        signs.append("Message uses urgency or pressure language.")
    if any(w in t for w in OVERPAY):
        signs.append("Mentions an overpayment or asks you to send money back — a common scam.")
    if any(w in t for w in PENDING):
        signs.append("Claims funds are 'pending' until you ship — PayPal does not hold payments for tracking numbers.")
    for e in [details.get("sender_email"), details.get("recipient_email")] + re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", t):
        if e and SUSPICIOUS_DOMAINS.search(e):
            signs.append(f"Email '{e}' imitates PayPal but is not from paypal.com.")
            break
    if not details.get("transaction_id"):
        signs.append("No transaction ID found — genuine PayPal receipts include one.")
    if details.get("amount") is None:
        signs.append("Could not find a payment amount.")
    return signs
