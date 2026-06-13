"""Per-plan model tiering — the client's plan picks the brain. Fail-safe to Haiku."""
from __future__ import annotations

import services.model_tier as mt
from services.model_tier import HAIKU, SONNET, OPUS, model_for


class _FakeClients:
    def __init__(self, doc):
        self._doc = doc

    def find_one(self, query, projection=None):
        return self._doc


class _FakeDB:
    def __init__(self, doc):
        self._col = _FakeClients(doc)

    def __getitem__(self, name):
        return self._col


def _install(monkeypatch, doc):
    monkeypatch.setattr(mt, "get_db", lambda: _FakeDB(doc))


def test_starter_gets_haiku(monkeypatch):
    _install(monkeypatch, {"plan": "starter"})
    assert model_for("Solo Biz") == HAIKU


def test_growth_gets_sonnet(monkeypatch):
    _install(monkeypatch, {"plan": "growth"})
    assert model_for("Team Biz") == SONNET


def test_agency_gets_opus(monkeypatch):
    _install(monkeypatch, {"plan": "agency"})
    assert model_for("Empire Biz") == OPUS


def test_per_client_override_wins(monkeypatch):
    # Solo plan, but pinned to Opus as a VIP courtesy.
    _install(monkeypatch, {"plan": "starter", "model_tier": OPUS})
    assert model_for("VIP on Solo") == OPUS


def test_override_accepts_slug(monkeypatch):
    _install(monkeypatch, {"plan": "starter", "model_tier": "growth"})
    assert model_for("Bumped") == SONNET


def test_unknown_plan_falls_back_to_haiku(monkeypatch):
    _install(monkeypatch, {"plan": "mystery"})
    assert model_for("Weird Plan") == HAIKU


def test_missing_client_falls_back(monkeypatch):
    _install(monkeypatch, None)              # no client doc
    assert model_for("Ghost") == HAIKU


def test_no_name_returns_default():
    assert model_for(None) == HAIKU
    assert model_for("") == HAIKU


def test_db_error_fails_safe(monkeypatch):
    class _Boom:
        def __getitem__(self, name):
            raise RuntimeError("db down")
    monkeypatch.setattr(mt, "get_db", lambda: _Boom())
    assert model_for("Anyone") == HAIKU      # never raises, never over-bills


def test_brain_label():
    assert mt.brain_label(OPUS) == "Opus 4.8"
    assert mt.brain_label(HAIKU) == "Haiku 4.5"


def test_draft_cost_per_model():
    assert mt.draft_cost_ngn(HAIKU) == 4.0
    assert mt.draft_cost_ngn(SONNET) == 12.0
    assert mt.draft_cost_ngn(OPUS) == 20.0
    assert mt.draft_cost_ngn("unknown-model") == 4.0   # floor


def test_draft_cost_for_client_uses_plan(monkeypatch):
    _install(monkeypatch, {"plan": "agency"})          # Empire → Opus
    assert mt.draft_cost_for("Empire Biz") == 20.0


def test_draft_cost_for_fails_safe(monkeypatch):
    class _Boom:
        def __getitem__(self, name):
            raise RuntimeError("db down")
    monkeypatch.setattr(mt, "get_db", lambda: _Boom())
    assert mt.draft_cost_for("Anyone") == 4.0          # Haiku floor on failure
