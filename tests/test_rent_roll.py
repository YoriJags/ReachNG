"""Golden tests for EstateOS rent — the money math we actually sell.

Two things must never silently drift:
  1. The chase escalation bands (CLAUDE.md domain rule): the day-count -> tone
     mapping a landlord's tenant sees. A wrong band sends a "final quit notice"
     tone to someone 3 days late, or a limp "friendly reminder" to someone 90
     days in arrears. Pure function, no DB.
  2. Period/charge opening is idempotent — the unique (unit_id, period) index
     means re-running a month never double-charges a tenant. DB-backed, so it
     carries @pytest.mark.db and is skipped unless RUN_DB_TESTS=1.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

import pytest

from services.estate.rent_roll import CHASE_STAGES, stage_for_days_overdue


# ── Escalation bands (pure) ───────────────────────────────────────────────────

def test_chase_stages_match_the_domain_rule():
    """CLAUDE.md: friendly 1-6, firm 7-13, serious 14-29, warning 30-59, final 60+."""
    assert [s["min_days"] for s in CHASE_STAGES] == [1, 7, 14, 30, 60]
    assert [s["tone"] for s in CHASE_STAGES] == [
        "friendly", "firm", "serious", "warning", "final",
    ]


def test_chase_stage_thresholds_are_strictly_increasing():
    mins = [s["min_days"] for s in CHASE_STAGES]
    assert mins == sorted(mins) and len(set(mins)) == len(mins), \
        "overlapping or unordered thresholds would make stage selection ambiguous"


@pytest.mark.parametrize("days,tone", [
    # lower edge / below threshold falls back to the gentlest tone
    (-5, "friendly"),
    (0,  "friendly"),
    # friendly band 1-6
    (1,  "friendly"),
    (6,  "friendly"),
    # firm band 7-13 (boundary 6/7)
    (7,  "firm"),
    (13, "firm"),
    # serious band 14-29 (boundary 13/14)
    (14, "serious"),
    (29, "serious"),
    # warning band 30-59 (boundary 29/30)
    (30, "warning"),
    (59, "warning"),
    # final band 60+ (boundary 59/60)
    (60, "final"),
    (365, "final"),
])
def test_stage_for_days_overdue_boundaries(days, tone):
    assert stage_for_days_overdue(days)["tone"] == tone


def test_stage_payload_shape():
    s = stage_for_days_overdue(20)
    assert {"min_days", "stage", "tone", "label"} <= set(s)
    assert s["stage"] == "serious" and s["label"]


# ── Idempotent period-open (DB-backed) ────────────────────────────────────────

@pytest.mark.db
def test_open_charge_is_idempotent_per_unit_period():
    """Opening the same (unit_id, period) twice must NOT create a second charge —
    the unique index blocks it and open_charge returns "" on the duplicate."""
    from services.estate.rent_roll import open_charge, ensure_rent_indexes, _col

    ensure_rent_indexes()  # the unique (unit_id, period) index must exist
    unit_id = f"test_unit_{secrets.token_hex(6)}"
    period = "2026-06"
    due = datetime(2026, 6, 1, tzinfo=timezone.utc)
    try:
        first = open_charge(unit_id, "tenant_x", period, 500000.0, due)
        second = open_charge(unit_id, "tenant_x", period, 500000.0, due)
        assert first, "first open should return an id"
        assert second == "", "duplicate (unit_id, period) must be rejected, not double-charged"
        assert _col("estate_rent_ledger").count_documents(
            {"unit_id": unit_id, "period": period}
        ) == 1
    finally:
        _col("estate_rent_ledger").delete_many({"unit_id": unit_id})
