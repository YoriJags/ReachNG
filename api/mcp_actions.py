"""EYO action layer — admin API (MCP connectors + HITL action queue).

Admin-only (Basic Auth). Lets the founder register a client's MCP server
connection, test connectivity, and approve/skip the actions EYO proposes. The
action *execution* still only ever happens after a tap here — same kill-switch
discipline as the message-draft approvals.

Everything is gated on MCP_ACTIONS_ENABLED. With the flag off, /status reports
disabled and the queue stays empty. See docs/MCP_ACTIONS.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from auth import require_auth as _admin_auth
from services import connections, crypto, mcp_actions
from tools import mcp_client

router = APIRouter(prefix="/api/v1/admin/mcp", tags=["EYO Actions (MCP)"])


def _serialise(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    cid = doc.get("contact_id")
    if cid is not None:
        doc["contact_id"] = str(cid)
    return doc


# ─── Status ───────────────────────────────────────────────────────────────────

@router.get("/status")
async def status(_: str = Depends(_admin_auth)):
    """Is the action layer on, can we encrypt creds, is the MCP client importable."""
    return {
        "enabled":          connections.mcp_enabled(),
        "encryption_ready": crypto.available(),
        "client_ready":     mcp_client.available(),
        "known_providers":  connections.KNOWN_PROVIDERS,
    }


# ─── Connections ──────────────────────────────────────────────────────────────

class ConnectionPayload(BaseModel):
    client_name: str
    provider: str
    url: str
    auth_type: str = "bearer"        # "bearer" | "none"
    token: str | None = None
    enabled: bool = True


class ConnectionRef(BaseModel):
    client_name: str
    provider: str


@router.get("/connections")
async def list_connections(client: str | None = None, _: str = Depends(_admin_auth)):
    return connections.list_connections(client_name=client)


@router.post("/connections")
async def set_connection(payload: ConnectionPayload, _: str = Depends(_admin_auth)):
    try:
        return connections.set_connection(
            payload.client_name, payload.provider, payload.url,
            auth_type=payload.auth_type, token=payload.token, enabled=payload.enabled,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@router.post("/connections/delete")
async def delete_connection(ref: ConnectionRef, _: str = Depends(_admin_auth)):
    ok = connections.delete_connection(ref.client_name, ref.provider)
    if not ok:
        raise HTTPException(404, "Connection not found")
    return {"success": True}


@router.post("/connections/test")
async def test_connection(ref: ConnectionRef, _: str = Depends(_admin_auth)):
    """Connect to the client's MCP server and list its tools — proves the URL +
    credential work before EYO ever proposes an action against it."""
    if not connections.mcp_enabled():
        raise HTTPException(409, "Action layer is off (MCP_ACTIONS_ENABLED)")
    conn = connections.resolve_connection(ref.client_name, ref.provider)
    if not conn:
        raise HTTPException(404, "No enabled connection for that client/provider")
    if not mcp_client.available():
        raise HTTPException(503, "MCP client library not installed")
    try:
        tools = mcp_client.list_tools_sync(conn)
    except Exception as e:
        raise HTTPException(502, f"Connection test failed: {e}")
    return {"success": True, "provider": ref.provider, "tools": tools}


# ─── Action queue ─────────────────────────────────────────────────────────────

@router.get("/actions")
async def list_actions(client: str | None = None, _: str = Depends(_admin_auth)):
    return [_serialise(a) for a in mcp_actions.get_pending_actions(client_name=client)]


@router.post("/actions/{approval_id}/approve")
async def approve_action(approval_id: str, background_tasks: BackgroundTasks,
                         _: str = Depends(_admin_auth)):
    doc = mcp_actions.approve_action(approval_id)
    if not doc:
        raise HTTPException(409, "Action not found, not pending, or expired")
    background_tasks.add_task(mcp_actions.execute_approved_action, doc)
    return {"success": True, "status": "approved",
            "summary": doc.get("summary"), "provider": (doc.get("action") or {}).get("provider")}


@router.post("/actions/{approval_id}/skip")
async def skip_action(approval_id: str, _: str = Depends(_admin_auth)):
    doc = mcp_actions.skip_action(approval_id)
    if not doc:
        raise HTTPException(404, "Action not found")
    return {"success": True, "status": "skipped"}
