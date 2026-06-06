"""Email inbound -> brain -> HITL draft. DB + brain faked, so pure."""
from __future__ import annotations

import services.email_inbound as ei


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
        self.clients_col = _Col(client)
        self.email_col = _Col()

    def __getitem__(self, name):
        return self.clients_col if name == "clients" else self.email_col


def _wire(monkeypatch, client, *, draft="Thanks for your email — happy to help.", calls=None):
    monkeypatch.setattr(ei, "_db", lambda: _Db(client))
    import services.inbound_classifier as ic
    monkeypatch.setattr(ic, "classify_inbound", lambda t: {"intent": "question"}, raising=False)
    import agent.brain as brain
    monkeypatch.setattr(brain, "draft_inbound_reply", lambda **kw: draft)
    import tools.hitl
    rec = calls if calls is not None else []
    monkeypatch.setattr(tools.hitl, "queue_draft", lambda **kw: rec.append(kw) or "id")
    return rec


def test_inbound_email_queues_email_draft(monkeypatch):
    client = {"name": "Altitude", "vertical": "real_estate", "active": True}
    calls = _wire(monkeypatch, client)
    ok = ei.handle_inbound_email(account_id="acc1", from_email="tunde@gmail.com",
                                 from_name="Tunde", subject="Lekki duplex",
                                 body="Is the duplex still available?")
    assert ok is True
    assert len(calls) == 1
    q = calls[0]
    assert q["channel"] == "email"
    assert q["email"] == "tunde@gmail.com"
    assert q["client_name"] == "Altitude"
    assert q["subject"].startswith("Re:")
    assert q["source"] == "email_inbound"


def test_unknown_account_no_draft(monkeypatch):
    calls = _wire(monkeypatch, None)              # no client for this account
    ok = ei.handle_inbound_email(account_id="ghost", from_email="x@y.com",
                                 body="hello?")
    assert ok is False and calls == []


def test_empty_body_ignored(monkeypatch):
    calls = _wire(monkeypatch, {"name": "Altitude", "active": True})
    assert ei.handle_inbound_email(account_id="acc1", from_email="x@y.com", body="") is False
    assert calls == []


def test_blank_draft_not_queued(monkeypatch):
    calls = _wire(monkeypatch, {"name": "Altitude", "active": True}, draft="")
    ok = ei.handle_inbound_email(account_id="acc1", from_email="x@y.com",
                                 body="any update?")
    assert ok is False and calls == []
