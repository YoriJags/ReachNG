"""
EYO Shield — fake-transfer detector scoring (invention #1).

Pure deterministic checks on the scorer. No DB / LLM.
"""
from __future__ import annotations

from services.shield import (
    assess_transfer, shield_alert_text, RISK_CLEAR, RISK_REVIEW, RISK_HIGH,
)


def _receipt(**over):
    base = {
        "is_receipt": True, "status": "success", "amount_ngn": 90000,
        "recipient_account": "0123456789", "recipient_name": "Altitude Lagos",
        "reference": "REF-001", "confidence": 0.9,
    }
    base.update(over)
    return base


def test_non_receipt_is_clear():
    v = assess_transfer({"is_receipt": False})
    assert v["risk"] == RISK_CLEAR and v["is_receipt"] is False and v["verify"] is False


def test_clean_matching_transfer_is_clear():
    v = assess_transfer(
        _receipt(),
        expected_amount=90000,
        client_account="0123456789",
        prior_references={"REF-OLD"},
    )
    assert v["risk"] == RISK_CLEAR
    assert v["verify"] is False


def test_pending_status_flags_review_or_high():
    v = assess_transfer(_receipt(status="pending"))
    assert v["verify"] is True
    assert any("success" in r.lower() or "land" in r.lower() for r in v["reasons"])


def test_failed_status_is_high():
    v = assess_transfer(_receipt(status="failed"))
    assert v["risk"] == RISK_HIGH


def test_amount_mismatch_flagged():
    v = assess_transfer(_receipt(amount_ngn=5000), expected_amount=90000)
    assert v["verify"] is True
    assert any("match" in r.lower() for r in v["reasons"])


def test_wrong_recipient_account_is_high():
    v = assess_transfer(_receipt(recipient_account="9999999999"),
                        client_account="0123456789")
    assert v["risk"] == RISK_HIGH
    assert any("isn't yours" in r.lower() or "not yours" in r.lower() for r in v["reasons"])


def test_reused_reference_is_high():
    v = assess_transfer(_receipt(reference="REF-DUP"),
                        prior_references={"REF-DUP"})
    assert v["risk"] == RISK_HIGH
    assert any("reference" in r.lower() for r in v["reasons"])


def test_repeat_offender_raises_risk():
    clean = assess_transfer(_receipt())
    flagged = assess_transfer(_receipt(), repeat_offender=True)
    assert flagged["score"] > clean["score"]
    assert flagged["verify"] is True


def test_recipient_name_mismatch_when_no_account():
    v = assess_transfer(
        _receipt(recipient_account=None, recipient_name="Some Other Person"),
        client_account_names=["Altitude Lagos", "Altitude Lounge Ltd"],
    )
    assert any("name" in r.lower() for r in v["reasons"])


def test_alert_text_has_amount_and_reasons():
    r = _receipt(status="pending", amount_ngn=90000)
    v = assess_transfer(r)
    txt = shield_alert_text("Tunde A.", r, v)
    assert "₦90,000" in txt
    assert "Tunde A." in txt
    assert "bank app" in txt.lower()
