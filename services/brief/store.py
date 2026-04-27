"""
BusinessBrief + VerticalPrimer — schema, persistence, completeness gate.

Storage:
  - business_brief lives on the client doc as `clients.business_brief`
  - vertical_primers is its own collection, keyed by `vertical`
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from pymongo import ASCENDING
from pydantic import BaseModel, Field

from database import get_db


# ─── Models ───────────────────────────────────────────────────────────────────

class VerticalPrimer(BaseModel):
    """Industry defaults the AI uses when a client hasn't filled their own brief.

    A primer captures what is true *about the industry as a whole* in Nigeria —
    vocabulary, tone, common objections, regulatory notes. Client briefs override
    on conflict, so primers should be sensible defaults, not aggressive defaults.
    """
    vertical: str
    label: str = ""
    vocabulary: list[str] = []                  # industry-specific terms the AI may use
    default_tone: str = "warm-professional"
    default_qualifying_questions: list[str] = []
    default_objections: list[str] = []           # objections the AI should be ready to handle
    default_cta: str = ""                        # e.g. "book a viewing", "book a free trial class"
    compliance_notes: list[str] = []             # legal/regulatory rails for this industry
    never_say_defaults: list[str] = []           # phrases banned by industry norms
    sample_one_liner: str = ""                   # placeholder shown in the brief form
    updated_at: Optional[datetime] = None


class BusinessBrief(BaseModel):
    """Per-client brief that overrides the vertical primer.

    Every field is optional; the merger fills gaps from the primer at runtime.
    Closer's existing CloserBrief is a strict subset — when a client has both,
    business_brief wins, closer_brief is read as a fallback for back-compat.
    """
    # Identity
    trading_name: str = ""
    one_liner: str = ""
    founder_story: str = ""
    geography: list[str] = []                    # cities/areas they operate in

    # What they sell
    products: list[dict] = []                    # [{name, price_ngn_min, price_ngn_max, notes}]
    usps: list[str] = []                         # unique selling points
    social_proof: list[str] = []                 # past wins, named or anonymised

    # Who they want
    icp: str = ""                                # ideal client profile
    not_a_fit: str = ""                          # disqualifiers

    # How they sound
    tone_overrides: str = ""                     # blank = use primer default
    signature: str = ""                          # message sign-off
    language_mix: list[str] = ["english"]

    # Hard rules
    never_say: list[str] = []
    always_say: list[str] = []
    red_flags: list[str] = []                    # signals to disqualify a lead fast

    # Selling motions
    qualifying_questions: list[str] = []
    objection_responses: dict[str, str] = {}     # {"too expensive": "let me show you..."}
    closing_action: str = ""                     # what counts as "ready"
    pricing_rules: str = ""                      # bands, negotiation limits

    # Reference assets
    brochure_url: str = ""
    calendar_link: str = ""
    payment_terms: str = ""

    # Meta
    updated_at: Optional[datetime] = None
    intake_source: str = "manual"                # "manual" | "ai_assisted" | "imported"


# ─── Collections ──────────────────────────────────────────────────────────────

def _primers():
    return get_db()["vertical_primers"]


def _clients():
    return get_db()["clients"]


def ensure_brief_indexes() -> None:
    _primers().create_index([("vertical", ASCENDING)], unique=True)


# ─── Vertical primer CRUD ────────────────────────────────────────────────────

def get_primer(vertical: str) -> Optional[dict]:
    return _primers().find_one({"vertical": vertical})


def list_primers() -> list[dict]:
    return list(_primers().find().sort("vertical", ASCENDING))


def upsert_primer(primer: VerticalPrimer) -> dict:
    now = datetime.now(timezone.utc)
    payload = primer.model_dump()
    payload["updated_at"] = now
    res = _primers().update_one(
        {"vertical": primer.vertical},
        {"$set": payload},
        upsert=True,
    )
    return {"matched": res.matched_count, "modified": res.modified_count, "upserted": res.upserted_id is not None}


# ─── Business brief CRUD (lives on client doc) ───────────────────────────────

def _client_query(client_id: Optional[str] = None, client_name: Optional[str] = None) -> dict:
    if client_id:
        return {"_id": ObjectId(client_id)}
    if client_name:
        import re as _re
        return {"name": {"$regex": f"^{_re.escape(client_name)}$", "$options": "i"}}
    raise ValueError("client_id or client_name required")


def get_brief(*, client_id: Optional[str] = None, client_name: Optional[str] = None) -> Optional[dict]:
    """Return the client doc's business_brief, or None if unset."""
    doc = _clients().find_one(_client_query(client_id, client_name), {"business_brief": 1, "vertical": 1, "name": 1, "closer_brief": 1})
    if not doc:
        return None
    return {
        "client_id": str(doc["_id"]),
        "client_name": doc.get("name"),
        "vertical": doc.get("vertical"),
        "business_brief": doc.get("business_brief") or {},
        "closer_brief": doc.get("closer_brief") or {},  # legacy fallback for back-compat
    }


def update_brief(
    *,
    brief: BusinessBrief,
    client_id: Optional[str] = None,
    client_name: Optional[str] = None,
) -> dict:
    now = datetime.now(timezone.utc)
    payload = brief.model_dump()
    payload["updated_at"] = now
    res = _clients().update_one(
        _client_query(client_id, client_name),
        {"$set": {"business_brief": payload, "updated_at": now}},
    )
    return {"matched": res.matched_count, "modified": res.modified_count}


# ─── Completeness gate ───────────────────────────────────────────────────────

# Fields that contribute to brief health score. Weights add up to 10.
_HEALTH_FIELDS: list[tuple[str, int, str]] = [
    ("trading_name",          1, "trading name"),
    ("one_liner",             1, "one-line description"),
    ("icp",                   2, "ideal client profile"),
    ("products",              1, "products / services"),
    ("usps",                  1, "unique selling points"),
    ("qualifying_questions",  1, "qualifying questions"),
    ("closing_action",        1, "closing action"),
    ("never_say",             1, "never-say list"),
    ("signature",             1, "signature / sign-off"),
]

# Fields that — if missing — block sending entirely.
_HEALTH_BLOCKERS: list[str] = ["icp", "closing_action"]


def brief_health(*, client_id: Optional[str] = None, client_name: Optional[str] = None) -> dict:
    """Score the brief completeness 0–10, surface what's missing, flag blockers.

    Caller can use `blockers` as a hard send-gate, `score` to surface a badge,
    `missing` to drive a "complete your brief" nudge in the UI.
    """
    info = get_brief(client_id=client_id, client_name=client_name)
    if not info:
        return {"score": 0, "missing": [f for _, _, f in _HEALTH_FIELDS], "blockers": _HEALTH_BLOCKERS, "exists": False}

    brief = info.get("business_brief") or {}
    legacy = info.get("closer_brief") or {}

    # Closer back-compat — if a closer_brief field has content, count it.
    legacy_map = {
        "icp": legacy.get("icp"),
        "qualifying_questions": legacy.get("qualifying_questions"),
        "closing_action": legacy.get("closing_action"),
        "never_say": legacy.get("never_say"),
        "products": [{"name": legacy.get("product")}] if legacy.get("product") else None,
    }

    score = 0
    missing: list[str] = []
    for key, weight, label in _HEALTH_FIELDS:
        value = brief.get(key) or legacy_map.get(key)
        if _has_content(value):
            score += weight
        else:
            missing.append(label)

    blockers: list[str] = []
    for key in _HEALTH_BLOCKERS:
        value = brief.get(key) or legacy_map.get(key)
        if not _has_content(value):
            blockers.append(key)

    return {
        "score": score,
        "max": 10,
        "missing": missing,
        "blockers": blockers,
        "exists": True,
    }


def _has_content(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True
