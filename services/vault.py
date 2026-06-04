"""
EYO Vault — per-customer memory surface (SPRINT 2 #6).

Surfaces what's already stored in services/client_memory.py as a CRM-style
view: one row per customer, with their accumulated facts (preferences,
spend, complaints, milestones) grouped + sorted by recency.

Switching cost from low -> structural. Once an owner sees that EYO knows
Funke prefers the DJ-booth table, books in groups of 6, last spent ₦450k
on a Saturday birthday, and is allergic to peppers — that data is the
relationship. Leaving = losing it.

Public
------
  list_customers(client_id, limit=200, search=None)
    -> [{contact_phone, contact_name, fact_count, last_seen_at,
         lifetime_ngn, top_fact}]
  get_customer(client_id, contact_phone)
    -> {contact_name, facts: [...], facts_by_type: {...}, lifetime_ngn,
        first_seen_at, last_seen_at, message_count}
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import structlog

from database import get_db
from services.client_memory import (
    _require_scope, get_memory_col, MemoryScopeViolationError,
)

log = structlog.get_logger()


# ─── List rollup ──────────────────────────────────────────────────────────────

def list_customers(
    client_id: str,
    *,
    limit: int = 200,
    search: Optional[str] = None,
) -> list[dict]:
    """One row per contact_phone. Aggregates facts to give the owner a
    sortable customer list. Scope-locked by client_id."""
    if not client_id:
        raise MemoryScopeViolationError("client_id required for vault listing")

    match: dict = {"client_id": str(client_id)}
    if search:
        s = re.escape(search.strip())
        match["$or"] = [
            {"contact_name":  {"$regex": s, "$options": "i"}},
            {"contact_phone": {"$regex": s, "$options": "i"}},
            {"fact_text":     {"$regex": s, "$options": "i"}},
        ]

    pipeline = [
        {"$match": match},
        {"$sort":  {"created_at": -1}},
        {"$group": {
            "_id":             "$contact_phone",
            "contact_name":    {"$first": "$contact_name"},
            "fact_count":      {"$sum": 1},
            "last_seen_at":    {"$max": "$created_at"},
            "first_seen_at":   {"$min": "$created_at"},
            "top_fact":        {"$first": "$fact_text"},
            "top_fact_type":   {"$first": "$fact_type"},
            "fact_texts":      {"$push": "$fact_text"},
        }},
        {"$sort":  {"last_seen_at": -1}},
        {"$limit": int(limit)},
    ]

    rows = list(get_memory_col().aggregate(pipeline))

    # Backfill lifetime spend from receipt_matches if available
    phones = [r["_id"] for r in rows if r.get("_id")]
    spend_by_phone: dict[str, int] = {}
    if phones:
        try:
            spend_pipe = [
                {"$match": {
                    "client_id":  str(client_id),
                    "from_phone": {"$in": phones},
                    "status":     "confirmed",
                }},
                {"$group": {"_id": "$from_phone", "ngn": {"$sum": "$amount_ngn"}}},
            ]
            for s in get_db()["receipt_matches"].aggregate(spend_pipe):
                spend_by_phone[s["_id"]] = int(s.get("ngn") or 0)
        except Exception:
            pass

    out = []
    for r in rows:
        phone = r["_id"]
        spend = spend_by_phone.get(phone, 0)
        all_text = " ".join((t or "").lower() for t in (r.get("fact_texts") or []))
        out.append({
            "contact_phone":  phone,
            "contact_name":   r.get("contact_name") or "—",
            "fact_count":     int(r.get("fact_count") or 0),
            "last_seen_at":   r.get("last_seen_at"),
            "first_seen_at":  r.get("first_seen_at"),
            "lifetime_ngn":   spend,
            "top_fact":       (r.get("top_fact") or "")[:160],
            "top_fact_type":  r.get("top_fact_type") or "context",
            "next_best_action": _nba_from_text(all_text, spend, r.get("last_seen_at")),
        })
    return out


# ─── Next best action (deterministic — no LLM call on a list view) ─────────────

_OCCASION_TOKENS = (
    "birthday", "anniversary", "wedding", "christmas", "detty december",
    "valentine", "graduation", "naming", "event", "party",
)


def next_best_action(facts_by_type: dict, lifetime_ngn: int, last_seen_at) -> str:
    """A single 'likely next best action' line from what EYO already knows.
    Cheap + deterministic so it can render on every Vault row."""
    all_text = " ".join(
        (f.get("fact_text") or "").lower()
        for fl in facts_by_type.values() for f in fl
    )
    return _nba_from_text(all_text, lifetime_ngn, last_seen_at)


def _nba_from_text(all_text: str, lifetime_ngn: int, last_seen_at) -> str:
    """Core NBA logic over a pre-joined (lowercased) text blob — so both the
    per-customer dossier and the list rollup can share it without an LLM call."""
    days_quiet = None
    if last_seen_at:
        try:
            if getattr(last_seen_at, "tzinfo", None) is None:
                last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
            days_quiet = (datetime.now(timezone.utc) - last_seen_at).days
        except Exception:
            days_quiet = None

    for tok in _OCCASION_TOKENS:
        if tok in all_text:
            return f"Send a tailored {tok} offer — they've shown interest before."
    if lifetime_ngn >= 100_000 and (days_quiet or 0) >= 30:
        return f"Re-engage: repeat buyer (~₦{lifetime_ngn:,.0f}) quiet {days_quiet} days — invite them back."
    if any(t in all_text for t in ("price", "quote", "how much", "cost")):
        return "Follow up on their pricing question with a clear quote + next step."
    if any(t in all_text for t in ("complain", "refund", "angry", "disappointed")):
        return "Check in warmly — past complaint on file; rebuild goodwill before selling."
    if days_quiet is not None and days_quiet >= 45:
        return f"Reach out — quiet {days_quiet} days. A simple 'we miss you' often reopens the door."
    return "Keep warm — share what's new or a small returning-customer perk."


# ─── Per-customer detail ──────────────────────────────────────────────────────

def get_customer(client_id: str, contact_phone: str) -> dict:
    """Full per-customer dossier: all facts grouped by type + spend + first/last seen."""
    cid, phone = _require_scope(client_id, contact_phone)

    rows = list(get_memory_col().find(
        {"client_id": cid, "contact_phone": phone}
    ).sort("created_at", -1))

    if not rows:
        return {"contact_name": "—", "contact_phone": phone, "facts": [],
                "facts_by_type": {}, "lifetime_ngn": 0,
                "first_seen_at": None, "last_seen_at": None, "fact_count": 0}

    facts_by_type: dict[str, list[dict]] = {}
    for r in rows:
        ft = r.get("fact_type", "context")
        facts_by_type.setdefault(ft, []).append({
            "fact_text":          r.get("fact_text", ""),
            "confidence":         r.get("confidence", 0.7),
            "created_at":         r.get("created_at"),
            "last_reinforced_at": r.get("last_reinforced_at"),
            "times_referenced":   r.get("times_referenced", 0),
            "source_excerpt":     r.get("source_excerpt"),
        })

    # Lifetime spend
    lifetime_ngn = 0
    try:
        for s in get_db()["receipt_matches"].aggregate([
            {"$match": {"client_id": cid, "from_phone": phone, "status": "confirmed"}},
            {"$group": {"_id": None, "ngn": {"$sum": "$amount_ngn"}}},
        ]):
            lifetime_ngn = int(s.get("ngn") or 0)
    except Exception:
        pass

    return {
        "contact_name":   rows[0].get("contact_name") or "—",
        "contact_phone":  phone,
        "fact_count":     len(rows),
        "first_seen_at":  rows[-1].get("created_at"),
        "last_seen_at":   rows[0].get("created_at"),
        "lifetime_ngn":   lifetime_ngn,
        "next_best_action": next_best_action(facts_by_type, lifetime_ngn, rows[0].get("created_at")),
        "facts_by_type":  facts_by_type,
        # Flat list for clients that prefer chronological
        "facts": [{
            "fact_type":    r.get("fact_type"),
            "fact_text":    r.get("fact_text"),
            "confidence":   r.get("confidence", 0.7),
            "created_at":   r.get("created_at"),
            "source_excerpt": r.get("source_excerpt"),
        } for r in rows],
    }
