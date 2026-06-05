"""Cashflow wiring (EYO invention #4, live path).

Now that money_leak values each lead for real, Cashflow can forecast the week
from honest numbers instead of restating the collectible headline. This adapter
maps the already-computed money-leak categories onto the tested forecast core
(services/cashflow.forecast_week):

  confirmed_owed  = ledgers owed (high certainty)
  pipeline_value  = "asked price, no quote" leads (warm, likely-to-close-on-nudge)
  stalled / risk  = ghosted "I'll pay" + silent inbound (money stuck)
  nudge_targets   = rescue_targets (who to poke to wake it up)

Thin + reuses money_leak's one resolve, so no extra DB logic here. Flag-gated by
the caller (portal / brief) on the client's `cashflow` flag.

close_rate is left at the core's documented default for now; deriving it from
each client's win/miss history is a later refinement.
"""
from __future__ import annotations

from typing import Optional

import structlog

from services.cashflow import forecast_week

log = structlog.get_logger()

# Need at least this many resolved deals before a client's own win-rate is
# trustworthy; below it we fall back to the core default.
_MIN_RESOLVED = 5


def _close_rate(client_name: str) -> Optional[float]:
    """A client's historical win-rate as the close_rate, or None (-> core
    default) when there isn't enough history yet. Best-effort, never raises."""
    try:
        from database import get_db
        c = get_db()["clients"].find_one({"name": client_name}, {"_id": 1})
        if not c:
            return None
        from services.outcome_learning import client_outcome_stats
        stats = client_outcome_stats(str(c["_id"]))
        resolved = (stats.get("wins") or 0) + (stats.get("misses") or 0)
        wr = stats.get("win_rate")
        return wr if (wr is not None and resolved >= _MIN_RESOLVED) else None
    except Exception:
        return None


def cashflow_for_client(client_name: str, *, days: int = 30,
                        close_rate: Optional[float] = None) -> dict:
    """Forecast the week for one client from real money-leak numbers.

    close_rate: explicit override wins; otherwise we use the client's own
    historical win-rate when there's enough history, else the core default.
    """
    from services.money_leak import money_leak_report, rescue_targets

    if close_rate is None:
        close_rate = _close_rate(client_name)

    rep = money_leak_report(client_name, days=days)
    cats = {c["key"]: c for c in rep.get("categories", [])}

    def _amt(key: str) -> float:
        return float((cats.get(key) or {}).get("amount_ngn") or 0)

    confirmed = _amt("confirmed_owed")
    pipeline = _amt("asked_price_no_quote")
    stalled = _amt("ghosted_promises") + _amt("silent_inbound")
    targets = rescue_targets(client_name, days=days, limit=5)

    forecast = forecast_week(
        confirmed_owed_ngn=confirmed,
        pipeline_value_ngn=pipeline,
        close_rate=close_rate,
        stalled_value_ngn=stalled,
        nudge_targets=targets,
    )
    # Pass foreign quotes through untouched — surfaced apart, never in expected.
    forecast["foreign_quotes"] = rep.get("foreign_quotes", {})
    return forecast
