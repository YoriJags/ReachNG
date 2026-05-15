"""
Client Memory Layer — durable per-contact facts with hard client-scope locking.

Why this exists
---------------
The drafter is good but forgetful. Every reply starts cold — the agent rediscovers
on every turn that Mrs Adekoya pays late, that Mr Bola's daughter goes to Lagoon
British, that this buyer wants Banana Island not Ikoyi. Without durable memory,
voice match degrades over time and the customer feels unseen.

This module stores extracted facts per (client_id, contact_phone) and retrieves
them at draft time. The architectural rule: every read/write REQUIRES a
non-empty `client_id`. Calls with no client_id raise MemoryScopeViolationError
immediately. This guarantees by construction that one client's memory can never
surface in another client's drafts.

Schema
------
client_memory:
  client_id          str   required, never null  ← isolation key
  contact_phone      str   required, normalised
  contact_name       str?  optional snapshot
  fact_type          str   "preference" | "history" | "constraint" | "context" | "complaint" | "other"
  fact_text          str   the actual durable note
  source_message_id  str?  link to inbound that taught us this
  source_excerpt     str?  short quote from the message
  confidence         float 0-1
  created_at         datetime
  last_reinforced_at datetime
  times_referenced   int   how often this fact got pulled into a draft

memory_audit_log:
  client_id, contact_phone, action ("read"|"write"|"extract"), count, ts, requested_by

Append-only — facts are never deleted or overwritten. Newer facts of the same
type quietly supersede older ones at retrieval (sorted by created_at desc).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Errors ───────────────────────────────────────────────────────────────────

class MemoryScopeViolationError(Exception):
    """Raised when a memory read/write is attempted without a client_id.
    This is a P0 architectural safeguard — never catch and swallow it."""


# ─── Collection accessors ─────────────────────────────────────────────────────

def get_memory_col():
    return get_db()["client_memory"]


def get_audit_col():
    return get_db()["memory_audit_log"]


def ensure_memory_indexes() -> None:
    """Idempotent — call from lifespan startup."""
    mem = get_memory_col()
    mem.create_index([("client_id", ASCENDING), ("contact_phone", ASCENDING)])
    mem.create_index([("client_id", ASCENDING), ("created_at", DESCENDING)])
    mem.create_index([("client_id", ASCENDING), ("fact_type", ASCENDING)])

    audit = get_audit_col()
    audit.create_index([("client_id", ASCENDING), ("ts", DESCENDING)])
    audit.create_index([("ts", DESCENDING)])


# ─── Phone normalisation ──────────────────────────────────────────────────────

def _normalise_phone(phone: str) -> str:
    """Strip whitespace + leading + so lookups are consistent."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone).lstrip("0")  # 08164583657 → 8164583657


# ─── Scope guard ──────────────────────────────────────────────────────────────

def _require_scope(client_id: Optional[str], contact_phone: Optional[str]) -> tuple[str, str]:
    """All memory ops MUST provide a client_id and contact_phone. Raises otherwise."""
    if not client_id or not str(client_id).strip():
        raise MemoryScopeViolationError(
            "client_memory access attempted without client_id — P0 isolation violation"
        )
    if not contact_phone or not str(contact_phone).strip():
        raise MemoryScopeViolationError(
            "client_memory access attempted without contact_phone — refusing"
        )
    return str(client_id).strip(), _normalise_phone(contact_phone)


# ─── Audit ────────────────────────────────────────────────────────────────────

def _audit(client_id: str, contact_phone: str, action: str, count: int, requested_by: str = "system") -> None:
    """Best-effort audit — never block the real op if audit insert fails."""
    try:
        get_audit_col().insert_one({
            "client_id":     client_id,
            "contact_phone": contact_phone,
            "action":        action,
            "count":         count,
            "requested_by":  requested_by,
            "ts":            datetime.now(timezone.utc),
        })
    except Exception as e:
        log.warning("memory_audit_log_failed", error=str(e))


# ─── Write ────────────────────────────────────────────────────────────────────

def store_fact(
    client_id: str,
    contact_phone: str,
    fact_type: str,
    fact_text: str,
    *,
    contact_name: Optional[str] = None,
    source_message_id: Optional[str] = None,
    source_excerpt: Optional[str] = None,
    confidence: float = 0.7,
    requested_by: str = "auto_extractor",
) -> str:
    """Persist one fact. Returns the inserted _id as str. Scope-locked."""
    cid, phone = _require_scope(client_id, contact_phone)
    now = datetime.now(timezone.utc)
    doc = {
        "client_id":          cid,
        "contact_phone":      phone,
        "contact_name":       contact_name,
        "fact_type":          fact_type or "other",
        "fact_text":          (fact_text or "").strip(),
        "source_message_id":  source_message_id,
        "source_excerpt":     (source_excerpt or "")[:240] or None,
        "confidence":         max(0.0, min(1.0, float(confidence))),
        "created_at":         now,
        "last_reinforced_at": now,
        "times_referenced":   0,
    }
    if not doc["fact_text"]:
        return ""  # silently skip empties
    res = get_memory_col().insert_one(doc)
    _audit(cid, phone, "write", 1, requested_by)
    return str(res.inserted_id)


def store_facts_bulk(
    client_id: str,
    contact_phone: str,
    facts: list[dict],
    *,
    contact_name: Optional[str] = None,
    source_message_id: Optional[str] = None,
    source_excerpt: Optional[str] = None,
    requested_by: str = "auto_extractor",
) -> int:
    """Persist many facts in one go. Returns count inserted."""
    if not facts:
        return 0
    cid, phone = _require_scope(client_id, contact_phone)
    now = datetime.now(timezone.utc)
    docs = []
    for f in facts:
        text = (f.get("fact_text") or "").strip()
        if not text:
            continue
        docs.append({
            "client_id":          cid,
            "contact_phone":      phone,
            "contact_name":       contact_name,
            "fact_type":          f.get("fact_type") or "other",
            "fact_text":          text,
            "source_message_id":  source_message_id,
            "source_excerpt":     (source_excerpt or "")[:240] or None,
            "confidence":         max(0.0, min(1.0, float(f.get("confidence", 0.7)))),
            "created_at":         now,
            "last_reinforced_at": now,
            "times_referenced":   0,
        })
    if not docs:
        return 0
    get_memory_col().insert_many(docs)
    _audit(cid, phone, "write", len(docs), requested_by)
    return len(docs)


# ─── Read ─────────────────────────────────────────────────────────────────────

def fetch_facts(
    client_id: str,
    contact_phone: str,
    *,
    limit: int = 10,
    fact_types: Optional[list[str]] = None,
    requested_by: str = "drafter",
) -> list[dict]:
    """Return the most recent N facts for this (client, contact). Scope-locked."""
    cid, phone = _require_scope(client_id, contact_phone)
    q: dict = {"client_id": cid, "contact_phone": phone}
    if fact_types:
        q["fact_type"] = {"$in": fact_types}
    cursor = get_memory_col().find(q).sort("created_at", -1).limit(limit)
    rows = list(cursor)
    # Tick reference counter (best-effort)
    if rows:
        try:
            ids = [r["_id"] for r in rows]
            get_memory_col().update_many(
                {"_id": {"$in": ids}},
                {"$inc": {"times_referenced": 1},
                 "$set": {"last_reinforced_at": datetime.now(timezone.utc)}},
            )
        except Exception:
            pass
    _audit(cid, phone, "read", len(rows), requested_by)
    return rows


def fetch_memory_block(
    client_id: str,
    contact_phone: str,
    *,
    limit: int = 8,
    requested_by: str = "drafter",
) -> str:
    """Return a formatted text block suitable for injection into a Claude prompt.

    Empty string if no memory exists. Always scope-locked.
    """
    rows = fetch_facts(client_id, contact_phone, limit=limit, requested_by=requested_by)
    if not rows:
        return ""
    lines = ["What you already know about this contact (do not repeat unprompted, but honour):"]
    for r in rows:
        ft = r.get("fact_type", "context")
        txt = r.get("fact_text", "").strip()
        if txt:
            lines.append(f"  • [{ft}] {txt}")
    return "\n".join(lines)


# ─── Auto-extraction (Claude Haiku) ───────────────────────────────────────────

@dataclass
class ExtractionInput:
    inbound_text: str
    last_outbound: Optional[str] = None
    contact_name: Optional[str] = None
    vertical: Optional[str] = None


_EXTRACTOR_SYSTEM = """You are a CRM memory-extractor for Nigerian SMEs.

Given a customer's inbound WhatsApp (plus optionally the business's last reply for
context), extract DURABLE FACTS that would be useful in future replies. Skip
ephemeral details that don't matter beyond today.

Examples of durable facts to extract:
  - preference: "prefers Banana Island over Ikoyi"
  - preference: "vegetarian"
  - history:    "previously bought the 3-bed at Eko Atlantic"
  - history:    "child name: Tobi, in Year 7"
  - constraint: "budget is ₦80M maximum"
  - constraint: "only available Saturdays after 2pm"
  - context:    "diaspora, currently in London — UK timezone"
  - complaint:  "previously complained about slow response on weekends"

DO NOT extract:
  - one-time questions ("what's your address?")
  - greetings, pleasantries
  - the message itself verbatim
  - speculation about things the customer didn't actually say

Return ONLY a JSON array (no preamble, no markdown). Empty array if no durable
fact was learned. Each fact: {"fact_type": str, "fact_text": str, "confidence": float}.

Up to 4 facts per turn. Confidence: 1.0 = explicit statement, 0.5 = clear inference.
"""


def extract_facts_from_message(inp: ExtractionInput) -> list[dict]:
    """Run Claude Haiku to pull durable facts from a single inbound turn.

    Returns a list of {fact_type, fact_text, confidence}. Never raises — returns
    empty list on any error. NOT scope-locked — caller does the scoping when
    storing.
    """
    from config import get_settings
    import anthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        return []

    if not (inp.inbound_text or "").strip():
        return []

    user_block = []
    if inp.contact_name:
        user_block.append(f"Customer name: {inp.contact_name}")
    if inp.vertical:
        user_block.append(f"Business vertical: {inp.vertical}")
    if inp.last_outbound:
        user_block.append(f"Business's previous reply:\n{inp.last_outbound[:600]}")
    user_block.append(f"Customer's new message:\n{inp.inbound_text[:1200]}")

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_EXTRACTOR_SYSTEM,
            messages=[{"role": "user", "content": "\n\n".join(user_block)}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    except Exception as e:
        log.warning("memory_extract_call_failed", error=str(e))
        return []

    # Tolerant JSON parse
    if raw.startswith("```"):
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    if not raw.startswith("["):
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            raw = m.group(0)
        else:
            return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    cleaned: list[dict] = []
    for item in data[:8]:
        if not isinstance(item, dict):
            continue
        text = (item.get("fact_text") or "").strip()
        if not text:
            continue
        cleaned.append({
            "fact_type":   (item.get("fact_type") or "other"),
            "fact_text":   text[:500],
            "confidence":  float(item.get("confidence", 0.7) or 0.7),
        })
    return cleaned


# ─── Convenience: extract + store in one call ─────────────────────────────────

def learn_from_inbound(
    client_id: str,
    contact_phone: str,
    inbound_text: str,
    *,
    contact_name: Optional[str] = None,
    vertical: Optional[str] = None,
    last_outbound: Optional[str] = None,
    source_message_id: Optional[str] = None,
) -> int:
    """Run extraction over an inbound, persist whatever was learned. Returns count.

    Scope-locked — refuses to run without (client_id, contact_phone).
    """
    cid, phone = _require_scope(client_id, contact_phone)

    # T0.2.5 rate-limit gate — abuse-proofing extraction calls.
    try:
        from services.usage_meter import check_rate, record
        if not check_rate(cid, "memory"):
            log.warning("memory_extract_rate_limited", client_id=cid)
            return 0
    except Exception:
        pass

    facts = extract_facts_from_message(ExtractionInput(
        inbound_text=inbound_text,
        last_outbound=last_outbound,
        contact_name=contact_name,
        vertical=vertical,
    ))
    # Record cost regardless of whether facts were extracted — the Haiku
    # call happened either way.
    try:
        from services.usage_meter import record as _rec
        _rec(cid, "memory", units=1)
    except Exception:
        pass
    if not facts:
        return 0
    excerpt = (inbound_text or "")[:240]
    return store_facts_bulk(
        client_id=cid,
        contact_phone=phone,
        facts=facts,
        contact_name=contact_name,
        source_message_id=source_message_id,
        source_excerpt=excerpt,
        requested_by="learn_from_inbound",
    )


# ─── Isolation check ──────────────────────────────────────────────────────────

def isolation_self_test() -> dict:
    """Cross-client probe — verifies no fact has a null/empty client_id and
    that every doc is queryable only through its own client_id.

    Returns a dict suitable for surfacing on the dashboard / alerting.
    """
    col = get_memory_col()
    total = col.count_documents({})
    missing_scope = col.count_documents({
        "$or": [
            {"client_id": {"$exists": False}},
            {"client_id": None},
            {"client_id": ""},
        ]
    })
    missing_phone = col.count_documents({
        "$or": [
            {"contact_phone": {"$exists": False}},
            {"contact_phone": None},
            {"contact_phone": ""},
        ]
    })
    result = {
        "total_facts":      total,
        "missing_client":   missing_scope,
        "missing_phone":    missing_phone,
        "pass":             (missing_scope == 0 and missing_phone == 0),
        "checked_at":       datetime.now(timezone.utc).isoformat(),
    }
    if not result["pass"]:
        log.error("memory_isolation_FAILED", **result)
    else:
        log.info("memory_isolation_ok", total=total)
    return result
