"""
Prospect interviews — capture the qualitative input from real conversations.

Phase A of the validation funnel: when someone replies to ReachNG's cold
outreach and the conversation moves to a real DM/call, Yori captures what
they actually said here. Quote-tagged so the strongest line lands on the
landing page as anonymous social proof later.

Schema (collection: prospect_interviews)
  {
    _id, prospect_name, business_name, vertical, channel,
    pain_today, what_theyd_pay_for, killer_quote,
    decision_maker_role, current_tool, monthly_whatsapp_volume,
    sentiment: "hot" | "warm" | "cold",
    next_step, contact_id (link to closer_lead or contact doc),
    created_at, updated_at,
    notes (free text)
  }

Cheap, no LLM. Pure CRUD around what Yori types after each conversation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


VALID_SENTIMENTS = ("hot", "warm", "cold")


def _col():
    return get_db()["prospect_interviews"]


def ensure_interview_indexes() -> None:
    _col().create_index([("created_at", DESCENDING)])
    _col().create_index([("sentiment", ASCENDING), ("created_at", DESCENDING)])
    _col().create_index([("business_name", ASCENDING)])


def create_interview(*,
                      prospect_name: str,
                      business_name: str,
                      vertical: Optional[str] = None,
                      channel: str = "whatsapp",
                      pain_today: str = "",
                      what_theyd_pay_for: str = "",
                      killer_quote: str = "",
                      decision_maker_role: Optional[str] = None,
                      current_tool: Optional[str] = None,
                      monthly_whatsapp_volume: Optional[int] = None,
                      sentiment: str = "warm",
                      next_step: str = "",
                      contact_id: Optional[str] = None,
                      notes: str = "") -> str:
    if not prospect_name.strip() or not business_name.strip():
        raise ValueError("prospect_name and business_name required")
    s = (sentiment or "warm").lower()
    if s not in VALID_SENTIMENTS:
        s = "warm"
    now = datetime.now(timezone.utc)
    doc = {
        "prospect_name":            prospect_name.strip()[:120],
        "business_name":            business_name.strip()[:120],
        "vertical":                 (vertical or "").strip().lower() or None,
        "channel":                  (channel or "whatsapp").strip().lower(),
        "pain_today":               (pain_today or "").strip()[:2000],
        "what_theyd_pay_for":       (what_theyd_pay_for or "").strip()[:2000],
        "killer_quote":             (killer_quote or "").strip()[:600],
        "decision_maker_role":      (decision_maker_role or None),
        "current_tool":             (current_tool or None),
        "monthly_whatsapp_volume":  (int(monthly_whatsapp_volume) if monthly_whatsapp_volume else None),
        "sentiment":                s,
        "next_step":                (next_step or "").strip()[:600],
        "contact_id":               contact_id,
        "notes":                    (notes or "").strip()[:4000],
        "created_at":               now,
        "updated_at":               now,
    }
    return str(_col().insert_one(doc).inserted_id)


def list_interviews(*, limit: int = 100, sentiment: Optional[str] = None,
                     vertical: Optional[str] = None) -> list[dict]:
    q: dict = {}
    if sentiment in VALID_SENTIMENTS:
        q["sentiment"] = sentiment
    if vertical:
        q["vertical"] = vertical.strip().lower()
    docs = list(_col().find(q).sort("created_at", DESCENDING).limit(min(limit, 500)))
    for d in docs:
        d["_id"]        = str(d["_id"])
        d["created_at"] = d["created_at"].isoformat() if hasattr(d.get("created_at"), "isoformat") else d.get("created_at")
        d["updated_at"] = d["updated_at"].isoformat() if hasattr(d.get("updated_at"), "isoformat") else d.get("updated_at")
    return docs


def update_interview(interview_id: str, patch: dict) -> bool:
    if not patch:
        return False
    allowed = {"pain_today", "what_theyd_pay_for", "killer_quote",
               "decision_maker_role", "current_tool", "monthly_whatsapp_volume",
               "sentiment", "next_step", "notes"}
    clean: dict = {k: v for k, v in patch.items() if k in allowed}
    if "sentiment" in clean and clean["sentiment"] not in VALID_SENTIMENTS:
        clean.pop("sentiment")
    if "monthly_whatsapp_volume" in clean and clean["monthly_whatsapp_volume"]:
        try:
            clean["monthly_whatsapp_volume"] = int(clean["monthly_whatsapp_volume"])
        except (TypeError, ValueError):
            clean.pop("monthly_whatsapp_volume")
    if not clean:
        return False
    clean["updated_at"] = datetime.now(timezone.utc)
    res = _col().update_one({"_id": ObjectId(interview_id)}, {"$set": clean})
    return res.matched_count > 0


def delete_interview(interview_id: str) -> bool:
    res = _col().delete_one({"_id": ObjectId(interview_id)})
    return res.deleted_count > 0


def stats() -> dict:
    """Quick rollup for the dashboard header."""
    pipeline = [
        {"$group": {"_id": "$sentiment", "n": {"$sum": 1}}},
    ]
    out = {"hot": 0, "warm": 0, "cold": 0, "total": 0}
    for row in _col().aggregate(pipeline):
        s = row["_id"] or "warm"
        if s in out:
            out[s] = row["n"]
        out["total"] += row["n"]
    return out
