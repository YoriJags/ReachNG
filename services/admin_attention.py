"""
Admin "Needs Attention" aggregator — the founder's triage surface.

Answers "what is broken / who needs help right now" by pulling four live signals:
  • aging_approvals — pending HITL drafts older than AGING_HOURS (going stale)
  • wa_disconnected — active clients whose WhatsApp session expired
  • at_risk_margin  — clients running below the margin floor (billing_table at_risk)
  • failed_jobs     — recent error/crashed scheduler + integration log entries

Read-only; admin-auth gated at the route. Every block is defensive so one bad
collection never blanks the whole panel.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import structlog

from database import get_db

log = structlog.get_logger()

AGING_HOURS = 12


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else (v if isinstance(v, str) else None)


def _aging_approvals(db, now) -> dict:
    out = {"count": 0, "oldest_hours": 0, "items": []}
    try:
        if "pending_approvals" not in db.list_collection_names():
            return out
        cutoff = now - timedelta(hours=AGING_HOURS)
        q = {"status": "pending", "created_at": {"$lt": cutoff}}
        out["count"] = db["pending_approvals"].count_documents(q)
        for d in db["pending_approvals"].find(
            q, {"client_name": 1, "contact_name": 1, "created_at": 1}
        ).sort("created_at", 1).limit(8):
            age = (now - d["created_at"]).total_seconds() / 3600 if d.get("created_at") else 0
            out["items"].append({
                "client":  d.get("client_name") or "—",
                "contact": d.get("contact_name") or "—",
                "hours":   round(age, 1),
            })
        if out["items"]:
            out["oldest_hours"] = max(i["hours"] for i in out["items"])
    except Exception as e:
        log.warning("attention_aging_failed", error=str(e))
    return out


def _wa_disconnected(db) -> dict:
    out = {"count": 0, "clients": []}
    try:
        for c in db["clients"].find(
            {"active": True, "wa_session_expired_at": {"$ne": None}},
            {"name": 1, "wa_session_expired_at": 1},
        ).limit(25):
            out["clients"].append({
                "name":  c.get("name") or "—",
                "since": _iso(c.get("wa_session_expired_at")),
            })
        out["count"] = len(out["clients"])
    except Exception as e:
        log.warning("attention_wa_failed", error=str(e))
    return out


def _at_risk_margin() -> dict:
    out = {"count": 0, "clients": []}
    try:
        from services.usage_meter import billing_table
        for r in billing_table(days=30):
            if r.get("at_risk"):
                out["clients"].append({
                    "name":       r.get("name") or "—",
                    "margin_pct": r.get("margin_pct"),
                    "plan":       r.get("plan"),
                })
        out["count"] = len(out["clients"])
    except Exception as e:
        log.warning("attention_margin_failed", error=str(e))
    return out


def _failed_jobs() -> dict:
    out = {"count": 0, "items": []}
    try:
        from tools.log_buffer import get_recent
        seen = set()
        for e in reversed(get_recent(200)):
            ev = str(e.get("event") or "")
            is_fail = (e.get("level") in ("error", "critical")) or ev.endswith("_crashed")
            if not is_fail or ev in seen:
                continue
            seen.add(ev)
            out["items"].append({"event": ev, "ts": e.get("ts"), "level": e.get("level")})
            if len(out["items"]) >= 10:
                break
        out["count"] = len(out["items"])
    except Exception as e:
        log.warning("attention_jobs_failed", error=str(e))
    return out


def needs_attention() -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    aging = _aging_approvals(db, now)
    wa    = _wa_disconnected(db)
    risk  = _at_risk_margin()
    jobs  = _failed_jobs()
    return {
        "total":           aging["count"] + wa["count"] + risk["count"] + jobs["count"],
        "aging_approvals": aging,
        "wa_disconnected": wa,
        "at_risk_margin":  risk,
        "failed_jobs":     jobs,
        "aging_hours":     AGING_HOURS,
        "generated_at":    _iso(now),
    }
