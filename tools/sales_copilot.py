"""
Sales Copilot signal pack for client portals.

Turns inbound replies + queued HITL drafts into a compact "next action" view.
Read-only: sending still goes through the existing portal approval endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from database import get_db


_INTENT_RANK = {
    "interested": 0,
    "price_question": 1,
    "question": 2,
    "referral": 3,
    "not_now": 4,
    "unknown": 5,
    "opted_out": 9,
}


def _iso(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else None


def _contact_query(contact_id: Any) -> dict:
    if isinstance(contact_id, ObjectId):
        return {"_id": contact_id}
    try:
        return {"_id": ObjectId(str(contact_id))}
    except Exception:
        return {"_id": contact_id}


def _suggested_action(intent: str, has_draft: bool) -> str:
    if has_draft:
        return "Review and send the drafted reply"
    if intent in ("interested", "price_question"):
        return "Call or send price/details now"
    if intent == "question":
        return "Answer the question, then ask one qualifier"
    if intent == "referral":
        return "Thank them and ask for the referred contact"
    if intent == "not_now":
        return "Schedule a softer follow-up"
    if intent == "opted_out":
        return "Do not contact again"
    return "Review conversation"


def _priority(intent: str, hot_lead: bool, urgency: str | None, has_draft: bool) -> str:
    if intent == "opted_out":
        return "closed"
    if hot_lead or urgency == "high" or intent in ("interested", "price_question"):
        return "hot"
    if has_draft or intent in ("question", "referral"):
        return "warm"
    return "watch"


def sales_copilot_for(client_name: str, days: int = 14, limit: int = 12) -> dict[str, Any]:
    """
    Return recent inbound threads needing attention for one client.

    Scope is intentionally strict: replies are resolved through contacts, then
    contacts.client_name must match this portal's client_name.
    """
    db = get_db()
    if "replies" not in db.list_collection_names() or "contacts" not in db.list_collection_names():
        return {"summary": {"hot": 0, "warm": 0, "drafts": 0, "total": 0}, "threads": []}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    approvals = db["pending_approvals"] if "pending_approvals" in db.list_collection_names() else None
    contacts = db["contacts"]

    rows = (
        db["replies"]
        .find(
            {"received_at": {"$gte": since}},
            {
                "contact_id": 1,
                "contact_name": 1,
                "sender": 1,
                "channel": 1,
                "text": 1,
                "intent": 1,
                "urgency": 1,
                "hot_lead": 1,
                "summary": 1,
                "received_at": 1,
            },
        )
        .sort("received_at", -1)
        .limit(300)
    )

    seen: set[str] = set()
    threads: list[dict[str, Any]] = []

    for r in rows:
        cid = r.get("contact_id")
        if not cid:
            continue
        key = str(cid)
        if key in seen:
            continue

        contact = contacts.find_one(
            _contact_query(cid),
            {"client_name": 1, "name": 1, "phone": 1, "email": 1, "vertical": 1, "status": 1},
        )
        if not contact or (contact.get("client_name") or "").strip() != client_name:
            continue

        draft = None
        if approvals is not None:
            draft = approvals.find_one(
                {"contact_id": contact["_id"], "client_name": client_name, "status": "pending"},
                {"message": 1, "channel": 1, "created_at": 1},
                sort=[("created_at", -1)],
            )

        intent = r.get("intent") or "unknown"
        urgency = r.get("urgency") or "low"
        hot_lead = bool(r.get("hot_lead"))
        has_draft = draft is not None
        pri = _priority(intent, hot_lead, urgency, has_draft)

        threads.append(
            {
                "contact_id": key,
                "contact_name": contact.get("name") or r.get("contact_name") or r.get("sender") or "Unknown",
                "phone": contact.get("phone") or r.get("sender") or "",
                "email": contact.get("email") or "",
                "channel": r.get("channel") or draft.get("channel") if draft else r.get("channel") or "",
                "intent": intent,
                "urgency": urgency,
                "priority": pri,
                "hot_lead": hot_lead,
                "reply_text": (r.get("text") or "")[:360],
                "summary": r.get("summary") or "",
                "received_at": _iso(r.get("received_at")),
                "suggested_action": _suggested_action(intent, has_draft),
                "approval_id": str(draft["_id"]) if draft else None,
                "draft_preview": (draft.get("message") or "")[:360] if draft else "",
                "draft_created_at": _iso(draft.get("created_at")) if draft else None,
            }
        )
        seen.add(key)
        if len(threads) >= limit:
            break

    threads.sort(key=lambda t: (_INTENT_RANK.get(t["intent"], 8), t.get("received_at") or ""), reverse=False)

    summary = {
        "hot": sum(1 for t in threads if t["priority"] == "hot"),
        "warm": sum(1 for t in threads if t["priority"] == "warm"),
        "drafts": sum(1 for t in threads if t.get("approval_id")),
        "total": len(threads),
    }
    return {"summary": summary, "threads": threads}


def operator_copilot(days: int = 14, per_client_limit: int = 8) -> dict[str, Any]:
    """
    Cross-client Sales Copilot for the admin/operator dashboard.

    Returns one bucket per active client with the same thread shape as
    sales_copilot_for(), plus a roll-up summary. Operator approve/skip
    controls hit /api/v1/approvals/{id}/approve|skip (admin-auth).
    """
    db = get_db()
    clients_col = db["clients"]
    clients = list(clients_col.find(
        {"active": True},
        {"name": 1, "vertical": 1},
    ).sort("name", 1))

    buckets: list[dict[str, Any]] = []
    roll = {"hot": 0, "warm": 0, "drafts": 0, "total": 0}
    for c in clients:
        name = c.get("name") or ""
        if not name:
            continue
        pack = sales_copilot_for(name, days=days, limit=per_client_limit)
        if pack["summary"]["total"] == 0:
            continue
        buckets.append({
            "client": name,
            "vertical": c.get("vertical") or "general",
            "summary": pack["summary"],
            "threads": pack["threads"],
        })
        for k in roll:
            roll[k] += pack["summary"].get(k, 0)

    # Surface noisiest clients first (most pending action)
    buckets.sort(key=lambda b: (-b["summary"]["hot"], -b["summary"]["drafts"], -b["summary"]["total"]))
    return {"summary": roll, "clients": buckets, "days": days}
