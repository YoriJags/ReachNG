"""
EYO Cashflow — the WhatsApp CFO (invention #4).

Forecasts the owner's week from conversation signals: what they're likely to
collect, what's stuck in stalled chats, and who to nudge to wake it up. No
messaging tool offers an owner-side forecast — this is CFO-lite for an SME that
runs on WhatsApp.

Deterministic blend core (pure, no LLM): takes already-gathered figures
(confirmed-owed, hot-pipeline value, historical close-rate, stalled value, nudge
targets) and returns the forecast. The gathering (money_leak + receipt_matches +
outcome_learning) is the wiring slice. Output is clearly an estimate.
"""
from __future__ import annotations

from typing import Iterable, Optional

DEFAULT_CLOSE_RATE = 0.4   # used when a client has no historical close-rate yet


def _ngn(n: float) -> int:
    return int(round(n or 0))


def forecast_week(
    *,
    confirmed_owed_ngn: float = 0.0,
    pipeline_value_ngn: float = 0.0,
    close_rate: Optional[float] = None,
    stalled_value_ngn: float = 0.0,
    nudge_targets: Optional[Iterable[dict]] = None,
) -> dict:
    """Forecast likely collections for the week.

    expected = confirmed obligations due (high certainty)
             + hot-pipeline value × close-rate (probabilistic)
    at_risk  = money sitting in stalled / ghosted chats

    Returns {expected_ngn, at_risk_ngn, close_rate, drivers[], nudge_targets[],
             is_estimate}.
    """
    cr = DEFAULT_CLOSE_RATE if close_rate is None else max(0.0, min(1.0, float(close_rate)))
    pipeline_expected = float(pipeline_value_ngn or 0) * cr
    expected = float(confirmed_owed_ngn or 0) + pipeline_expected

    drivers = []
    if confirmed_owed_ngn:
        drivers.append({"label": "Confirmed owed", "ngn": _ngn(confirmed_owed_ngn),
                        "certainty": "high"})
    if pipeline_value_ngn:
        drivers.append({"label": "Hot pipeline", "ngn": _ngn(pipeline_expected),
                        "raw_ngn": _ngn(pipeline_value_ngn), "close_rate": round(cr, 2),
                        "certainty": "likely"})

    return {
        "expected_ngn":  _ngn(expected),
        "at_risk_ngn":   _ngn(stalled_value_ngn),
        "close_rate":    round(cr, 2),
        "drivers":       drivers,
        "nudge_targets": list(nudge_targets or [])[:5],
        "is_estimate":   True,
    }


def cashflow_summary_text(forecast: dict) -> str:
    """One-line owner-facing summary for the Monday brief / Money tab."""
    exp = forecast.get("expected_ngn", 0)
    risk = forecast.get("at_risk_ngn", 0)
    n = len(forecast.get("nudge_targets") or [])
    parts = [f"This week you're likely to collect about ₦{exp:,.0f}."]
    if risk:
        tail = f" Nudge {n} to wake it up." if n else ""
        parts.append(f"₦{risk:,.0f} is stuck in stalled chats.{tail}")
    parts.append("(Estimate — based on what's owed, your hot pipeline, and your close rate.)")
    return " ".join(parts)
