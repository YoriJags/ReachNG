"""
Transport-correctness guardrails for ReachNG's two-sided stack.

CLIENT EYO ENGINE — a paying client's customer reply must send through THAT
client's transport (Unipile QR account or their Meta WABA), never from ReachNG's
own number, and must fail loudly when credentials are missing.

INTERNAL PROSPECT OS — Yori's acquisition email must route through Resend, never
Unipile.

These tests monkeypatch the leaf send functions so no real network call is made.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

# Required env so `config.get_settings()` constructs before importing outreach.
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/reachng_test")

from tools import outreach  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ─── WhatsApp routing ─────────────────────────────────────────────────────────

def test_unipile_client_sends_via_unipile(monkeypatch):
    calls = {}

    async def fake_unipile(phone, message, account_id):
        calls["unipile"] = {"phone": phone, "account_id": account_id}
        return {"success": True, "message_id": "u1", "provider": "unipile"}

    async def boom_meta(*a, **k):
        raise AssertionError("Meta must not be called for a Unipile client")

    async def boom_bare(*a, **k):
        raise AssertionError("ReachNG's own number (send_whatsapp) must not be called")

    monkeypatch.setattr(outreach, "send_whatsapp_unipile", fake_unipile)
    monkeypatch.setattr(outreach, "send_whatsapp_meta", boom_meta)
    monkeypatch.setattr(outreach, "send_whatsapp", boom_bare)

    client_doc = {"name": "Altitude", "whatsapp_provider": "unipile",
                  "whatsapp_account_id": "acc_altitude"}
    res = _run(outreach.send_whatsapp_for_client("+2348010000000", "hi", client_doc))

    assert res["success"] is True
    assert res["provider"] == "unipile"
    assert calls["unipile"]["account_id"] == "acc_altitude"


def test_meta_client_sends_via_meta(monkeypatch):
    calls = {}

    async def fake_meta(phone, message, pn, tok):
        calls["meta"] = {"pn": pn, "tok": tok}
        return {"success": True, "message_id": "m1"}

    async def boom_unipile(*a, **k):
        raise AssertionError("Unipile must not be called for a Meta client")

    async def boom_bare(*a, **k):
        raise AssertionError("ReachNG's own number must not be called")

    monkeypatch.setattr(outreach, "send_whatsapp_meta", fake_meta)
    monkeypatch.setattr(outreach, "send_whatsapp_unipile", boom_unipile)
    monkeypatch.setattr(outreach, "send_whatsapp", boom_bare)

    client_doc = {"name": "Lex", "whatsapp_provider": "meta",
                  "meta_phone_number_id": "PN1", "meta_access_token": "TOK1"}
    res = _run(outreach.send_whatsapp_for_client("+2348010000000", "hi", client_doc))

    assert res["success"] is True
    assert calls["meta"] == {"pn": "PN1", "tok": "TOK1"}


def test_meta_client_missing_creds_fails_loudly_no_fallback(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("No transport should be invoked when Meta creds are missing")

    monkeypatch.setattr(outreach, "send_whatsapp_meta", boom)
    monkeypatch.setattr(outreach, "send_whatsapp_unipile", boom)
    monkeypatch.setattr(outreach, "send_whatsapp", boom)

    client_doc = {"name": "NoCreds", "whatsapp_provider": "meta"}  # no creds
    res = _run(outreach.send_whatsapp_for_client("+2348010000000", "hi", client_doc))

    assert res["success"] is False
    assert res["error"] == "meta_credentials_missing"


def test_missing_provider_no_account_fails_loudly_not_reachng_number(monkeypatch):
    """No provider + no Unipile account → fail loudly. Crucially, ReachNG's own
    Meta number (send_whatsapp) must NEVER be used as a silent fallback."""
    async def boom_bare(*a, **k):
        raise AssertionError("ReachNG's own number must not be a fallback")

    async def boom_unipile(*a, **k):
        raise AssertionError("Unipile must not be called without an account_id")

    monkeypatch.setattr(outreach, "send_whatsapp", boom_bare)
    monkeypatch.setattr(outreach, "send_whatsapp_unipile", boom_unipile)
    monkeypatch.setattr(outreach, "get_settings",
                        lambda: SimpleNamespace(unipile_whatsapp_account_id=None,
                                                unipile_dsn=None, unipile_api_key=None))

    res = _run(outreach.send_whatsapp_for_client("+2348010000000", "hi", {"name": "Orphan"}))

    assert res["success"] is False
    assert res["error"] == "no_whatsapp_transport"


def test_unipile_send_uses_chats_endpoint(monkeypatch):
    """send_whatsapp_unipile must POST to /api/v1/chats with the account + attendee."""
    captured = {}

    class _Resp:
        status_code = 200
        def json(self):
            return {"id": "chat_123"}

    class _Client:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr(outreach, "get_settings",
                        lambda: SimpleNamespace(unipile_dsn="api8.unipile.com:1234",
                                                unipile_api_key="KEY"))
    monkeypatch.setattr(outreach.httpx, "AsyncClient", _Client)

    res = _run(outreach.send_whatsapp_unipile("+2348010000000", "hi", "acc_x"))

    assert res["success"] is True
    assert captured["url"].endswith("/api/v1/chats")
    assert captured["json"]["account_id"] == "acc_x"
    assert captured["json"]["attendees_ids"] == ["+2348010000000"]
    assert captured["headers"]["X-API-KEY"] == "KEY"


# ─── Email routing (internal acquisition → Resend) ────────────────────────────

def test_internal_prospect_os_email_forces_resend(monkeypatch):
    """BaseCampaign._send must send acquisition email with force_smtp=True so it
    routes via Resend (hello@reachng.ng), never the client's Unipile mailbox."""
    from campaigns.base import BaseCampaign

    captured = {}

    async def fake_send_email(**kwargs):
        captured.update(kwargs)
        return {"success": True, "provider": "resend"}

    monkeypatch.setattr("campaigns.base.send_email", fake_send_email)

    biz = {"name": "Premium Realty", "email": "owner@premium.ng"}
    generated = {"subject": "Quick question", "message": "Hello"}
    _run(BaseCampaign()._send("email", biz, generated))

    assert captured.get("force_smtp") is True


def test_send_email_force_smtp_hits_resend(monkeypatch):
    """With Resend configured + force_smtp=True, send_email posts to the Resend API."""
    captured = {}

    class _Resp:
        def json(self):
            return {"id": "resend_1"}
        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            return _Resp()

    monkeypatch.setattr(outreach, "get_settings",
                        lambda: SimpleNamespace(
                            resend_api_key="re_test", resend_from_email="hello@reachng.ng",
                            unipile_dsn=None, unipile_api_key=None, unipile_email_account_id=None,
                            gmail_address=None, gmail_app_password=None))
    monkeypatch.setattr(outreach.httpx, "AsyncClient", _Client)

    res = _run(outreach.send_email("o@x.ng", "subj", "body", force_smtp=True))

    assert res["success"] is True
    assert res["provider"] == "resend"
    assert "resend.com" in captured["url"]
