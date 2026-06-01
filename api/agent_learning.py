"""
Agent Learning surface — T0.4 close-out UI back-end.

Outcome Loop has been running invisibly since commit 8fb7cdb:
  - Every approved draft tagged with an outcome_id
  - Inbound classifier resolves outcomes to win / miss
  - Nightly silence sweep at 02:00 Lagos
  - Weekly distil at Sun 23:00 Lagos -> writes clients.prompt_addendum

This module exposes that work so owners can see EYO improving.

Routes:
  GET  /api/v1/portal/agent-learning/{token}      token-gated, per-client
  GET  /api/v1/admin/agent-learning/{client_id}   admin Basic Auth, any client
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from auth import require_auth
from database import get_db
from services.outcome_learning import client_outcome_stats, get_addendum_for_client


router = APIRouter(tags=["AgentLearning"])


def _iso(v) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else (v if isinstance(v, str) else None)


def _get_client_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    return get_db()["clients"].find_one({"portal_token": token, "active": True})


def _get_client_by_id(client_id: str) -> Optional[dict]:
    if not client_id:
        return None
    try:
        return get_db()["clients"].find_one({"_id": ObjectId(client_id)})
    except Exception:
        return get_db()["clients"].find_one({"name": client_id})


def _build_payload(client: dict, *, include_recent: bool = True) -> dict:
    """Shared payload shape for both portal and admin endpoints."""
    cid     = str(client["_id"])
    stats   = client_outcome_stats(cid, lookback_days=30)
    addend  = get_addendum_for_client(client)
    payload = {
        "client_name":         client.get("name"),
        "vertical":            client.get("vertical"),
        "stats":               stats,
        "addendum":            addend,
        "addendum_updated_at": _iso(client.get("prompt_addendum_at")),
        "distil_id":           client.get("prompt_addendum_distil"),
    }

    if include_recent:
        col = get_db()["outcomes"]
        recent = list(col.find(
            {"client_id": cid, "status": {"$in": ["win", "miss"]}},
            {"status": 1, "win_signal": 1, "miss_reason": 1,
             "draft_message": 1, "resolved_at": 1, "source": 1},
        ).sort("resolved_at", -1).limit(15))
        payload["recent"] = [
            {
                "status":       r.get("status"),
                "signal":       r.get("win_signal") or r.get("miss_reason"),
                "draft_excerpt": (r.get("draft_message") or "")[:140],
                "source":       r.get("source"),
                "resolved_at":  _iso(r.get("resolved_at")),
            }
            for r in recent
        ]
    return payload


@router.get("/portal/agent-learning/{token}")
async def portal_agent_learning(token: str):
    """Token-gated. The client sees their own outcomes only (the cookie/token
    is the isolation boundary; downstream queries are scoped by client_id)."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    return _build_payload(client, include_recent=True)


@router.get("/admin/agent-learning/{client_id}", dependencies=[Depends(require_auth)])
async def admin_agent_learning(client_id: str):
    """Admin Basic Auth. Same payload shape, addressable by client id or name."""
    client = _get_client_by_id(client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return _build_payload(client, include_recent=True)


@router.get("/admin/needs-attention", dependencies=[Depends(require_auth)])
async def admin_needs_attention():
    """Founder triage feed: aging approvals, WA-disconnected clients, at-risk
    margin, failed jobs. Powers the admin 'Needs Attention' tab."""
    from services.admin_attention import needs_attention
    return needs_attention()


@router.get("/admin/agent-learning", dependencies=[Depends(require_auth)])
async def admin_agent_learning_summary():
    """Cross-client wins/misses summary for the Control Tower dashboard tab.
    One row per active client with last-30d totals + addendum freshness."""
    db = get_db()
    rows = []
    for c in db["clients"].find(
        {"active": True},
        {"name": 1, "vertical": 1, "prompt_addendum": 1, "prompt_addendum_at": 1},
    ).sort("name", 1):
        cid = str(c["_id"])
        try:
            stats = client_outcome_stats(cid, lookback_days=30)
        except Exception:
            stats = {"wins": 0, "misses": 0, "pending": 0}
        rows.append({
            "client_id":         cid,
            "client_name":       c.get("name"),
            "vertical":          c.get("vertical"),
            "wins":              int(stats.get("wins") or 0),
            "misses":            int(stats.get("misses") or 0),
            "pending":           int(stats.get("pending") or 0),
            "win_rate":          (stats.get("win_rate")
                                   if isinstance(stats.get("win_rate"), (int, float))
                                   else (stats["wins"] / max(1, stats["wins"] + stats["misses"]))
                                        if (stats.get("wins") or stats.get("misses")) else 0.0),
            "has_addendum":      bool(c.get("prompt_addendum")),
            "addendum_updated":  _iso(c.get("prompt_addendum_at")),
        })
    return {"clients": rows, "count": len(rows)}
