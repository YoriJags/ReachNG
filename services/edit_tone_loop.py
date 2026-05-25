"""
Edit tone-loop (P0.5 trust/tone item).

Closes the loop between operator edits and the never-say list.

Mechanics:
  1. Every time an operator edits a draft (`tools/hitl.py::edit_draft`), we
     diff the original vs the edited text and record per-word removals into
     `edit_tone_signals` (one row per (client, word, weekly bucket)).
  2. A weekly scheduler job aggregates: if a single word was removed ≥ N
     times in the last 7 days, surface "Add to never-say?" suggestions on
     the client's portal Configure page.

Storage:
  edit_tone_signals
    { client_id, week_start, word, count, last_seen, suggested, applied }
    Index: (client_id, week_start, word) unique.

Why not just count edits live: bursty editing (one chat full of "babe") could
bias the suggestion. Weekly buckets smooth it out.

Cost: zero LLM. Pure regex + Mongo upsert per edit (~3ms).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Iterable, Optional

import structlog
from pymongo import ASCENDING

from database import get_db

log = structlog.get_logger()

# Words we always want to flag as candidates — overlaps with tools/tone but is
# the *signal* set (worth nudging the owner to formalise), not the *scrub*
# set (which already strips automatically).
_TONE_CANDIDATES = {
    "babe", "love", "dear", "darling", "sweetie", "sweetheart",
    "honey", "hun", "boo", "bae", "fam", "bro", "sis",
    "sister", "brother", "my dear", "my love",
}

_WORD_RE = re.compile(r"[a-zA-Z]+(?:\s+[a-zA-Z]+)?")

SUGGEST_THRESHOLD = 3  # ≥3 removals in the rolling 7-day window → surface


def _col():
    return get_db()["edit_tone_signals"]


def ensure_tone_indexes() -> None:
    _col().create_index(
        [("client_id", ASCENDING), ("week_start", ASCENDING), ("word", ASCENDING)],
        unique=True,
    )
    _col().create_index([("client_id", ASCENDING), ("suggested", ASCENDING)])


def _tokens(text: str) -> set[str]:
    """Lowercase candidate words present in the text. Single + 2-word."""
    if not text:
        return set()
    found: set[str] = set()
    lower = text.lower()
    for cand in _TONE_CANDIDATES:
        if re.search(rf"\b{re.escape(cand)}\b", lower):
            found.add(cand)
    return found


def _week_start(now: Optional[datetime] = None) -> datetime:
    n = now or datetime.now(timezone.utc)
    # Monday 00:00 UTC
    start = n - timedelta(days=n.weekday(), hours=n.hour, minutes=n.minute,
                          seconds=n.second, microseconds=n.microsecond)
    return start


def record_edit(approval_doc: Optional[dict], *, new_message: str) -> None:
    """Diff original vs edited and bump per-word counters for the client."""
    if not approval_doc:
        return
    client_name = approval_doc.get("client_name")
    if not client_name:
        return
    original = approval_doc.get("original_message") or approval_doc.get("message") or ""
    removed = _tokens(original) - _tokens(new_message)
    if not removed:
        return

    # Resolve client_id by name (single lookup — cached client docs are
    # acceptable cost for an operator edit event).
    cdoc = get_db()["clients"].find_one(
        {"name": client_name}, {"_id": 1, "never_say": 1})
    if not cdoc:
        return
    cid = str(cdoc["_id"])
    existing_never_say = {(s or "").strip().lower()
                          for s in (cdoc.get("never_say") or [])}
    # Skip words already on the never_say list — we'd suggest a dup.
    removed = {w for w in removed if w not in existing_never_say}
    if not removed:
        return

    week = _week_start()
    now = datetime.now(timezone.utc)
    col = _col()
    for word in removed:
        col.update_one(
            {"client_id": cid, "week_start": week, "word": word},
            {"$inc":  {"count": 1},
             "$set":  {"last_seen": now},
             "$setOnInsert": {"suggested": False, "applied": False}},
            upsert=True,
        )
    log.info("edit_tone_recorded", client=client_name, removed=list(removed))


def pending_suggestions(client_id: str, *, weeks: int = 1) -> list[dict]:
    """Returns words removed ≥ SUGGEST_THRESHOLD times in the last `weeks` weeks.

    Used by the portal Configure page to render "Add to never-say?" prompts.
    """
    if not client_id:
        return []
    since = _week_start() - timedelta(weeks=max(0, weeks - 1))
    pipeline = [
        {"$match": {"client_id": str(client_id),
                     "week_start": {"$gte": since},
                     "applied": False}},
        {"$group": {"_id": "$word",
                     "count":     {"$sum": "$count"},
                     "last_seen": {"$max": "$last_seen"}}},
        {"$match": {"count": {"$gte": SUGGEST_THRESHOLD}}},
        {"$sort":  {"count": -1}},
    ]
    out = []
    for row in _col().aggregate(pipeline):
        out.append({"word": row["_id"], "count": row["count"],
                    "last_seen": row.get("last_seen")})
    return out


def mark_applied(client_id: str, words: Iterable[str]) -> int:
    """Mark suggestions as applied (owner accepted them). Returns count."""
    words_norm = [(w or "").strip().lower() for w in words if (w or "").strip()]
    if not words_norm:
        return 0
    res = _col().update_many(
        {"client_id": str(client_id), "word": {"$in": words_norm}},
        {"$set": {"applied": True, "applied_at": datetime.now(timezone.utc)}},
    )
    return res.modified_count
