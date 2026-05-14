"""
Multi-tenant isolation test suite for the client_memory layer.

Runs:
  1. Static contract — fetch_facts / fetch_memory_block / store_fact MUST raise
     MemoryScopeViolationError when called without a client_id.
  2. Synthetic cross-client probe — writes a fact under client A, then queries
     under client B with the same phone. MUST return zero matching facts.
  3. Self-test consistency — `isolation_self_test()` MUST report pass=True for
     every existing fact in the database.

Run via:
  python -m tests.test_isolation
Or import and call run_isolation_suite() from the scheduler.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger()


# ─── Contract guards (no DB needed) ───────────────────────────────────────────

def _expect_raises(exc_type, fn, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as e:
        log.error("isolation_unexpected_exception", expected=exc_type.__name__, got=type(e).__name__)
        return False
    return False


def test_scope_guards() -> dict:
    """Every memory function MUST refuse calls without (client_id, contact_phone)."""
    from services.client_memory import (
        store_fact, fetch_facts, fetch_memory_block, learn_from_inbound,
        MemoryScopeViolationError,
    )
    results: dict[str, bool] = {}
    results["store_fact_no_client"] = _expect_raises(
        MemoryScopeViolationError, store_fact, "", "+2348100000000", "context", "x",
    )
    results["store_fact_no_phone"] = _expect_raises(
        MemoryScopeViolationError, store_fact, "client_A", "", "context", "x",
    )
    results["fetch_facts_no_client"] = _expect_raises(
        MemoryScopeViolationError, fetch_facts, None, "+2348100000000",
    )
    results["fetch_block_no_phone"] = _expect_raises(
        MemoryScopeViolationError, fetch_memory_block, "client_A", "",
    )
    results["learn_no_client"] = _expect_raises(
        MemoryScopeViolationError, learn_from_inbound, "", "+2348100000000", "hello",
    )
    return {"pass": all(results.values()), "details": results}


# ─── Synthetic cross-client probe (writes to DB) ──────────────────────────────

def test_cross_client_probe() -> dict:
    """Write a fact under a synthetic client_A + phone P, then query under
    synthetic client_B + phone P. The query MUST return zero results.

    All synthetic data is tagged with a probe_id and deleted at the end.
    """
    from services.client_memory import (
        store_fact, fetch_facts, get_memory_col, get_audit_col,
    )
    probe_id = f"isolation_probe_{secrets.token_hex(6)}"
    client_a = f"{probe_id}_client_A"
    client_b = f"{probe_id}_client_B"
    phone = f"+234{secrets.randbelow(10**9):09d}"

    try:
        # Seed: write under client_A
        fact_id = store_fact(
            client_id=client_a,
            contact_phone=phone,
            fact_type="context",
            fact_text=f"{probe_id} — sensitive note for client A only",
            requested_by="isolation_probe",
        )
        assert fact_id, "seed write returned no id"

        # Probe: query under client_B with the same phone
        leak = fetch_facts(
            client_id=client_b,
            contact_phone=phone,
            requested_by="isolation_probe",
        )
        leaked_count = len(leak)

        # Same client should still see it (control)
        sanity = fetch_facts(
            client_id=client_a,
            contact_phone=phone,
            requested_by="isolation_probe",
        )
        same_client_count = len(sanity)

        return {
            "pass":                leaked_count == 0 and same_client_count >= 1,
            "leaked_to_client_b":  leaked_count,
            "same_client_visible": same_client_count,
            "probe_id":            probe_id,
        }
    finally:
        # Always clean up the synthetic data
        try:
            get_memory_col().delete_many({"client_id": {"$in": [client_a, client_b]}})
            get_audit_col().delete_many({"client_id": {"$in": [client_a, client_b]}})
        except Exception as e:
            log.warning("isolation_probe_cleanup_failed", error=str(e))


# ─── Database-wide self-test ──────────────────────────────────────────────────

def test_db_self_test() -> dict:
    from services.client_memory import isolation_self_test
    return isolation_self_test()


# ─── Suite runner ─────────────────────────────────────────────────────────────

def run_isolation_suite() -> dict:
    """Run all three isolation checks. Returns a single report dict suitable
    for logging, dashboard surfacing, and alerting."""
    started_at = datetime.now(timezone.utc).isoformat()
    contract = test_scope_guards()
    probe    = test_cross_client_probe()
    self_t   = test_db_self_test()

    overall = bool(contract.get("pass") and probe.get("pass") and self_t.get("pass"))
    report: dict[str, Any] = {
        "pass":          overall,
        "started_at":    started_at,
        "finished_at":   datetime.now(timezone.utc).isoformat(),
        "scope_guards":  contract,
        "cross_client":  probe,
        "self_test":     self_t,
    }
    if overall:
        log.info("isolation_suite_ok")
    else:
        log.error("isolation_suite_FAILED", **{k: report[k] for k in ("scope_guards", "cross_client", "self_test")})
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(run_isolation_suite(), indent=2, default=str))
