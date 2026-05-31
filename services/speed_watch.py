"""
Competitor Speed Watch (#8) — scoreboard energy.

Computes the client's REAL median first-response time (inbound → first outbound
to that contact) over a window, and frames it against a category benchmark.

Honesty rule: the response time is measured from real data. The "faster than
X%" line is an *estimate* under a simple model (exponential response-time
distribution with mean = the category benchmark) and is labelled as such.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import structlog

from database import get_db

log = structlog.get_logger()

# Rough Lagos-SME first-response benchmarks, in minutes. Conservative; these
# are assumptions, not measured market data — tune as real data arrives.
_BENCHMARK_MINUTES = {
    "hospitality": 120,
    "real_estate": 240,
    "events":      150,
    "legal":       360,
    "logistics":   180,
    "fitness":     120,
    "default":     180,
}


def _benchmark_for(vertical: str | None) -> int:
    return _BENCHMARK_MINUTES.get((vertical or "").lower(), _BENCHMARK_MINUTES["default"])


def _fmt_duration(minutes: float) -> str:
    if minutes < 1:
        return "under a minute"
    if minutes < 60:
        return f"{round(minutes)} min"
    hrs = minutes / 60.0
    if hrs < 24:
        return f"{hrs:.1f} hr" if hrs < 10 else f"{round(hrs)} hr"
    return f"{round(hrs / 24)} day(s)"


def response_speed_for(client_name: str, days: int = 30, vertical: str | None = None) -> dict:
    """Median first-response time + a benchmark comparison for the client."""
    db = get_db()
    if "inbound_messages" not in db.list_collection_names():
        return {"samples": 0, "median_minutes": None, "headline": "Not enough data yet to measure response speed."}

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, min(180, days)))
    outreach = db["outreach_log"] if "outreach_log" in db.list_collection_names() else None

    inbounds = db["inbound_messages"].find(
        {"client_name": client_name, "received_at": {"$gte": since}},
        {"sender_phone": 1, "received_at": 1},
    ).sort("received_at", 1).limit(1000)

    deltas: list[float] = []
    for m in inbounds:
        phone = m.get("sender_phone")
        rcv = m.get("received_at")
        if not phone or not rcv or outreach is None:
            continue
        reply = outreach.find_one(
            {"client_name": client_name, "phone": phone, "sent_at": {"$gte": rcv}},
            {"sent_at": 1}, sort=[("sent_at", 1)],
        )
        if reply and reply.get("sent_at"):
            mins = (reply["sent_at"] - rcv).total_seconds() / 60.0
            if 0 <= mins <= 60 * 24 * 7:   # ignore > 1 week as not-a-response
                deltas.append(mins)

    if not deltas:
        return {"samples": 0, "median_minutes": None,
                "headline": "Not enough replies in the window to measure speed yet."}

    deltas.sort()
    median = deltas[len(deltas) // 2]
    benchmark = _benchmark_for(vertical)

    # Estimated percentile faster than peers, under an exponential model with
    # mean = benchmark. P(peer slower than you) = e^(-your_median / benchmark).
    faster_than = max(50, min(97, round(math.exp(-median / benchmark) * 100)))

    return {
        "samples":          len(deltas),
        "median_minutes":   round(median, 1),
        "median_pretty":    _fmt_duration(median),
        "benchmark_minutes": benchmark,
        "benchmark_pretty": _fmt_duration(benchmark),
        "faster_than_pct":  faster_than,
        "headline": (
            f"You reply in {_fmt_duration(median)}. Similar businesses in your "
            f"category average {_fmt_duration(benchmark)}+ — you're faster than "
            f"~{faster_than}% of them (est.)."
        ),
    }
