"""
Sequences — multi-touch outbound campaigns with auto-stop on reply.

A sequence is an ordered list of steps. Each step has:
  - day_offset   (days from sequence start to fire)
  - intent       (drafter intent passed to assemble_context: outreach_warm, followup, final)
  - max_words    (drafting hint)

Default sequence (3 steps) ships per vertical via the vertical primer.
Clients override on `clients.sequences.default`.

Flow:
  1. B2CCampaign queues the first draft AND calls `start_contact_in_sequence(contact_id, "default")`
  2. The scheduler job `_sequence_tick` (hourly) finds contacts with next_due_at <= now
     where status is "contacted" (not replied/opted_out) and fires the next step
  3. After all steps fire, sequence_step >= len(steps) — contact stops getting messages
  4. Reply router marks status="replied" or "opted_out" — both filter out of due query
"""
from services.sequences.store import (
    Sequence,
    SequenceStep,
    DEFAULT_SEQUENCE,
    get_sequence_for_client,
    start_contact_in_sequence,
    advance_contact,
    list_due_contacts,
    cancel_sequence,
)
from services.sequences.engine import process_due_contacts

__all__ = [
    "Sequence",
    "SequenceStep",
    "DEFAULT_SEQUENCE",
    "get_sequence_for_client",
    "start_contact_in_sequence",
    "advance_contact",
    "list_due_contacts",
    "cancel_sequence",
    "process_due_contacts",
]
