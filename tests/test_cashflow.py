"""EYO Cashflow — WhatsApp CFO forecast (invention #4). Pure checks."""
from __future__ import annotations

from services.cashflow import forecast_week, cashflow_summary_text, DEFAULT_CLOSE_RATE


def test_expected_blends_owed_plus_pipeline_times_close_rate():
    f = forecast_week(confirmed_owed_ngn=500000, pipeline_value_ngn=1000000, close_rate=0.5)
    assert f["expected_ngn"] == 500000 + 500000   # owed + 1M*0.5


def test_default_close_rate_when_unknown():
    f = forecast_week(pipeline_value_ngn=1000000)
    assert f["close_rate"] == round(DEFAULT_CLOSE_RATE, 2)
    assert f["expected_ngn"] == int(round(1000000 * DEFAULT_CLOSE_RATE))


def test_close_rate_clamped():
    assert forecast_week(pipeline_value_ngn=100000, close_rate=5)["close_rate"] == 1.0
    assert forecast_week(pipeline_value_ngn=100000, close_rate=-1)["close_rate"] == 0.0


def test_at_risk_passthrough_and_nudge_cap():
    f = forecast_week(stalled_value_ngn=640000,
                      nudge_targets=[{"name": f"C{i}"} for i in range(9)])
    assert f["at_risk_ngn"] == 640000
    assert len(f["nudge_targets"]) == 5     # capped


def test_drivers_present():
    f = forecast_week(confirmed_owed_ngn=200000, pipeline_value_ngn=400000, close_rate=0.25)
    labels = {d["label"] for d in f["drivers"]}
    assert {"Confirmed owed", "Hot pipeline"} <= labels


def test_summary_text():
    f = forecast_week(confirmed_owed_ngn=900000, stalled_value_ngn=300000,
                      nudge_targets=[{"name": "Tunde"}])
    txt = cashflow_summary_text(f)
    assert "₦900,000" in txt
    assert "₦300,000" in txt
    assert "estimate" in txt.lower()
