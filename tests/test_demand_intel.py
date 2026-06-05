"""Demand intelligence — storage, assembly, and the flag-gated capture wire.

DB + flag are faked so these stay pure.
"""
from __future__ import annotations

import services.demand_intel as di


class _FakeCol:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.inserted = []

    def insert_one(self, doc):
        self.inserted.append(doc)
        self.rows.append(doc)

    def find(self, q, *a, **k):
        # ignore filters except client_name for the test's purposes
        cname = q.get("client_name")
        return [r for r in self.rows if r.get("client_name") == cname]

    def create_index(self, *a, **k):
        pass


def _patch(monkeypatch, col, *, flag=True):
    monkeypatch.setattr(di, "_col", lambda: col)
    monkeypatch.setattr(di, "eyo_enabled", lambda c, f: flag)


def test_capture_records_when_flag_on(monkeypatch):
    col = _FakeCol()
    _patch(monkeypatch, col, flag=True)
    ok = di.maybe_capture_demand({"name": "Altitude"}, "how much for the 2 bedroom?", "234803")
    assert ok is True
    assert len(col.inserted) == 1
    assert col.inserted[0]["topic"] == "2 bedroom"
    assert col.inserted[0]["price_ask"] is True


def test_capture_skipped_when_flag_off(monkeypatch):
    col = _FakeCol()
    _patch(monkeypatch, col, flag=False)
    assert di.maybe_capture_demand({"name": "Altitude"}, "do you have ankara", "234803") is False
    assert col.inserted == []


def test_capture_ignores_non_demand_and_images(monkeypatch):
    col = _FakeCol()
    _patch(monkeypatch, col, flag=True)
    assert di.maybe_capture_demand({"name": "Altitude"}, "thanks see you", "234803") is False
    assert di.maybe_capture_demand({"name": "Altitude"}, "[Image received]", "234803") is False
    assert col.inserted == []


def test_capture_never_raises(monkeypatch):
    # _col blows up -> capture must swallow and return False
    monkeypatch.setattr(di, "eyo_enabled", lambda c, f: True)
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(di, "_col", _boom)
    assert di.maybe_capture_demand({"name": "Altitude"}, "how much for rice?", "234") is False


def test_radar_aggregates_three_mentions(monkeypatch):
    col = _FakeCol([
        {"client_name": "Altitude", "topic": "2 bedroom", "price_ask": True},
        {"client_name": "Altitude", "topic": "2 bedroom", "price_ask": True},
        {"client_name": "Altitude", "topic": "2 bedroom", "price_ask": False},
        {"client_name": "Altitude", "topic": "ankara", "price_ask": False},   # only 1 -> filtered
        {"client_name": "Other", "topic": "noise", "price_ask": True},        # other client
    ])
    _patch(monkeypatch, col, flag=True)
    radar = di.radar_for_client("Altitude", min_mentions=3)
    topics = [s["topic"] for s in radar["signals"]]
    assert topics == ["2 bedroom"]            # ankara (1) filtered by min_mentions
    assert radar["signals"][0]["mentions"] == 3
    assert radar["signals"][0]["price_asks"] == 2


def test_demand_items_scoped_to_client(monkeypatch):
    col = _FakeCol([
        {"client_name": "Altitude", "topic": "flat", "price_ask": True},
        {"client_name": "Other", "topic": "car", "price_ask": True},
    ])
    _patch(monkeypatch, col, flag=True)
    items = di.demand_items_for("Altitude")
    assert items == [{"topic": "flat", "price_ask": True, "quote_sent": False}]
