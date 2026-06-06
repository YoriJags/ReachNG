"""GUARDRAIL: nothing breaks when external integrations are unconfigured.

These lock in the promise that the product runs fine BEFORE Meta grants IG/FB,
and with no Unipile and no email creds. CI runs the whole suite with none of
those credentials, so this just asserts the gates are explicit + fail-safe.
If any of these fail, an external dependency has crept into a core path.
"""
from __future__ import annotations

import os

# config.Settings requires these two just to import the app (same as CI). Set
# throwaway values so this module is self-sufficient when run in isolation. We do
# NOT set any Meta / Unipile / email credentials — that's the whole point.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-guardrail")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/guardrail")


def test_app_imports_without_meta_or_email_creds():
    """The app boots without Meta / IG / FB / email credentials present.
    (CI's environment has none of them.)"""
    import main
    assert main.app is not None


def test_unipile_gate_is_safe():
    """unipile_enabled() must return a bool, never raise — channels no-op when
    Unipile isn't configured."""
    from config import unipile_enabled
    assert isinstance(unipile_enabled(), bool)


def test_email_encryption_gate_off_without_key(monkeypatch):
    """No EMAIL_CRED_KEY -> the IMAP email feature is simply off, never a crash
    and never plaintext storage."""
    import services.email_creds as ec
    monkeypatch.setattr(ec, "get_settings",
                        lambda: type("S", (), {"email_cred_key": None})())
    assert ec.encryption_available() is False


def test_client_email_send_without_creds_is_false():
    """Sending from a client mailbox with no creds returns False, never raises."""
    from services.email_imap import send_email_via_client
    assert send_email_via_client({"name": "X"}, to_email="a@b.com",
                                 subject="s", body="b") is False


def test_eyo_invention_flags_fail_safe_off():
    """An unknown / unconfigured flag is OFF and never raises (short-circuits
    before any DB call) — inventions stay dark until explicitly enabled."""
    from services.eyo_flags import eyo_enabled
    assert eyo_enabled("Anyone", "not_a_real_feature") is False
    assert eyo_enabled("", "shield") is False
