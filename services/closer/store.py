"""
ReachNG Closer — lead intake + brief storage.

Phase 1 scope: ingest leads from three channels (email stub, Unipile WhatsApp,
webhook), persist them scoped to a client, and expose a thread we can read.
No AI drafting yet — that is Phase 2.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from pydantic import BaseModel, Field

from database import get_db

CloserStage = Literal["new", "qualifying", "ready", "booked", "lost", "stalled"]
VALID_STAGES: tuple[str, ...] = ("new", "qualifying", "ready", "booked", "lost", "stalled")

CloserSource = Literal["email", "whatsapp", "webhook", "manual"]


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CloserBrief(BaseModel):
    """Per-client playbook the Closer uses to qualify and convert leads."""
    product: str = ""                      # e.g. "3-bed terraces in Lekki Phase 1"
    icp: str = ""                          # Ideal client profile — who they sell to
    qualifying_questions: list[str] = []   # Must-ask before advancing stage
    red_flags: list[str] = []              # Reasons to mark lost fast
    closing_action: str = ""               # What "ready" means — e.g. "book a viewing"
    tone: str = "warm-professional"        # Voice: "luxury", "warm-professional", "hustle"
    pricing_rules: str = ""                # Pricing bands, negotiation limits
    never_say: list[str] = []              # Banned phrases / disclosures


class CloserLead(BaseModel):
    id: Optional[str] = None
    client_id: str
    client_name: str
    vertical: str = "real_estate"
    source: CloserSource
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    inquiry_text: str = ""
    stage: CloserStage = "new"
    thread: list[dict] = []
    handover_at: Optional[datetime] = None
    source_consent: Optional[str] = None    # "form", "inbound", "explicit" — filled at intake
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ─── Collection + indexes ─────────────────────────────────────────────────────

def _col():
    return get_db()["closer_leads"]


def ensure_closer_indexes() -> None:
    c = _col()
    c.create_index([("client_id", ASCENDING), ("created_at", DESCENDING)])
    c.create_index([("client_id", ASCENDING), ("stage", ASCENDING)])
    c.create_index([("contact_phone", ASCENDING)], sparse=True)
    c.create_index([("contact_email", ASCENDING)], sparse=True)
    c.create_index([("created_at", DESCENDING)])


# ─── Serialise helper ─────────────────────────────────────────────────────────

def _serialise(doc: dict) -> dict:
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    for f in ("created_at", "updated_at", "handover_at"):
        v = out.get(f)
        if hasattr(v, "isoformat"):
            out[f] = v.isoformat()
    for msg in out.get("thread", []):
        ts = msg.get("at")
        if hasattr(ts, "isoformat"):
            msg["at"] = ts.isoformat()
    return out


# ─── Brief ────────────────────────────────────────────────────────────────────

def update_brief(client_id: str, brief: CloserBrief) -> dict:
    """Write the per-client closer_brief onto the client doc."""
    now = datetime.now(timezone.utc)
    res = get_db()["clients"].update_one(
        {"_id": ObjectId(client_id)},
        {"$set": {"closer_brief": brief.model_dump(), "closer_enabled": True, "updated_at": now}},
    )
    return {"matched": res.matched_count, "modified": res.modified_count}


# ─── Lead CRUD ────────────────────────────────────────────────────────────────

def create_lead(
    *,
    client_id: str,
    client_name: str,
    vertical: str,
    source: CloserSource,
    contact_name: Optional[str] = None,
    contact_phone: Optional[str] = None,
    contact_email: Optional[str] = None,
    inquiry_text: str = "",
    source_consent: Optional[str] = None,
) -> dict:
    now = datetime.now(timezone.utc)
    doc = {
        "client_id": client_id,
        "client_name": client_name,
        "vertical": vertical,
        "source": source,
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "contact_email": contact_email,
        "inquiry_text": inquiry_text,
        "stage": "new",
        "thread": [],
        "source_consent": source_consent,
        "created_at": now,
        "updated_at": now,
    }
    if inquiry_text:
        doc["thread"].append({
            "direction": "in",
            "channel": source,
            "body": inquiry_text,
            "at": now,
        })
    res = _col().insert_one(doc)
    doc["_id"] = res.inserted_id
    return _serialise(doc)


def find_lead_by_contact(
    client_id: str,
    *,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[dict]:
    """Find an open lead for this client by phone or email."""
    if not phone and not email:
        return None
    q: dict = {"client_id": client_id, "stage": {"$nin": ["lost", "booked"]}}
    if phone:
        q["contact_phone"] = phone
    if email:
        q["contact_email"] = email
    return _col().find_one(q, sort=[("created_at", DESCENDING)])


def list_leads_for_client(client_id: str, *, stage: Optional[str] = None, limit: int = 100) -> list[dict]:
    q: dict = {"client_id": client_id}
    if stage:
        q["stage"] = stage
    docs = list(_col().find(q).sort("created_at", DESCENDING).limit(min(limit, 500)))
    return [_serialise(d) for d in docs]


def get_lead(lead_id: str) -> Optional[dict]:
    doc = _col().find_one({"_id": ObjectId(lead_id)})
    return _serialise(doc) if doc else None


def append_thread_message(
    lead_id: str,
    *,
    direction: Literal["in", "out", "note"],
    channel: str,
    body: str,
    author: Optional[str] = None,
) -> bool:
    now = datetime.now(timezone.utc)
    entry = {
        "direction": direction,
        "channel": channel,
        "body": body,
        "author": author,
        "at": now,
    }
    res = _col().update_one(
        {"_id": ObjectId(lead_id)},
        {"$push": {"thread": entry}, "$set": {"updated_at": now}},
    )
    return res.matched_count > 0


def update_stage(lead_id: str, stage: str, *, handover: bool = False) -> bool:
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage: {stage}")
    now = datetime.now(timezone.utc)
    patch: dict = {"stage": stage, "updated_at": now}
    if handover or stage == "ready":
        patch["handover_at"] = now
    res = _col().update_one({"_id": ObjectId(lead_id)}, {"$set": patch})
    return res.matched_count > 0
