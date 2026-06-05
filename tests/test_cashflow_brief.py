"""Cashflow live wiring — maps real money-leak numbers onto the forecast core.

money_leak + rescue_targets are monkeypatched so this stays pure.
"""
from __future__ import annotations

import services.cashflow_brief as cb


def _patch(monkeypatch, report, targets=None):
    monkeypatch.setattr(cb, "_dummy", None, raising=False)
    import services.money_leak as ml
    monkeypatch.setattr(ml, "money_leak_report", lambda name, days=30: report)
    monkeypatch.setattr(ml, "rescue_targets", lambda name, days=30, limit=5: targets or [])


_REPORT = {
    "categories": [
        {"key": "confirmed_owed", "amount_ngn": 500_000},
        {"key": "asked_price_no_quote", "amount_ngn": 400_000},
        {"key": "ghosted_promises", "amount_ngn": 150_000},
        {"key": "silent_inbound", "amount_ngn": 50_000},
    ],
    "foreign_quotes": {"USD": 50_000},
}


def test_maps_categories_onto_forecast(monkeypatch):
    _patch(monkeypatch, _REPORT, targets=[{"contact_name": "Tunde"}])
    fc = cb.cashflow_for_client("Altitude", close_rate=0.5)
    # expected = confirmed (500k) + pipeline (400k) * close_rate (0.5) = 700k
    assert fc["expected_ngn"] == 700_000
    # at_risk = ghosted (150k) + silent (50k) = 200k
    assert fc["at_risk_ngn"] == 200_000
    assert fc["is_estimate"] is True
    assert len(fc["nudge_targets"]) == 1


def test_foreign_quotes_passed_through(monkeypatch):
    _patch(monkeypatch, _REPORT)
    fc = cb.cashflow_for_client("Altitude")
    assert fc["foreign_quotes"] == {"USD": 50_000}


def test_default_close_rate_when_unset(monkeypatch):
    _patch(monkeypatch, _REPORT)
    fc = cb.cashflow_for_client("Altitude")   # close_rate=None -> core default
    assert 0.0 <= fc["close_rate"] <= 1.0
    assert fc["expected_ngn"] >= 500_000      # at least the confirmed owed
