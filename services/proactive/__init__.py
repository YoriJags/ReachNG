"""
Proactive Intelligence (T0.5) — the "agent acts without being asked" moat.

Each behaviour is a function that finds a timely opportunity and drafts to the
HITL queue. A single daily scheduler job (scheduler.py::_proactive_sweep) calls
run_proactive_sweep().

Behaviours:
  • festivals  — festive-window re-engagement of dormant customers   (shipped)
  • birthdays  — nudge on customer birthday facts in client_memory    (TODO)
  • capacity   — quiet-night fill prompts for hospitality             (TODO)
  • reminders  — booking/appointment reminders                        (TODO)

Stale-lead revival is intentionally NOT here — it already ships via Revenue
Rescue (services/money_leak.rescue_targets + /run-resurrection).

Per-client opt-out: clients.proactive_enabled == False disables it (default on).
"""
from __future__ import annotations

import structlog

from database import get_db
from services.proactive.festivals import active_festival, draft_festival_nudges

log = structlog.get_logger()


def run_proactive_sweep() -> dict:
    """Daily orchestrator. v1 runs the festival behaviour when a window is open."""
    fest = active_festival()
    if not fest:
        return {"skipped": "no_festival_window"}

    db = get_db()
    clients = db["clients"].find(
        {"active": True},
        {"name": 1, "vertical": 1, "signature": 1, "proactive_enabled": 1},
    )

    touched, total = 0, 0
    for c in clients:
        if c.get("proactive_enabled") is False:     # opt-out; default on
            continue
        try:
            n = draft_festival_nudges(c, fest)
            if n:
                touched += 1
                total += n
        except Exception as e:
            log.warning("proactive_sweep_client_failed", client=c.get("name"), error=str(e))

    result = {"festival": fest["key"], "clients_touched": touched, "drafts_queued": total}
    log.info("proactive_sweep_done", **result)
    return result
