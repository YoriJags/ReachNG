"""Per-client pricing store — set/get round-trip + topic normalization (faked DB)."""
from __future__ import annotations

import services.pricing as pr


class _FakeCol:
    def __init__(self):
        self.docs = []

    def update_one(self, q, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update["$set"])
                return
        if upsert:
            self.docs.append(dict(update["$set"]))

    def find_one(self, q, *a, **k):
        for d in self.docs:
            if all(d.get(key) == v for key, v in q.items()):
                return d
        return None

    def find(self, q, *a, **k):
        return [d for d in self.docs if all(d.get(k2) == v for k2, v in q.items())]

    def create_index(self, *a, **k):
        pass


def _patch(monkeypatch):
    col = _FakeCol()
    monkeypatch.setattr(pr, "_col", lambda: col)
    return col


def test_set_then_get_roundtrip(monkeypatch):
    _patch(monkeypatch)
    pr.set_pricing("Altitude", "2 Bedroom Flat", 2_500_000, 2_000_000,
                   sweeteners=["free inspection"])
    rules = pr.get_pricing("Altitude", "2 bedroom flats")   # variant of the product
    assert rules is not None
    assert rules["list_price"] == 2_500_000
    assert rules["floor_price"] == 2_000_000
    assert rules["sweeteners"] == ["free inspection"]
    assert rules["product_key"] == "2 bedroom flat"          # normalized + singularized


def test_get_unknown_product_is_none(monkeypatch):
    _patch(monkeypatch)
    pr.set_pricing("Altitude", "duplex", 5_000_000, 4_000_000)
    assert pr.get_pricing("Altitude", "bungalow") is None


def test_pricing_scoped_per_client(monkeypatch):
    _patch(monkeypatch)
    pr.set_pricing("Altitude", "duplex", 5_000_000, 4_000_000)
    assert pr.get_pricing("Other Co", "duplex") is None
    assert len(pr.list_pricing("Altitude")) == 1
