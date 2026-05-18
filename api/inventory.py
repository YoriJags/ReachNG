"""
Inventory portal — owner-facing page + CRUD routes.

Lives at /portal/{token}/inventory. Token-gated.
Admin can launch the same page for any client from the dashboard.
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from auth import require_auth as _require_admin_auth
from database import get_db
from services.inventory import (
    InventoryItem,
    count_items,
    delete_item,
    list_items,
    upsert_item,
)

log = structlog.get_logger()
router = APIRouter(tags=["Inventory"])


def _clients():
    return get_db()["clients"]


def _get_client_by_token(token: str) -> Optional[dict]:
    return _clients().find_one({"portal_token": token, "active": True})


def _client_id(c: dict) -> str:
    return str(c["_id"])


# ─── Portal page ─────────────────────────────────────────────────────────

@router.get("/portal/{token}/inventory", response_class=HTMLResponse)
async def portal_inventory_page(token: str, request: Request):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal/inventory.html", {
        "token":       token,
        "client_name": client.get("name", "your business"),
    })


# ─── Portal CRUD (token-gated) ───────────────────────────────────────────

@router.get("/api/v1/portal/{token}/inventory")
async def portal_list_inventory(token: str):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)
    return {
        "items": list_items(cid),
        "counts": count_items(cid),
    }


@router.post("/api/v1/portal/{token}/inventory")
async def portal_create_inventory(token: str, item: InventoryItem):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)
    try:
        new_id = upsert_item(cid, item_id=None, item=item)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "item_id": new_id}


@router.put("/api/v1/portal/{token}/inventory/{item_id}")
async def portal_update_inventory(token: str, item_id: str, item: InventoryItem):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)
    try:
        upsert_item(cid, item_id=item_id, item=item)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "item_id": item_id}


@router.delete("/api/v1/portal/{token}/inventory/{item_id}")
async def portal_delete_inventory(token: str, item_id: str):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)
    ok = delete_item(cid, item_id)
    if not ok:
        raise HTTPException(404, "item not found")
    return {"ok": True}


# ─── Admin (Basic Auth) — fetch counts to surface on dashboard ────────────

@router.get("/api/v1/admin/clients/{client_id}/inventory/counts")
async def admin_inventory_counts(client_id: str, _: str = Depends(_require_admin_auth)):
    return count_items(client_id)
