"""Meta IG/Messenger adapter — signature, webhook parse, inbound, dormant gate."""
from __future__ import annotations

import hashlib
import hmac

import services.meta_messaging as mm
import services.meta_inbound as mi


# ── Signature ─────────────────────────────────────────────────────────────────

def test_verify_signature_ok():
    secret, body = "appsecret", b'{"a":1}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert mm.verify_signature(secret, body, sig) is True


def test_verify_signature_rejects_tampered():
    assert mm.verify_signature("appsecret", b'{"a":1}', "sha256=deadbeef") is False
    assert mm.verify_signature("appsecret", b'{"a":1}', None) is False


def test_verify_signature_skipped_without_secret():
    # dev: no app secret configured -> skip (logged), don't hard-fail
    assert mm.verify_signature(None, b'{}', None) is True


# ── Webhook parse ─────────────────────────────────────────────────────────────

def test_parse_messenger_event():
    body = {"object": "page", "entry": [
        {"id": "PAGE1", "messaging": [
            {"sender": {"id": "PSID1"}, "recipient": {"id": "PAGE1"},
             "message": {"text": "hi"}}]}]}
    assert mm.parse_webhook(body) == [
        {"channel": "messenger", "account_id": "PAGE1", "sender_id": "PSID1", "text": "hi"}]


def test_parse_instagram_event():
    body = {"object": "instagram", "entry": [
        {"id": "IG1", "messaging": [
            {"sender": {"id": "IGSID"}, "message": {"text": "yo"}}]}]}
    ev = mm.parse_webhook(body)[0]
    assert ev["channel"] == "instagram" and ev["account_id"] == "IG1"


def test_parse_skips_echoes_and_nontext():
    body = {"object": "page", "entry": [{"id": "P", "messaging": [
        {"sender": {"id": "s"}, "message": {"is_echo": True, "text": "x"}},
        {"sender": {"id": "s"}, "message": {}}]}]}
    assert mm.parse_webhook(body) == []


def test_parse_ignores_other_objects():
    assert mm.parse_webhook({"object": "whatsapp_business_account"}) == []
    assert mm.parse_webhook({}) == []


def test_messaging_dormant_by_default():
    # off unless META_MESSAGING_ENABLED is explicitly set
    assert mm.messaging_enabled() is False


# ── Inbound -> brain -> HITL ───────────────────────────────────────────────────

class _Col:
    def __init__(self, client=None):
        self.client = client
        self.inserted = []

    def find_one(self, q, *a, **k):
        return self.client

    def insert_one(self, doc):
        self.inserted.append(doc)


class _Db:
    def __init__(self, client):
        self.c, self.m = _Col(client), _Col()

    def __getitem__(self, name):
        return self.c if name == "clients" else self.m


def _wire(monkeypatch, client, *, draft="Thanks for the DM!"):
    monkeypatch.setattr(mi, "_db", lambda: _Db(client))
    import services.inbound_classifier as ic
    monkeypatch.setattr(ic, "classify_inbound", lambda t: {"intent": "question"}, raising=False)
    import agent.brain as brain
    monkeypatch.setattr(brain, "generate_auto_reply_draft", lambda **kw: draft)
    calls = []
    import tools.hitl
    monkeypatch.setattr(tools.hitl, "queue_draft", lambda **kw: calls.append(kw) or "id")
    return calls


def test_meta_inbound_queues_draft(monkeypatch):
    calls = _wire(monkeypatch, {"name": "Altitude", "vertical": "general", "active": True})
    ok = mi.handle_meta_message(channel="instagram", account_id="IG1",
                                sender_id="user1", text="how much for the gown?")
    assert ok is True and len(calls) == 1
    assert calls[0]["channel"] == "instagram"
    assert calls[0]["source"] == "meta_inbound"
    assert calls[0]["contact_id"] == "user1"


def test_meta_inbound_unknown_account(monkeypatch):
    calls = _wire(monkeypatch, None)
    assert mi.handle_meta_message(channel="messenger", account_id="X",
                                  sender_id="u", text="hi") is False
    assert calls == []
