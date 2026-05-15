"""
Client Rules Engine — plain-English IF-THEN behaviour overrides per client.

Examples
--------
  • "If someone asks about refunds, offer 50% within 7 days, 25% within 14, none after."
  • "Never quote prices on weekends without my approval — always escalate to me."
  • "For diaspora numbers (UK/US area codes), include £/$ alongside ₦."
  • "If the word 'wedding' appears, switch to the bridal package response."

Rules are matched against each inbound message and compiled into a prompt
addendum that the drafter sees as part of its instructions. Rules can also
mark a draft for owner escalation, surfacing it in the HITL queue with a flag.

Scope rule (P0): every read/write requires a non-empty `client_id`. Calls with
no client_id raise `RulesScopeViolationError`. No cross-client rule bleed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Errors ───────────────────────────────────────────────────────────────────

class RulesScopeViolationError(Exception):
    """P0 — refuses any rules op without a client_id."""


# ─── Collections ──────────────────────────────────────────────────────────────

def get_rules_col():
    return get_db()["client_rules"]


def ensure_rules_indexes() -> None:
    col = get_rules_col()
    col.create_index([("client_id", ASCENDING), ("active", ASCENDING)])
    col.create_index([("client_id", ASCENDING), ("created_at", DESCENDING)])
    col.create_index([("client_id", ASCENDING), ("source_scenario", ASCENDING)])


# ─── Scope guard ──────────────────────────────────────────────────────────────

def _require_scope(client_id: Optional[str]) -> str:
    if not client_id or not str(client_id).strip():
        raise RulesScopeViolationError(
            "client_rules access attempted without client_id — P0 violation"
        )
    return str(client_id).strip()


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def add_rule(
    client_id: str,
    *,
    name: str,
    behavior_text: str,
    trigger_keywords: Optional[list[str]] = None,
    trigger_intent: Optional[str] = None,
    escalate_to_owner: bool = False,
    source_scenario: Optional[str] = None,
) -> str:
    """Persist one rule. Returns the inserted _id. Scope-locked."""
    cid = _require_scope(client_id)
    if not (behavior_text or "").strip():
        raise ValueError("rule.behavior_text required")
    kws = [k.strip().lower() for k in (trigger_keywords or []) if (k or "").strip()][:24]
    doc = {
        "client_id":         cid,
        "name":              (name or "Unnamed rule").strip()[:120],
        "behavior_text":     behavior_text.strip()[:1200],
        "trigger_keywords":  kws,
        "trigger_intent":    (trigger_intent or "").strip().lower() or None,
        "escalate_to_owner": bool(escalate_to_owner),
        "source_scenario":   source_scenario,
        "active":            True,
        "fire_count":        0,
        "created_at":        datetime.now(timezone.utc),
        "last_fired_at":     None,
    }
    return str(get_rules_col().insert_one(doc).inserted_id)


def list_rules(client_id: str, *, only_active: bool = False, limit: int = 200) -> list[dict]:
    cid = _require_scope(client_id)
    q: dict = {"client_id": cid}
    if only_active:
        q["active"] = True
    rules = list(get_rules_col().find(q).sort("created_at", -1).limit(limit))
    for r in rules:
        r["_id"] = str(r["_id"])
    return rules


def update_rule(client_id: str, rule_id: str, **changes) -> int:
    cid = _require_scope(client_id)
    try:
        oid = ObjectId(rule_id)
    except Exception:
        return 0
    allowed = {"name", "behavior_text", "trigger_keywords", "trigger_intent",
               "escalate_to_owner", "active"}
    patch = {k: v for k, v in changes.items() if k in allowed}
    if "trigger_keywords" in patch and patch["trigger_keywords"] is not None:
        patch["trigger_keywords"] = [k.strip().lower() for k in patch["trigger_keywords"] if (k or "").strip()]
    if not patch:
        return 0
    return get_rules_col().update_one(
        {"_id": oid, "client_id": cid}, {"$set": patch},
    ).modified_count


def delete_rule(client_id: str, rule_id: str) -> int:
    cid = _require_scope(client_id)
    try:
        oid = ObjectId(rule_id)
    except Exception:
        return 0
    return get_rules_col().delete_one({"_id": oid, "client_id": cid}).deleted_count


# ─── Matching ─────────────────────────────────────────────────────────────────

@dataclass
class RuleHit:
    rule_id: str
    name: str
    behavior_text: str
    escalate_to_owner: bool


def match_rules(client_id: str, inbound_text: str, intent: Optional[str] = None) -> list[RuleHit]:
    """Return all active rules whose triggers match the inbound. Scope-locked.

    A rule matches if EITHER:
      • any trigger_keyword appears (case-insensitive substring) in inbound, OR
      • trigger_intent equals the supplied intent.

    Rules with no triggers at all are treated as ALWAYS-ON guardrails.
    """
    cid = _require_scope(client_id)
    text_lc = (inbound_text or "").lower()
    intent_lc = (intent or "").lower().strip() or None

    cursor = get_rules_col().find({"client_id": cid, "active": True})
    hits: list[RuleHit] = []
    fired_ids: list[ObjectId] = []
    for r in cursor:
        kws = r.get("trigger_keywords") or []
        rintent = r.get("trigger_intent")
        always_on = not kws and not rintent
        matched = always_on
        if not matched and kws:
            matched = any(k in text_lc for k in kws)
        if not matched and rintent and intent_lc:
            matched = (rintent == intent_lc)
        if matched:
            hits.append(RuleHit(
                rule_id=str(r["_id"]),
                name=r.get("name", ""),
                behavior_text=r.get("behavior_text", ""),
                escalate_to_owner=bool(r.get("escalate_to_owner")),
            ))
            fired_ids.append(r["_id"])

    if fired_ids:
        try:
            get_rules_col().update_many(
                {"_id": {"$in": fired_ids}},
                {"$inc": {"fire_count": 1},
                 "$set": {"last_fired_at": datetime.now(timezone.utc)}},
            )
        except Exception:
            pass
    return hits


# ─── Prompt compilation ───────────────────────────────────────────────────────

def fetch_rules_block(client_id: str, inbound_text: str, intent: Optional[str] = None) -> tuple[str, bool]:
    """Return (prompt_addendum, escalate_flag). Both empty/False if no rules fire."""
    if not client_id:
        return "", False
    try:
        hits = match_rules(client_id, inbound_text, intent)
    except RulesScopeViolationError:
        return "", False
    except Exception as e:
        log.warning("rules_match_failed", error=str(e))
        return "", False
    if not hits:
        return "", False
    lines = ["ACTIVE RULES — these instructions OVERRIDE the default playbook. Follow them exactly:"]
    for h in hits:
        lines.append(f"  • {h.behavior_text}")
    block = "\n".join(lines)
    escalate = any(h.escalate_to_owner for h in hits)
    return block, escalate
