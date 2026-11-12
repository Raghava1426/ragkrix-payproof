import os

os.environ.pop("PAYPAL_CLIENT_ID", None)
os.environ.pop("GEMINI_API_KEY", None)

from app import app  # noqa: E402


def post(**data):
    return app.test_client().post("/api/verify", data=data)


def test_verified():
    r = post(text="I have paid $180.00 via PayPal. Transaction ID: DEMO-VERIFIED-001").get_json()
    assert r["verdict"] == "VERIFIED"
    assert r["extracted"]["amount"] == 180.0


def test_amount_mismatch():
    r = post(text="Paid $180.00. Transaction ID: DEMO-PARTIAL-002").get_json()
    assert r["verdict"] == "MISMATCH"


def test_pending_is_mismatch():
    r = post(text="Paid $250.00", transaction_id="DEMO-PENDING-003").get_json()
    assert r["verdict"] == "MISMATCH"


def test_fake_unverified_with_warnings():
    r = post(text="URGENT: payment of $250.00 is pending until you ship. From service@paypal-secure-mail.com").get_json()
    assert r["verdict"] == "UNABLE_TO_VERIFY"
    joined = " ".join(r["warning_signs"])
    assert "imitates PayPal" in joined and "urgency" in joined and "No transaction ID" in joined


def test_expected_amount_overrides():
    r = post(text="Transaction ID: DEMO-VERIFIED-001", expected_amount="200").get_json()
    assert r["verdict"] == "MISMATCH"


def test_empty_rejected():
    assert post().status_code == 400


def test_home_page():
    assert b"PayProof" in app.test_client().get("/").data
