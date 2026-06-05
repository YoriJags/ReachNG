"""Identity resolution — extraction/normalization (pure) + link store (faked)."""
from __future__ import annotations

import pytest

import services.identity as idn


# ── Pure extraction / normalization ───────────────────────────────────────────

@pytest.mark.parametrize("raw,canon", [
    ("08031234567", "2348031234567"),
    ("+2348031234567", "2348031234567"),
    ("2348031234567", "2348031234567"),
    ("0803 123 4567", "2348031234567"),
    ("12345", None),
])
def test_normalize_phone(raw, canon):
    assert idn.normalize_phone(raw) == canon


def test_extract_phone_from_email_signature():
    body = "Thanks,\nTunde\nAltitude Homes\n0803 123 4567"
    assert idn.extract_phone_from_text(body) == "2348031234567"


def test_extract_email_from_whatsapp():
    assert idn.extract_email_from_text("you can mail me Tunde@Gmail.com") == "tunde@gmail.com"


def test_extract_none_when_absent():
    assert idn.extract_phone_from_text("no number here") is None
    assert idn.extract_email_from_text("no email here") is None


# ── Link store (faked collections) ────────────────────────────────────────────

class _Col:
    def __init__(self):
        self.docs = []

    def find_one(self, q, *a, **k):
        for d in self.docs:
            if all(d.get(key) == v for key, v in q.items() if key != "_id"):
                return d
        return None

    def update_one(self, q, update, upsert=False):
        existing = self.find_one(q)
        if existing:
            if "$set" in update:
                existing.update(update["$set"])
            return type("R", (), {"matched_count": 1})()
        if upsert:
            doc = dict(q)
            doc.update(update.get("$set", {}))
            doc.update(update.get("$setOnInsert", {}))
            self.docs.append(doc)
        return type("R", (), {"matched_count": 0})()

    def find(self, q, *a, **k):
        return [d for d in self.docs if all(d.get(key) == v for key, v in q.items())]

    def create_index(self, *a, **k):
        pass


def _patch(monkeypatch):
    links, sugg = _Col(), _Col()
    monkeypatch.setattr(idn, "_links", lambda: links)
    monkeypatch.setattr(idn, "_suggestions", lambda: sugg)
    return links, sugg


def test_link_and_lookup_both_directions(monkeypatch):
    _patch(monkeypatch)
    assert idn.link_identities("Altitude", "08031234567", "Tunde@gmail.com") is True
    assert idn.linked_email_for_phone("Altitude", "+2348031234567") == "tunde@gmail.com"
    assert idn.linked_phone_for_email("Altitude", "tunde@gmail.com") == "2348031234567"


def test_suggest_then_confirm_promotes_to_link(monkeypatch):
    _patch(monkeypatch)
    assert idn.suggest_link("Altitude", "08031234567", "t@x.com", "phone in email") is True
    assert len(idn.pending_links("Altitude")) == 1
    assert idn.confirm_link("Altitude", "08031234567", "t@x.com") is True
    assert idn.linked_phone_for_email("Altitude", "t@x.com") == "2348031234567"
    assert idn.pending_links("Altitude") == []        # no longer pending


def test_suggest_skipped_when_already_linked(monkeypatch):
    _patch(monkeypatch)
    idn.link_identities("Altitude", "08031234567", "t@x.com")
    assert idn.suggest_link("Altitude", "08031234567", "t@x.com") is False
