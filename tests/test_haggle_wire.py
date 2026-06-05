"""Haggle live wiring — flag gate, pricing gate, counter vs below-floor escalate.

maybe_haggle is async; we drive it with asyncio.run (no pytest-asyncio dep).
All externals faked.
"""
from __future__ import annotations

import asyncio

import services.haggle_wire as hw


_RULES = {
    "list_price": 2_500_000, "floor_price": 2_000_000,
    "sweeteners": [], "max_rounds": 3, "product": "2 bedroom", "product_key": "2 bedroom",
}


def _wire(monkeypatch, *, flag=True, rules=_RULES):
    monkeypatch.setattr(hw, "eyo_enabled", lambda c, f: flag)
    monkeypatch.setattr(hw, "get_pricing", lambda c, t: rules)
    monkeypatch.setattr(hw, "_get_state", lambda *a, **k: None)
    monkeypatch.setattr(hw, "_save_state", lambda *a, **k: None)
    drafts, alerts = [], []
    import tools.hitl
    monkeypatch.setattr(tools.hitl, "queue_draft", lambda **kw: drafts.append(kw) or "id")
    import tools.outreach
    async def _send(**kw):
        alerts.append(kw)
    monkeypatch.setattr(tools.outreach, "send_whatsapp_for_client", _send)
    return drafts, alerts


def _run(coro):
    return asyncio.run(coro)


def test_counter_alerts_owner_and_queues_draft(monkeypatch):
    drafts, alerts = _wire(monkeypatch)
    ok = _run(hw.maybe_haggle({"name": "Altitude", "owner_phone": "234999"},
                              "can you do 2.2m for the 2 bedroom", "234803"))
    assert ok is True
    assert len(drafts) == 1 and drafts[0]["source"] == "haggle"
    assert len(alerts) == 1                   # owner-first: pinged on every haggle


def test_no_owner_phone_still_drafts(monkeypatch):
    drafts, alerts = _wire(monkeypatch)
    ok = _run(hw.maybe_haggle({"name": "Altitude"},          # no owner_phone
                              "can you do 2.2m for the 2 bedroom", "234803"))
    assert ok is True and len(drafts) == 1 and alerts == []


def test_below_floor_escalates_and_alerts_owner(monkeypatch):
    drafts, alerts = _wire(monkeypatch)      # sweeteners=[] -> below floor escalates
    ok = _run(hw.maybe_haggle({"name": "Altitude", "owner_phone": "234999"},
                              "₦1,000,000 last price for the 2 bedroom", "234803"))
    assert ok is True
    assert len(alerts) == 1                   # owner pinged to decide
    assert len(drafts) == 1                   # customer gets a neutral holding line


def test_flag_off_does_nothing(monkeypatch):
    drafts, alerts = _wire(monkeypatch, flag=False)
    ok = _run(hw.maybe_haggle({"name": "Altitude"},
                              "any discount for the 2 bedroom?", "234803"))
    assert ok is False and drafts == [] and alerts == []


def test_no_pricing_set_skips(monkeypatch):
    drafts, alerts = _wire(monkeypatch, rules=None)
    ok = _run(hw.maybe_haggle({"name": "Altitude"},
                              "any discount for the 2 bedroom?", "234803"))
    assert ok is False and drafts == []


def test_not_a_haggle_skips(monkeypatch):
    drafts, alerts = _wire(monkeypatch)
    ok = _run(hw.maybe_haggle({"name": "Altitude"}, "I'll take it, thanks", "234803"))
    assert ok is False and drafts == []
