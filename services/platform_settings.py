"""
Platform Settings — single-source-of-truth for runtime-tunable global settings.

The first surface is pricing: today the three plan tier amounts live as a
hardcoded dict in `api/marketing.py::PLAN_PRICING`. Changing them requires a
deploy. With this service they live in a Mongo doc and the operator can edit
them from the Control Tower → Settings tab.

Same pattern is reusable for any future global setting (overage rates, daily
caps, drift thresholds, etc.) so the operator never has to redeploy for a
config tweak.

Storage
-------
One doc per setting in collection `platform_settings`:
    {_id: ObjectId, key: "pricing", value: {...}, updated_at, updated_by, audit: [...]}

Every write appends to `audit` (last 50 entries) so we can see who changed
what and when.

Pricing schema
--------------
    {"starter": {"label": str, "ngn": int},
     "growth":  {"label": str, "ngn": int},
     "scale":   {"label": str, "ngn": int}}
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from pymongo import ASCENDING

from database import get_db

log = structlog.get_logger()


# ─── Defaults (fallback when no doc exists) ───────────────────────────────────

DEFAULT_PRICING = {
    "starter": {"label": "Starter", "ngn": 80_000},
    "growth":  {"label": "Growth",  "ngn": 150_000},
    "scale":   {"label": "Scale",   "ngn": 300_000},
}


# ─── Collection ───────────────────────────────────────────────────────────────

def _col():
    return get_db()["platform_settings"]


def ensure_settings_indexes() -> None:
    _col().create_index([("key", ASCENDING)], unique=True)


# ─── Generic read / write ─────────────────────────────────────────────────────

def get_setting(key: str, default: Any = None) -> Any:
    doc = _col().find_one({"key": key})
    if not doc:
        return default
    return doc.get("value", default)


def set_setting(key: str, value: Any, *, updated_by: str = "admin") -> dict:
    now = datetime.now(timezone.utc)
    audit_entry = {"at": now, "by": updated_by, "value": value}
    _col().update_one(
        {"key": key},
        {"$set":  {"value": value, "updated_at": now, "updated_by": updated_by},
         "$push": {"audit": {"$each": [audit_entry], "$slice": -50}}},
        upsert=True,
    )
    log.info("platform_setting_changed", key=key, by=updated_by)
    return {"key": key, "value": value, "updated_at": now.isoformat()}


# ─── Pricing-specific helpers ─────────────────────────────────────────────────

def get_plan_pricing() -> dict:
    """Returns the live pricing dict, falling back to DEFAULT_PRICING."""
    val = get_setting("pricing", DEFAULT_PRICING)
    # Validate shape — fall back if corrupted
    if not isinstance(val, dict) or not all(k in val for k in ("starter", "growth", "scale")):
        return DEFAULT_PRICING
    for plan in ("starter", "growth", "scale"):
        entry = val.get(plan) or {}
        if not isinstance(entry.get("ngn"), int) or entry["ngn"] <= 0:
            return DEFAULT_PRICING
    return val


def set_plan_pricing(pricing: dict, *, updated_by: str = "admin") -> dict:
    """Validate + persist a new pricing dict."""
    # Normalise + validate
    cleaned: dict = {}
    for plan in ("starter", "growth", "scale"):
        entry = (pricing or {}).get(plan) or {}
        label = (entry.get("label") or plan.title()).strip()[:32]
        try:
            ngn = int(entry.get("ngn"))
        except (TypeError, ValueError):
            raise ValueError(f"invalid ngn for {plan}")
        if not (1_000 <= ngn <= 10_000_000):
            raise ValueError(f"{plan} ngn out of range (1,000–10,000,000)")
        cleaned[plan] = {"label": label, "ngn": ngn}
    return set_setting("pricing", cleaned, updated_by=updated_by)


def get_pricing_audit(limit: int = 20) -> list[dict]:
    doc = _col().find_one({"key": "pricing"}, {"audit": 1})
    if not doc:
        return []
    audit = doc.get("audit") or []
    return list(reversed(audit[-limit:]))
