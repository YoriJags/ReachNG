"""
Sequence tick engine.

Runs every 30 minutes via the scheduler. For each due contact:
  - resolve the client + the contact's current step
  - generate a draft via the existing B2C drafter (intent comes from the step)
  - queue it through HITL (which enforces brief gate + account caps)
  - advance the contact to the next step

Failure modes are non-blocking — an error on one contact never halts the tick.
"""
from __future__ import annotations

import re
from typing import Optional

from bson import ObjectId
from database import get_db
import structlog

from services.sequences.store import (
    list_due_contacts,
    advance_contact,
    get_sequence_for_client,
    cancel_sequence,
)

log = structlog.get_logger()


async def process_due_contacts(*, max_per_run: int = 100) -> dict:
    """Find contacts whose next step is due and queue the next draft.

    Returns a per-run summary with counts. Safe to run concurrently with
    B2CCampaign.run because both go through queue_draft (which has the gate)
    and Mongo per-doc updates are atomic.
    """
    from agent.brain import generate_b2c_message
    from tools.hitl import queue_draft, BriefIncompleteError
    from tools.account_guard import OutreachCapExceeded, OutreachPaused

    log.info("sequence_tick_start")
    due = list_due_contacts(limit=max_per_run)

    queued = 0
    skipped_brief = 0
    skipped_caps = 0
    skipped_paused = 0
    skipped_no_channel = 0
    cancelled_no_step = 0
    errors = 0

    for contact in due:
        contact_id = str(contact["_id"])
        client_name = contact.get("client_name")
        if not client_name:
            cancel_sequence(contact_id, reason="missing_client_name")
            cancelled_no_step += 1
            continue

        client = _client_lookup(client_name)
        if not client or not client.get("active", True):
            cancel_sequence(contact_id, reason="client_inactive")
            cancelled_no_step += 1
            continue

        seq = get_sequence_for_client(client, contact.get("sequence_name") or "default")
        step_idx = int(contact.get("sequence_step") or 0)
        if step_idx >= len(seq.steps):
            cancel_sequence(contact_id, reason="sequence_complete")
            cancelled_no_step += 1
            continue

        step = seq.steps[step_idx]
        phone = contact.get("phone")
        email = contact.get("email")
        channel = "whatsapp" if phone else ("email" if email else None)
        if not channel:
            skipped_no_channel += 1
            continue

        name = contact.get("name") or "Customer"
        notes = contact.get("notes")
        tags = contact.get("tags") or []
        vertical = contact.get("vertical") or client.get("vertical") or "general"

        try:
            generated = generate_b2c_message(
                customer_name=name,
                channel=channel,
                vertical=vertical,
                client_name=client_name,
                notes=notes,
                tags=tags,
            )
        except Exception as e:
            log.error("sequence_draft_failed", contact=name, error=str(e))
            errors += 1
            continue

        try:
            queue_draft(
                contact_id=contact_id,
                contact_name=name,
                vertical=vertical,
                channel=channel,
                message=generated.get("message", ""),
                subject=generated.get("subject"),
                phone=phone,
                email=email,
                source="byo_leads",
                client_name=client_name,
            )
        except BriefIncompleteError as e:
            # Brief regressed since launch — pause this contact's sequence so
            # we don't re-burn API tokens every tick. Owner re-enables by
            # restarting the campaign once the brief is fixed.
            cancel_sequence(contact_id, reason=f"brief_incomplete:{','.join(e.blockers)}")
            skipped_brief += 1
            continue
        except OutreachPaused:
            # Client-wide pause — leave the contact alone, the next tick will
            # retry once the admin resumes outreach.
            skipped_paused += 1
            continue
        except OutreachCapExceeded:
            # Daily cap hit — stop this run, the rest will catch up tomorrow.
            skipped_caps += 1
            break
        except Exception as e:
            log.error("sequence_queue_failed", contact=name, error=str(e))
            errors += 1
            continue

        advance_contact(contact_id)
        queued += 1
        log.info(
            "sequence_step_queued",
            contact=name,
            client=client_name,
            step=step_idx,
            step_label=step.label or step.intent,
        )

    summary = {
        "due_total":          len(due),
        "queued":             queued,
        "skipped_brief":      skipped_brief,
        "skipped_caps":       skipped_caps,
        "skipped_paused":     skipped_paused,
        "skipped_no_channel": skipped_no_channel,
        "cancelled":          cancelled_no_step,
        "errors":             errors,
    }
    log.info("sequence_tick_done", **summary)
    return summary


# ─── Internal ────────────────────────────────────────────────────────────────

def _client_lookup(client_name: str) -> Optional[dict]:
    return get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}}
    )
