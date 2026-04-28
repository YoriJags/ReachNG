"""
Sequence schema + state machine on b2c_contacts.

State on a contact:
  sequence_name       : str   ("default" unless overridden)
  sequence_step       : int   (0-based index of NEXT step to fire; len(steps) means done)
  sequence_started_at : datetime
  next_due_at         : datetime | None   (None = no further step pending)

A contact stops receiving messages when any of:
  - sequence_step >= len(sequence.steps)
  - status in {"replied", "opted_out", "converted"}
  - next_due_at is None
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from database import get_db
import structlog

log = structlog.get_logger()


# ─── Models ───────────────────────────────────────────────────────────────────

class SequenceStep(BaseModel):
    day_offset: int = 0                  # days from sequence start to fire this step
    intent: str = "outreach_warm"        # drafter intent → assemble_context
    max_words: int = 60                  # WhatsApp-shaped default
    label: str = ""                      # human-readable name for ops dashboards


class Sequence(BaseModel):
    name: str = "default"
    label: str = "Default 3-touch"
    steps: list[SequenceStep] = Field(default_factory=list)


# Default sequence applied to every client unless they override on clients.sequences.
# Spacing is conservative — 3 days between touches, 4 days for the final.
DEFAULT_SEQUENCE = Sequence(
    name="default",
    label="Default 3-touch (initial → +3d → +7d)",
    steps=[
        SequenceStep(day_offset=0, intent="outreach_warm", max_words=55, label="Initial"),
        SequenceStep(day_offset=3, intent="followup",      max_words=45, label="Follow-up"),
        SequenceStep(day_offset=7, intent="followup",      max_words=40, label="Final touch"),
    ],
)


# ─── Resolution ──────────────────────────────────────────────────────────────

def get_sequence_for_client(client_doc: dict, name: str = "default") -> Sequence:
    """Pull the named sequence from the client doc, falling back to the global default.
    Per-vertical overrides live on the vertical primer (future); for v1, the per-client
    override on `clients.sequences.{name}` wins."""
    client_seqs = (client_doc or {}).get("sequences") or {}
    raw = client_seqs.get(name)
    if not raw or not raw.get("steps"):
        return DEFAULT_SEQUENCE
    try:
        return Sequence(**raw)
    except Exception as e:
        log.warning("sequence_parse_failed_fallback_to_default", client=client_doc.get("name"), error=str(e))
        return DEFAULT_SEQUENCE


# ─── State machine on b2c_contacts ───────────────────────────────────────────

def _contacts():
    return get_db()["b2c_contacts"]


def start_contact_in_sequence(
    contact_id: str,
    *,
    sequence_name: str = "default",
    initial_step_already_sent: bool = True,
) -> Optional[dict]:
    """Mark a contact as entered into a sequence.

    `initial_step_already_sent=True` (the common case) means the campaign runner
    just queued step 0 — so we set sequence_step=1 and schedule next_due_at to
    fire step 1 (typically D+3). If False, we set step=0 and next_due_at=now.
    """
    now = datetime.now(timezone.utc)
    contact = _contacts().find_one({"_id": ObjectId(contact_id)})
    if not contact:
        return None

    client_name = contact.get("client_name")
    client = _client_lookup(client_name)
    seq = get_sequence_for_client(client, sequence_name)
    if not seq.steps:
        return None

    next_step_idx = 1 if initial_step_already_sent else 0
    next_due_at: Optional[datetime] = None
    if next_step_idx < len(seq.steps):
        offset_days = seq.steps[next_step_idx].day_offset - seq.steps[0].day_offset
        next_due_at = now + timedelta(days=max(0, offset_days))

    update = {
        "sequence_name": sequence_name,
        "sequence_step": next_step_idx,
        "sequence_started_at": contact.get("sequence_started_at") or now,
        "next_due_at": next_due_at,
        "updated_at": now,
    }
    _contacts().update_one({"_id": ObjectId(contact_id)}, {"$set": update})
    return update


def advance_contact(contact_id: str) -> Optional[dict]:
    """Bump the contact to the next step after a draft has been queued for the
    current step. Sets next_due_at based on the next step's day_offset, or clears
    it when the sequence is complete."""
    now = datetime.now(timezone.utc)
    contact = _contacts().find_one({"_id": ObjectId(contact_id)})
    if not contact:
        return None

    client_name = contact.get("client_name")
    client = _client_lookup(client_name)
    seq = get_sequence_for_client(client, contact.get("sequence_name") or "default")

    current_step = int(contact.get("sequence_step") or 0)
    next_step_idx = current_step + 1

    if next_step_idx >= len(seq.steps):
        # Sequence complete — clear next_due_at so we never re-pick this contact.
        update = {
            "sequence_step": next_step_idx,
            "next_due_at": None,
            "sequence_completed_at": now,
            "updated_at": now,
        }
    else:
        started = contact.get("sequence_started_at") or now
        offset_days = seq.steps[next_step_idx].day_offset - seq.steps[0].day_offset
        update = {
            "sequence_step": next_step_idx,
            "next_due_at": started + timedelta(days=max(0, offset_days)),
            "updated_at": now,
        }

    _contacts().update_one({"_id": ObjectId(contact_id)}, {"$set": update})
    return update


def cancel_sequence(contact_id: str, *, reason: str = "manual") -> bool:
    """Stop a sequence early — used by the reply router on reply/opt-out."""
    now = datetime.now(timezone.utc)
    res = _contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {
            "next_due_at": None,
            "sequence_cancelled_at": now,
            "sequence_cancel_reason": reason,
            "updated_at": now,
        }},
    )
    return res.matched_count > 0


def list_due_contacts(*, limit: int = 200) -> list[dict]:
    """Contacts whose next sequence step is ready to fire.

    Filters:
      - next_due_at <= now
      - status in {new, contacted}  (NOT replied / opted_out / converted)
      - sequence_step is set
    """
    now = datetime.now(timezone.utc)
    return list(
        _contacts()
        .find({
            "next_due_at": {"$lte": now, "$ne": None},
            "status": {"$in": ["new", "contacted"]},
            "sequence_step": {"$exists": True},
        })
        .sort("next_due_at", 1)
        .limit(min(limit, 1000))
    )


# ─── Internal ────────────────────────────────────────────────────────────────

def _client_lookup(client_name: Optional[str]) -> Optional[dict]:
    if not client_name:
        return None
    return get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}}
    )
