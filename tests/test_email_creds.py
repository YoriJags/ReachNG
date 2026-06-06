"""Per-client email credentials — encryption round-trip + fail-safe (no key)."""
from __future__ import annotations

import pytest

pytest.importorskip("cryptography")   # CI installs it; skip if absent locally

import services.email_creds as ec


def _with_key(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(ec, "get_settings",
                        lambda: type("S", (), {"email_cred_key": key})())


def test_encrypt_decrypt_roundtrip(monkeypatch):
    _with_key(monkeypatch)
    assert ec.encryption_available() is True
    token = ec._enc("app-password-123")
    assert token and token != "app-password-123"
    assert ec._dec(token) == "app-password-123"


def test_get_credentials_decrypts(monkeypatch):
    _with_key(monkeypatch)
    token = ec._enc("secret-pw")
    doc = {
        "email_provider": "imap",
        "email_imap": {"host": "imap.x", "port": 993, "use_ssl": True},
        "email_smtp": {"host": "smtp.x", "port": 465, "use_ssl": True},
        "email_username": "owner@altitude.ng",
        "email_password_enc": token,
    }
    creds = ec.get_email_credentials(doc)
    assert creds["password"] == "secret-pw"
    assert creds["username"] == "owner@altitude.ng"
    assert creds["imap"]["host"] == "imap.x"


def test_non_imap_client_has_no_creds(monkeypatch):
    _with_key(monkeypatch)
    assert ec.get_email_credentials({"email_provider": "unipile"}) is None
    assert ec.get_email_credentials(None) is None


def test_refuses_to_store_without_key(monkeypatch):
    monkeypatch.setattr(ec, "get_settings",
                        lambda: type("S", (), {"email_cred_key": None})())
    assert ec.encryption_available() is False
    with pytest.raises(RuntimeError):
        ec.set_email_credentials("X", imap_host="i", imap_port=993,
                                 smtp_host="s", smtp_port=465,
                                 username="u", password="p")
