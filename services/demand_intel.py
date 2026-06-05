"""Demand intelligence — capture, store, and assemble the EYO Radar.

Flow:
  inbound message ──(flag-gated, non-blocking)──> extract_demand()
        └─> record_demand_signal()  -> demand_signals collection
  portal / brief ──> radar_for_client() -> build_radar() ranked output

The extraction is pure (services/demand_extract). The ranking is the pure core
(services/demand_radar.build_radar). This module is the thin DB layer + the
non-blocking capture hook, flag-gated on the client's `radar` flag.

NOTE: quote_sent isn't tracked yet (we don't yet attribute outbound quotes back
to a demand topic), so items carry quote_sent=False. Radar therefore reports
demand + price-asks honestly; "did we quote them" attribution is a follow-up.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

from services.demand_extract import extract_demand
from services.demand_radar import build_radar
from services.eyo_flags import eyo_enabled

log = structlog.get_logger()


def _col():
    from database import get_db
    return get_db()["demand_signals"]


def ensure_demand_indexes() -> None:
    _col().create_index([("client_name", 1), ("created_at", -1)])


def record_demand_signal(client_name: str, contact_phone: str,
                         topic: str, price_ask: bool) -> None:
    _col().insert_one({
        "client_name":   client_name,
        "contact_phone": contact_phone,
        "topic":         topic,
        "price_ask":     bool(price_ask),
        "created_at":    datetime.now(timezone.utc),
    })


def demand_items_for(client_name: str, days: int = 30) -> list[dict]:
    """Shape stored signals into the items build_radar() expects."""
    if not client_name:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = _col().find(
        {"client_name": client_name, "created_at": {"$gte": since}},
        {"topic": 1, "price_ask": 1},
    )
    return [
        {"topic": r.get("topic"), "price_ask": bool(r.get("price_ask")), "quote_sent": False}
        for r in rows if r.get("topic")
    ]


def radar_for_client(client_name: str, *, days: int = 30,
                     min_mentions: int = 3, top_n: int = 5) -> dict:
    """Assemble the ranked demand radar for one client from captured signals."""
    items = demand_items_for(client_name, days=days)
    return build_radar(items, min_mentions=min_mentions, top_n=top_n)


def maybe_capture_demand(client_doc: Optional[dict], body_text: str,
                         contact_phone: str) -> bool:
    """Best-effort, flag-gated capture from one inbound. Returns True if a
    signal was stored. Never raises — must not break inbound handling."""
    try:
        if not client_doc or not body_text or body_text.startswith("[Image received"):
            return False
        cname = client_doc.get("name")
        if not cname or not eyo_enabled(cname, "radar"):
            return False
        sig = extract_demand(body_text)
        if not sig:
            return False
        record_demand_signal(cname, contact_phone, sig["topic"], sig["price_ask"])
        log.info("demand_signal_captured", client=cname, price_ask=sig["price_ask"])
        return True
    except Exception as e:
        log.warning("demand_capture_failed", error=str(e))
        return False
