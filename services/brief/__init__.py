"""
Business Brief — per-client + per-vertical context layer.

The single source of truth that every AI drafter (Closer, BYO Leads outreach,
invoice chaser, debt collector, rent chase) reads from. A vertical primer
provides industry defaults; the client's business_brief overrides on top.

Public surface:
  - BusinessBrief, VerticalPrimer (Pydantic models)
  - get_brief, update_brief                       (per-client)
  - get_primer, upsert_primer, list_primers       (per-vertical)
  - assemble_context(client_id, intent)           (the merger AI drafters use)
  - brief_health(client_id)                       (completeness gate)
  - seed_default_primers()                        (idempotent boot seed)
  - ensure_brief_indexes()                        (Mongo indexes)
"""
from services.brief.store import (
    BusinessBrief,
    VerticalPrimer,
    get_brief,
    update_brief,
    get_primer,
    upsert_primer,
    list_primers,
    brief_health,
    ensure_brief_indexes,
    list_brief_history,
    restore_brief_version,
)
from services.brief.context import assemble_context
from services.brief.primers import seed_default_primers

__all__ = [
    "BusinessBrief",
    "VerticalPrimer",
    "get_brief",
    "update_brief",
    "get_primer",
    "upsert_primer",
    "list_primers",
    "assemble_context",
    "brief_health",
    "seed_default_primers",
    "ensure_brief_indexes",
    "list_brief_history",
    "restore_brief_version",
]
