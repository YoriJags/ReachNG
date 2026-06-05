"""Referral live-path wiring — flag gate, strong-win gate, dedupe, non-blocking.

All externals (flag read, asks collection, HITL queue_draft) are faked so this
stays pure.
"""
from __future__ import annotations

import services.referral_wire as rw


class _FakeCol:
    def __init__(self, existing=None):
        self.docs = list(existing or [])
        self.inserted = []

    def find_one(self, q, *a, **k):
        for d in self.docs:
            if all(d.get(key) == val for key, val in q.items() if key != "_id"):
                return d
        return None

    def insert_one(self, doc):
        self.docs.append(doc)
        self.inserted.append(doc)


def _wire(monkeypatch, *, flag=True, col=None, queue=None):
    monkeypatch.setattr(rw, "eyo_enabled", lambda c, f: flag)
    fake_col = col if col is not None else _FakeCol()
    monkeypatch.setattr(rw, "_asks_col", lambda: fake_col)
    calls = []
    def _queue(**kwargs):
        calls.append(kwargs)
        if queue == "raise":
            raise RuntimeError("hitl down")
        return "approval_id"
    import tools.hitl
    monkeypatch.setattr(tools.hitl, "queue_draft", _queue)
    return fake_col, calls


def test_strong_win_queues_a_draft(monkeypatch):
    col, calls = _wire(monkeypatch)
    ok = rw.maybe_ask_referral(client_name="Altitude", contact_phone="2348031234567",
                               contact_name="Tunde", win_signal="paid")
    assert ok is True
    assert len(calls) == 1
    assert calls[0]["source"] == "referral" and calls[0]["channel"] == "whatsapp"
    assert calls[0]["client_name"] == "Altitude"
    assert "Tunde" in calls[0]["message"]
    assert len(col.inserted) == 1   # ask recorded for dedupe


def test_soft_win_does_not_ask(monkeypatch):
    _, calls = _wire(monkeypatch)
    assert rw.maybe_ask_referral(client_name="Altitude", contact_phone="234803",
                                 win_signal="interested") is False
    assert calls == []


def test_flag_off_does_not_ask(monkeypatch):
    _, calls = _wire(monkeypatch, flag=False)
    assert rw.maybe_ask_referral(client_name="Altitude", contact_phone="234803",
                                 win_signal="paid") is False
    assert calls == []


def test_never_asks_twice(monkeypatch):
    seeded = _FakeCol([{"client_name": "Altitude", "contact_phone": "234803"}])
    _, calls = _wire(monkeypatch, col=seeded)
    assert rw.maybe_ask_referral(client_name="Altitude", contact_phone="234803",
                                 win_signal="booked") is False
    assert calls == []


def test_blank_inputs_are_safe(monkeypatch):
    _, calls = _wire(monkeypatch)
    assert rw.maybe_ask_referral(client_name="", contact_phone="x", win_signal="paid") is False
    assert rw.maybe_ask_referral(client_name="Altitude", contact_phone="", win_signal="paid") is False


def test_queue_failure_is_swallowed(monkeypatch):
    _, calls = _wire(monkeypatch, queue="raise")
    # queue_draft raising must not propagate — wiring is non-blocking
    assert rw.maybe_ask_referral(client_name="Altitude", contact_phone="234803",
                                 contact_name="Bola", win_signal="paid") is False
