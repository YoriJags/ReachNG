"""
EYO Radar — demand intelligence from the aggregate inbox (invention #3).

Meta's agent answers one chat at a time. Radar reads ALL inbound across a
client's customers and briefs the OWNER on what the market is asking for:
unmet demand, missing prices, the thing 14 people wanted this week that you
never listed a price for.

This module is the deterministic aggregation core (pure, no LLM): it takes
demand items that already carry a `topic` + flags (the text→topic extraction is
the upstream wiring, reusing the inbound classifier, exactly like Shield takes an
already-extracted receipt) and produces a ranked, owner-facing radar.
"""
from __future__ import annotations

from typing import Iterable, Optional


def build_radar(
    items: Iterable[dict],
    *,
    known_prices: Optional[Iterable[str]] = None,
    min_mentions: int = 3,
    top_n: int = 5,
) -> dict:
    """Aggregate inbound demand into ranked signals.

    items: [{topic: str, price_ask: bool, quote_sent: bool}, ...]
    known_prices: topics the owner already has a listed price/package for.

    Returns {signals, all_signals, total_topics} where each signal is:
      {topic, display, mentions, price_asks, quotes_sent, unmet_quotes, missing_price}
    """
    known = {str(k).strip().lower() for k in (known_prices or [])}
    agg: dict[str, dict] = {}

    for it in items:
        topic = (it.get("topic") or "").strip().lower()
        if not topic:
            continue
        a = agg.setdefault(topic, {
            "topic": topic, "mentions": 0, "price_asks": 0, "quotes_sent": 0,
        })
        a["mentions"] += 1
        if it.get("price_ask"):
            a["price_asks"] += 1
        if it.get("quote_sent"):
            a["quotes_sent"] += 1

    signals = []
    for a in agg.values():
        a["unmet_quotes"] = max(0, a["price_asks"] - a["quotes_sent"])
        a["missing_price"] = (a["topic"] not in known) and a["price_asks"] > 0
        a["display"] = a["topic"].title()
        signals.append(a)

    # Rank: most price-asked first, then most-mentioned.
    signals.sort(key=lambda x: (x["price_asks"], x["mentions"]), reverse=True)
    ranked = [s for s in signals if s["mentions"] >= min_mentions]
    return {"signals": ranked[:top_n], "all_signals": signals, "total_topics": len(signals)}


def radar_headlines(radar: dict, top: int = 3) -> list[str]:
    """Owner-facing lines for the top demand signals — action-oriented."""
    out = []
    for s in radar.get("signals", [])[:top]:
        if s["missing_price"]:
            out.append(
                f"{s['price_asks']} people asked about {s['display']} this week — "
                f"you have no listed price. Post one and capture it.")
        elif s["unmet_quotes"] > 0:
            n = s["unmet_quotes"]
            out.append(
                f"{n} {s['display']} enquir{'y' if n == 1 else 'ies'} got no quote yet — follow up.")
        else:
            out.append(f"{s['mentions']} people asked about {s['display']} this week.")
    return out
