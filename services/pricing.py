"""Per-client product pricing — the structured source Haggle negotiates against.

Each product carries a public `list_price` and a SECRET `floor_price` the customer
never sees, plus allowed `sweeteners`. Matched to an inbound message by normalized
topic (reusing demand_extract.normalize_topic) so "2 bedroom" / "2-bedroom" /
"2 bedrooms" all resolve to the same rule.

Scoped strictly by client_name. The floor never leaves this layer except into the
negotiation core.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from services.demand_extract import normalize_topic

log = structlog.get_logger()


def _col():
    from database import get_db
    return get_db()["client_pricing"]


def ensure_pricing_indexes() -> None:
    _col().create_index([("client_name", 1), ("product_key", 1)], unique=True)


def _key(product: str) -> str:
    return normalize_topic(product) or (product or "").strip().lower()


def set_pricing(client_name: str, product: str, list_price_ngn: float,
                floor_price_ngn: float, sweeteners: Optional[list] = None,
                max_rounds: int = 3) -> str:
    """Upsert a product's pricing rule. Returns the normalized product key."""
    key = _key(product)
    _col().update_one(
        {"client_name": client_name, "product_key": key},
        {"$set": {
            "client_name":    client_name,
            "product_key":    key,
            "product":        product,
            "list_price_ngn":  float(list_price_ngn),
            "floor_price_ngn": float(floor_price_ngn),
            "sweeteners":      list(sweeteners or []),
            "max_rounds":      int(max_rounds),
            "updated_at":      datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return key


def list_pricing(client_name: str) -> list[dict]:
    if not client_name:
        return []
    return list(_col().find({"client_name": client_name}, {"_id": 0}))


def get_pricing(client_name: str, topic: str) -> Optional[dict]:
    """The negotiation rules for the product a message is about, or None.

    Returns the shape services.haggle.negotiate() expects, plus product metadata.
    """
    if not client_name:
        return None
    key = _key(topic)
    if not key:
        return None
    doc = _col().find_one({"client_name": client_name, "product_key": key}, {"_id": 0})
    if not doc:
        return None
    return {
        "list_price":  doc.get("list_price_ngn"),
        "floor_price": doc.get("floor_price_ngn"),
        "sweeteners":  doc.get("sweeteners") or [],
        "max_rounds":  int(doc.get("max_rounds") or 3),
        "product":     doc.get("product"),
        "product_key": key,
    }
