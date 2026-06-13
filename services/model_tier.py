"""
Per-plan model tiering — the client's plan chooses the brain.

The smarter (more expensive) the model, the better EYO drafts in the owner's
voice. Rather than eat that cost ourselves, we make it a **tier feature**: the
plan price carries the model cost with margin, and clients who want the sharper
brain choose the higher plan. See docs/MODEL_ECONOMICS.md for the numbers.

Founder pricing (locked first cohort):
  Solo  ₦60k  → starter → Haiku 4.5   (fast, capable; the baseline brain)
  Team  ₦120k → growth  → Sonnet 4.6  (sharper voice, better judgement)
  Empire ₦250k → agency → Opus 4.8    (the strongest writer)

One resolver, keyed by the client's plan (with an optional per-client override),
so a drafting call site never hardcodes a model again. Fail-safe: any lookup
failure or unknown plan falls back to Haiku — we never accidentally bill a
client for a pricier model they didn't buy.
"""
from __future__ import annotations

import re
from typing import Optional

import structlog

from database import get_db

log = structlog.get_logger()

# Canonical model IDs.
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-8"

_VALID = {HAIKU, SONNET, OPUS}

# Plan slug → brain. The plan price covers this model's cost with margin at the
# plan's expected message volume (docs/MODEL_ECONOMICS.md).
_PLAN_BRAIN: dict[str, str] = {
    "starter": HAIKU,    # Solo ₦60k
    "growth": SONNET,    # Team ₦120k
    "agency": OPUS,      # Empire ₦250k
    # Higher historical tiers, if ever used, get the top brain.
    "national": OPUS,
    "international": OPUS,
}

# Human-facing label for the brain, for the dashboard/portal.
_BRAIN_LABEL = {HAIKU: "Haiku 4.5", SONNET: "Sonnet 4.6", OPUS: "Opus 4.8"}


def brain_label(model: str) -> str:
    return _BRAIN_LABEL.get(model, model)


def model_for(client_name: Optional[str], *, default: str = HAIKU) -> str:
    """Resolve the drafting model from the client's plan.

    Precedence: explicit per-client `model_tier` override → plan mapping →
    `default`. Always returns a valid model ID; never raises."""
    if not client_name:
        return default
    try:
        doc = get_db()["clients"].find_one(
            {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}},
            {"plan": 1, "model_tier": 1},
        ) or {}
    except Exception as e:
        log.warning("model_tier_lookup_failed", error=str(e))
        return default

    # Per-client override — lets the founder bump a specific VIP without
    # changing their plan. Accepts a model ID or a tier slug.
    override = doc.get("model_tier")
    if override in _VALID:
        return override
    if override in _PLAN_BRAIN:
        return _PLAN_BRAIN[override]

    plan = (doc.get("plan") or "").strip().lower()
    return _PLAN_BRAIN.get(plan, default)


def plan_brain_table() -> dict[str, str]:
    """{plan_slug: model_id} — for the pricing/economics surfaces."""
    return dict(_PLAN_BRAIN)
