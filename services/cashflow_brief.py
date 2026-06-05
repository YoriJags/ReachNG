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


def cashflow_for_client(client_name: str, *, days: int = 30,
                        close_rate: Optional[float] = None) -> dict:
    """Forecast the week for one client from real money-leak numbers."""
    from services.money_leak import money_leak_report, rescue_targets

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
