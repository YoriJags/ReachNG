"""HITL action proposals — the owner-tap gate for things EYO DOES (not says).

A *draft* is a message EYO wants to SEND. An *action* is something EYO wants to
DO in the client's own tools — book a viewing in their Google Calendar, push a
lead to their CRM, file a receipt in their Sheet. Same non-negotiable rule:
nothing happens without the owner's tap.

Action proposals share the ``pending_approvals`` collection (so they surface in
the existing queue infra) but carry ``kind="action"`` and a structured
``action = {provider, tool, arguments}`` plus a human ``summary``. On approval,
``execute_approved_action`` runs the MCP tool via ``tools.mcp_client`` —
deterministic code, never a re-decision by the model.

DORMANT seam: ``queue_action`` refuses unless ``connections.mcp_enabled()`` is
on AND the client has an enabled connection for the provider. With the flag off
(the default) nothing queues, so nothing can ever execute. See docs/MCP_ACTIONS.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from bson import ObjectId

from database import get_db
from services import connections

log = structlog.get_logger()

ACTION_EXPIRY_HOURS = 72


class ActionStatus:
    PENDING  = "pending"
    APPROVED = "approved"
    EXECUTED = "executed"
    FAILED   = "failed"
    SKIPPED  = "skipped"


class McpActionsDisabled(RuntimeError):
    """Raised when an action is queued while the action layer is switched off."""
    def __init__(self):
        super().__init__(
            "EYO action layer is off — set MCP_ACTIONS_ENABLED to enable. No "
            "action was queued.")


class McpConnectionMissing(RuntimeError):
    """Raised when a client has no enabled connection for the action's provider."""
    def __init__(self, client_name: str, provider: str):
        self.client_name = client_name
        self.provider = provider
        super().__init__(
            f"No enabled '{provider}' connection for '{client_name}'. Connect it "
            f"first before EYO can act in it.")


def _approvals():
    return get_db()["pending_approvals"]


# ─── Queue (propose) ──────────────────────────────────────────────────────────

def queue_action(
    client_name: str,
    provider: str,
    tool: str,
    arguments: dict,
    summary: str,
    *,
    vertical: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_id: Optional[str] = None,
) -> str:
    """Stage an action for the owner to approve. Returns the approval _id.

    Raises McpActionsDisabled if the flag is off, or McpConnectionMissing if the
    client hasn't connected that provider. Both are surfaced to the caller — an
    action is NEVER silently dropped or silently executed.
    """
    if not connections.mcp_enabled():
        raise McpActionsDisabled()

    # Must resolve to a live, enabled connection — proves the client opted in
    # before we ever offer to act in their system.
    conn = connections.resolve_connection(client_name, provider)
    if not conn:
        raise McpConnectionMissing(client_name, provider)

    now = datetime.now(timezone.utc)
    doc = {
        "kind":         "action",            # distinguishes from message drafts
        "client_name":  client_name,
        "vertical":     vertical,
        "contact_name": contact_name,
        "contact_id":   contact_id,
        "action": {
            "provider":  provider,
            "tool":      tool,
            "arguments": arguments or {},
        },
        "summary":      summary,             # human-readable card text
        "status":       ActionStatus.PENDING,
        "created_at":   now,
        "expires_at":   now + timedelta(hours=ACTION_EXPIRY_HOURS),
        "actioned_at":  None,
        "executed_at":  None,
        "action_result": None,
    }
    res = _approvals().insert_one(doc)
    log.info("mcp_action_queued", client=client_name, provider=provider, tool=tool)
    return str(res.inserted_id)


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_pending_actions(client_name: Optional[str] = None, limit: int = 50) -> list[dict]:
    now = datetime.now(timezone.utc)
    q: dict = {
        "kind": "action",
        "status": ActionStatus.PENDING,
        "$or": [{"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
    }
    if client_name:
        import re
        q["client_name"] = {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}
    return list(_approvals().find(q).sort("created_at", -1).limit(limit))


def _get_action(approval_id: str) -> Optional[dict]:
    doc = _approvals().find_one({"_id": ObjectId(approval_id)})
    if not doc or doc.get("kind") != "action":
        return None
    return doc


# ─── Approve / skip ───────────────────────────────────────────────────────────

def approve_action(approval_id: str) -> Optional[dict]:
    """Mark an action approved (ready to execute). Returns the doc, or None if it
    isn't an action, doesn't exist, or has expired."""
    doc = _get_action(approval_id)
    if not doc:
        return None
    if doc.get("status") != ActionStatus.PENDING:
        return None
    expires_at = doc.get("expires_at")
    if expires_at and datetime.now(timezone.utc) > expires_at:
        _set_status(approval_id, ActionStatus.SKIPPED)
        log.warning("mcp_action_expired_on_approve", approval_id=approval_id)
        return None
    return _set_status(approval_id, ActionStatus.APPROVED)


def skip_action(approval_id: str) -> Optional[dict]:
    if not _get_action(approval_id):
        return None
    return _set_status(approval_id, ActionStatus.SKIPPED)


def _set_status(approval_id: str, status: str) -> Optional[dict]:
    _approvals().update_one(
        {"_id": ObjectId(approval_id)},
        {"$set": {"status": status, "actioned_at": datetime.now(timezone.utc)}},
    )
    return _approvals().find_one({"_id": ObjectId(approval_id)})


# ─── Execute (only ever after approval) ──────────────────────────────────────

async def execute_approved_action(approval_doc: dict) -> dict:
    """Run an approved action against the client's MCP server. Deterministic —
    re-reads the structured tool call the owner approved and dispatches it; never
    asks the model. Records the result on the doc. Never raises into the caller.

    Returns the executor result dict ({ok, result} | {ok: False, error}).
    """
    approval_id = approval_doc.get("_id")
    action = approval_doc.get("action") or {}
    provider = action.get("provider")
    tool = action.get("tool")
    arguments = action.get("arguments") or {}
    client_name = approval_doc.get("client_name")

    if approval_doc.get("status") != ActionStatus.APPROVED:
        log.warning("mcp_execute_not_approved", approval_id=str(approval_id),
                    status=approval_doc.get("status"))
        return {"ok": False, "error": "action not approved"}

    conn = connections.resolve_connection(client_name, provider)
    if not conn:
        _record_result(approval_id, ok=False, error="connection missing or disabled")
        return {"ok": False, "error": "connection missing or disabled"}

    from tools import mcp_client
    result = await mcp_client.call_tool(conn, tool, arguments)   # never raises
    _record_result(approval_id, ok=result.get("ok"), result=result.get("result"),
                   error=result.get("error"))
    return result


def _record_result(approval_id, *, ok: bool, result=None, error=None) -> None:
    try:
        patch = {
            "status":      ActionStatus.EXECUTED if ok else ActionStatus.FAILED,
            "executed_at": datetime.now(timezone.utc),
            "action_result": {"ok": bool(ok), "result": result, "error": error},
        }
        _approvals().update_one({"_id": ObjectId(str(approval_id))}, {"$set": patch})
        if ok:
            log.info("mcp_action_executed", approval_id=str(approval_id))
        else:
            log.error("mcp_action_execute_failed", approval_id=str(approval_id), error=error)
    except Exception as e:
        log.error("mcp_action_record_failed", error=str(e))
