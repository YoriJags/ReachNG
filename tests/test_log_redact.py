"""PII redaction processor — phones/emails never reach the logs."""
from __future__ import annotations

from tools.log_redact import redact_pii


def test_redacts_phone_field():
    out = redact_pii(None, "info", {"event": "whatsapp_sent", "phone": "2348031234567"})
    assert out["phone"] == "[phone]"


def test_redacts_local_phone_and_email_in_message():
    out = redact_pii(None, "info",
                     {"event": "mailed 08031234567 at tunde@gmail.com"})
    assert "08031234567" not in out["event"]
    assert "tunde@gmail.com" not in out["event"]
    assert "[phone]" in out["event"] and "[email]" in out["event"]


def test_redacts_email_field():
    out = redact_pii(None, "info", {"event": "x", "email": "owner@altitude.ng"})
    assert out["email"] == "[email]"


def test_leaves_non_pii_untouched():
    out = redact_pii(None, "info",
                     {"event": "draft_sent", "client": "Altitude", "count": 3})
    assert out["client"] == "Altitude" and out["count"] == 3
