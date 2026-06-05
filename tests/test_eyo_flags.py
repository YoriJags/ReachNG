"""EYO per-client feature flags — pure guard logic + fail-safe behaviour.

DB reads are exercised with a fake get_db so these stay pure (no Mongo).
"""
from __future__ import annotations

import database
from services.eyo_flags import EYO_FEATURES, eyo_enabled, eyo_flags_for


class _FakeCol:
    def __init__(self, doc):
        self._doc = doc

    def find_one(self, *args, **kwargs):
        return self._doc


class _FakeDb:
    def __init__(self, doc):
        self._col = _FakeCol(doc)

    def __getitem__(self, _name):
        return self._col


def _patch_db(monkeypatch, doc):
    monkeypatch.setattr(database, "get_db", lambda: _FakeDb(doc))


def test_five_canonical_features():
    assert set(EYO_FEATURES) == {"shield", "haggle", "radar", "cashflow", "referral"}


def test_unknown_feature_is_off():
    assert eyo_enabled("Altitude Lagos", "telepathy") is False


def test_blank_client_is_off():
    assert eyo_enabled("", "cashflow") is False


def test_enabled_when_flag_true(monkeypatch):
    _patch_db(monkeypatch, {"eyo": {"cashflow": True}})
    assert eyo_enabled("Altitude Lagos", "cashflow") is True


def test_off_by_default_when_absent(monkeypatch):
    _patch_db(monkeypatch, {"name": "Altitude Lagos"})   # no "eyo" key
    assert eyo_enabled("Altitude Lagos", "cashflow") is False


def test_other_flag_does_not_leak(monkeypatch):
    _patch_db(monkeypatch, {"eyo": {"radar": True}})
    assert eyo_enabled("Altitude Lagos", "radar") is True
    assert eyo_enabled("Altitude Lagos", "cashflow") is False


def test_missing_client_is_off(monkeypatch):
    _patch_db(monkeypatch, None)
    assert eyo_enabled("Ghost Co", "shield") is False


def test_db_error_fails_safe_to_off(monkeypatch):
    def _boom():
        raise RuntimeError("mongo down")
    monkeypatch.setattr(database, "get_db", _boom)
    assert eyo_enabled("Altitude Lagos", "cashflow") is False


def test_flags_for_returns_all_keys(monkeypatch):
    _patch_db(monkeypatch, {"eyo": {"cashflow": True, "radar": True}})
    flags = eyo_flags_for("Altitude Lagos")
    assert set(flags) == set(EYO_FEATURES)
    assert flags["cashflow"] is True and flags["radar"] is True
    assert flags["shield"] is False
