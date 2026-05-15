"""
Outcome Learning Loop (T0.4) — the compounding moat.

Every approved draft is tagged with an `outcome_id`. When a positive customer
reply lands (book / pay / yes), the matching outcome is marked `win`. When
silence persists past N days or an explicit `no` arrives, it's `miss`.

A weekly job (Sunday 23:00 Lagos) reviews wins vs misses per client and emits
a `prompt_addendum` — auto-merged into that client's BusinessBrief override.
The agent then writes better drafts the next week. Per-client, automatic,
hands-off.

Schema (collection: `outcomes`)
-------------------------------
{
  _id, client_id, client_name,
  approval_id,           # ref tools/hitl approvals._id
  contact_phone, contact_name,
  source,                # "closer" | "b2c" | "chase" | etc — from approval doc
  vertical,
  draft_message,         # what we sent (post-edit if edited)
  draft_was_edited,      # bool — did the operator have to edit?
  status,                # "open" | "win" | "miss"
  win_signal,            # if win — "paid" | "booked" | "yes" | "reply_positive"
  miss_reason,           # if miss — "silence" | "explicit_no" | "complaint"
  created_at, resolved_at,
  weekly_distil_id,      # set after a Sunday job has consumed this row
}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Constants ────────────────────────────────────────────────────────────────

SILENCE_MISS_AFTER_DAYS = 7
WEEKLY_LOOKBACK_DAYS = 7

_POSITIVE_INTENTS = {"booked", "paid", "yes", "interested", "deposit_made"}
_NEGATIVE_INTENTS = {"no", "not_interested", "complaint", "refund", "decline"}


# ─── Collection ───────────────────────────────────────────────────────────────

def _col():
    return get_db()["outcomes"]


def ensure_outcome_indexes() -> None:
    col = _col()
    col.create_index([("client_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)])
    col.create_index([("approval_id", ASCENDING)], unique=True, sparse=True)
    col.create_index([("contact_phone", ASCENDING), ("status", ASCENDING)])
    col.create_index([("status", ASCENDING), ("created_at", ASCENDING)])  # nightly silence sweep


# ─── Public: tag on approval ──────────────────────────────────────────────────

def open_outcome_from_approval(approval_doc: dict) -> Optional[str]:
    """Called from tools/hitl.py after a draft is approved (or edited+approved).

    Idempotent on approval_id — safe to call twice.
    Returns the new outcome_id, or None if we shouldn't track this draft.
    """
    if not approval_doc:
        return None

    approval_id = str(approval_doc.get("_id") or "")
    if not approval_id:
        return None

    # Already tracked? Idempotent.
    existing = _col().find_one({"approval_id": approval_id}, {"_id": 1})
    if existing:
        return str(existing["_id"])

    msg = approval_doc.get("edited_message") or approval_doc.get("message") or ""
    doc = {
        "client_id":        approval_doc.get("client_id"),
        "client_name":      approval_doc.get("client_name"),
        "approval_id":      approval_id,
        "contact_phone":    approval_doc.get("contact_phone"),
        "contact_name":     approval_doc.get("contact_name"),
        "source":           approval_doc.get("source") or "unknown",
        "vertical":         approval_doc.get("vertical"),
        "draft_message":    msg[:2000],
        "draft_was_edited": bool(approval_doc.get("edited_message")),
        "status":           "open",
        "win_signal":       None,
        "miss_reason":      None,
        "created_at":       datetime.now(timezone.utc),
        "resolved_at":      None,
        "weekly_distil_id": None,
    }
    res = _col().insert_one(doc)
    log.info("outcome_opened", outcome_id=str(res.inserted_id), client_id=doc["client_id"],
             source=doc["source"], edited=doc["draft_was_edited"])
    return str(res.inserted_id)


# ─── Public: tag from inbound reply ───────────────────────────────────────────

def tag_from_inbound(*, contact_phone: str, client_id: Optional[str],
                     intent: Optional[str], raw_text: Optional[str] = None) -> int:
    """Match this inbound against any open outcomes for this contact and resolve them.

    `intent` is the classifier output from services/inbound_classifier.py
    (e.g. "interested", "complaint", "paid", "booked", "no").

    Returns count of outcomes resolved.
    """
    if not contact_phone:
        return 0

    q = {"contact_phone": contact_phone, "status": "open"}
    if client_id:
        q["client_id"] = client_id

    open_rows = list(_col().find(q).sort("created_at", -1).limit(20))
    if not open_rows:
        return 0

    intent_lc = (intent or "").lower()
    now = datetime.now(timezone.utc)

    new_status = None
    win_signal = None
    miss_reason = None

    if intent_lc in _POSITIVE_INTENTS:
        new_status, win_signal = "win", intent_lc
    elif intent_lc in _NEGATIVE_INTENTS:
        new_status, miss_reason = "miss", intent_lc
    else:
        # Neutral inbound — not a resolution signal. Leave open.
        return 0

    updates = {
        "status":      new_status,
        "resolved_at": now,
    }
    if win_signal:  updates["win_signal"]  = win_signal
    if miss_reason: updates["miss_reason"] = miss_reason

    ids = [r["_id"] for r in open_rows]
    res = _col().update_many({"_id": {"$in": ids}}, {"$set": updates})
    log.info("outcomes_resolved_from_inbound", count=res.modified_count,
             contact=contact_phone, intent=intent_lc, status=new_status)
    return res.modified_count


# ─── Scheduler: nightly silence sweep ─────────────────────────────────────────

def sweep_silence_to_miss() -> int:
    """Mark `open` outcomes older than SILENCE_MISS_AFTER_DAYS days as miss=silence.
    Runs nightly at 02:00 Lagos via scheduler.py.
    """
    from datetime import timedelta
    threshold = datetime.now(timezone.utc) - timedelta(days=SILENCE_MISS_AFTER_DAYS)
    res = _col().update_many(
        {"status": "open", "created_at": {"$lt": threshold}},
        {"$set": {
            "status":      "miss",
            "miss_reason": "silence",
            "resolved_at": datetime.now(timezone.utc),
        }},
    )
    log.info("outcome_silence_sweep", marked=res.modified_count)
    return res.modified_count


# ─── Scheduler: weekly distil ─────────────────────────────────────────────────

def distil_for_client(client_id: str) -> Optional[str]:
    """Read last-7-days wins + misses for one client. Ask Haiku to produce a
    short `prompt_addendum`. Persist on `clients.prompt_addendum`. Mark the
    consumed outcomes with the distil_id.

    Returns the new addendum string, or None if no signal.
    """
    from datetime import timedelta
    if not client_id:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=WEEKLY_LOOKBACK_DAYS)
    rows = list(_col().find({
        "client_id": client_id,
        "status":    {"$in": ["win", "miss"]},
        "resolved_at": {"$gte": cutoff},
        "weekly_distil_id": None,
    }).limit(200))

    wins   = [r for r in rows if r["status"] == "win"]
    misses = [r for r in rows if r["status"] == "miss"]

    # Need at least a handful of resolutions to draw a signal.
    if len(rows) < 5:
        return None

    addendum = _haiku_distil(wins=wins, misses=misses)
    if not addendum:
        return None

    distil_id = str(ObjectId())
    db = get_db()
    db["clients"].update_one(
        {"_id": ObjectId(client_id)} if ObjectId.is_valid(client_id) else {"name": client_id},
        {"$set": {
            "prompt_addendum":         addendum,
            "prompt_addendum_at":      datetime.now(timezone.utc),
            "prompt_addendum_distil":  distil_id,
        }},
    )
    _col().update_many(
        {"_id": {"$in": [r["_id"] for r in rows]}},
        {"$set": {"weekly_distil_id": distil_id}},
    )
    log.info("outcome_distil_applied", client_id=client_id, distil_id=distil_id,
             wins=len(wins), misses=len(misses), addendum_chars=len(addendum))
    return addendum


def distil_all_clients() -> dict:
    """Weekly Sunday 23:00 Lagos job — distil for every active client.
    Returns {client_id: addendum or None}.
    """
    db = get_db()
    active = list(db["clients"].find(
        {"active": True, "payment_status": "paid"},
        {"_id": 1, "name": 1},
    ))
    out: dict = {}
    for c in active:
        cid = str(c["_id"])
        try:
            out[cid] = distil_for_client(cid)
        except Exception as e:
            log.warning("outcome_distil_failed", client_id=cid, error=str(e))
            out[cid] = None
    return out


# ─── Haiku distil ─────────────────────────────────────────────────────────────

_DISTIL_SYSTEM = """You are a sales-effectiveness coach reviewing the past week of an AI sales agent's drafted WhatsApp replies for one Lagos SME.

You are given:
- WIN drafts: the customer responded positively (booked / paid / yes)
- MISS drafts: the customer went silent for 7+ days, said no, or complained

Produce a SHORT addendum (max 6 bullet points, each one sentence) that the agent should follow next week to write better drafts for THIS specific client. Focus on patterns:
- What phrasing / openers correlate with wins?
- What patterns precede misses (too long, wrong tone, missing CTA, etc)?
- Specific naira amounts, urgency cues, or context details that worked?

Be concrete. Reference real patterns from the drafts. Do not invent. If signal is weak, say so in one line.

Output format: plain bullet points starting with "- ". No preamble. No closing summary."""


def _haiku_distil(*, wins: list[dict], misses: list[dict]) -> Optional[str]:
    """One Haiku call to produce the addendum. Best-effort — never raises."""
    try:
        from anthropic import Anthropic
        from config import get_settings
    except Exception as e:
        log.warning("outcome_distil_anthropic_unavailable", error=str(e))
        return None

    settings = get_settings()
    if not getattr(settings, "anthropic_api_key", None):
        return None

    def _fmt(rows: list[dict], label: str) -> str:
        if not rows:
            return f"{label}: (none this week)"
        lines = [f"{label} ({len(rows)} total):"]
        for r in rows[:30]:
            signal = r.get("win_signal") or r.get("miss_reason") or "?"
            lines.append(f"  [{signal}] {r.get('draft_message', '')[:240]}")
        return "\n".join(lines)

    user_msg = "\n\n".join([_fmt(wins, "WINS"), _fmt(misses, "MISSES")])

    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_DISTIL_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = (resp.content[0].text if resp.content else "").strip()
        return text[:1500] or None
    except Exception as e:
        log.warning("outcome_distil_haiku_failed", error=str(e))
        return None


# ─── Public: prompt-injection helper ──────────────────────────────────────────

def get_addendum_for_client(client_doc: Optional[dict]) -> Optional[str]:
    """Used by agent/brain.py + services/closer/brain.py to inject the addendum
    into the system prompt. Returns the addendum text or None.
    """
    if not client_doc:
        return None
    return (client_doc.get("prompt_addendum") or "").strip() or None


# ─── Public: per-client stats (for portal + admin) ────────────────────────────

def client_outcome_stats(client_id: str, *, lookback_days: int = 30) -> dict:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    pipeline = [
        {"$match": {"client_id": client_id, "created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    by_status = {r["_id"]: r["n"] for r in _col().aggregate(pipeline)}
    wins   = by_status.get("win", 0)
    misses = by_status.get("miss", 0)
    open_  = by_status.get("open", 0)
    total_resolved = wins + misses
    win_rate = (wins / total_resolved) if total_resolved else None
    return {
        "lookback_days": lookback_days,
        "wins":          wins,
        "misses":        misses,
        "open":          open_,
        "win_rate":      win_rate,
    }
