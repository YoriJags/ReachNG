"""
Business Brief API — admin + portal routers.

Admin (Basic Auth):
  GET    /admin/brief/primers                         — list all vertical primers
  GET    /admin/brief/primers/{vertical}              — fetch one primer
  PUT    /admin/brief/primers/{vertical}              — upsert a primer
  GET    /admin/brief/clients/{name}                  — fetch client brief + health
  PUT    /admin/brief/clients/{name}                  — overwrite client brief
  POST   /admin/brief/clients/{name}/intake           — AI-assisted draft from URL+free-text
  GET    /admin/brief/clients/{name}/health           — completeness gate

Portal (token-gated):
  GET    /portal-brief/{token}                        — fetch this client's brief + health
  PUT    /portal-brief/{token}                        — save brief edits
  POST   /portal-brief/{token}/intake                 — AI-assisted draft (client supplies URL/text)
  GET    /portal-brief/{token}/health                 — health for the in-portal banner
"""
from __future__ import annotations

import re
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import get_db
from services.brief import (
    BusinessBrief,
    VerticalPrimer,
    get_brief,
    update_brief,
    get_primer,
    upsert_primer,
    list_primers,
    brief_health,
    list_brief_history,
    restore_brief_version,
)
from services.brief.intake import assist_intake


# Admin (Basic Auth — wired with main app prefix /api/v1)
router = APIRouter(prefix="/admin/brief", tags=["Business Brief — Admin"])

# Portal (token-gated, no Basic Auth)
public_router = APIRouter(prefix="/portal-brief", tags=["Business Brief — Portal"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_client_by_token(token: str) -> dict:
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    return client


def _get_client_by_name(name: str) -> dict:
    client = get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{name}' not found")
    return client


# ─── Schemas ──────────────────────────────────────────────────────────────────

class IntakePayload(BaseModel):
    url: Optional[str] = None
    free_text: Optional[str] = None
    questions_answers: Optional[dict[str, str]] = None
    save: bool = Field(default=False, description="If true, also write the structured draft to the client doc")


# ─── Admin: vertical primers ─────────────────────────────────────────────────

@router.get("/primers")
async def admin_list_primers():
    primers = list_primers()
    for p in primers:
        p.pop("_id", None)
    return {"primers": primers}


@router.get("/primers/{vertical}")
async def admin_get_primer(vertical: str):
    p = get_primer(vertical)
    if not p:
        raise HTTPException(404, f"No primer for vertical '{vertical}'")
    p.pop("_id", None)
    return p


@router.put("/primers/{vertical}")
async def admin_upsert_primer(vertical: str, primer: VerticalPrimer):
    if primer.vertical and primer.vertical != vertical:
        raise HTTPException(400, "vertical mismatch between path and body")
    primer.vertical = vertical
    res = upsert_primer(primer)
    return {"success": True, **res}


# ─── Admin: client briefs ────────────────────────────────────────────────────

@router.get("/clients/{name}")
async def admin_get_client_brief(name: str):
    client = _get_client_by_name(name)
    info = get_brief(client_name=name)
    health = brief_health(client_name=name)
    return {
        "client_id": str(client["_id"]),
        "client_name": client.get("name"),
        "vertical": client.get("vertical"),
        "business_brief": (info or {}).get("business_brief") or {},
        "closer_brief": (info or {}).get("closer_brief") or {},
        "health": health,
    }


@router.put("/clients/{name}")
async def admin_put_client_brief(name: str, brief: BusinessBrief):
    _get_client_by_name(name)  # 404 if missing
    res = update_brief(brief=brief, client_name=name)
    health = brief_health(client_name=name)
    return {"success": True, **res, "health": health}


@router.get("/clients/{name}/health")
async def admin_health(name: str):
    return brief_health(client_name=name)


@router.get("/clients/{name}/history")
async def admin_brief_history(name: str, limit: int = 20):
    """List prior versions of this client's brief, newest first."""
    return list_brief_history(client_name=name, limit=limit)


@router.post("/clients/{name}/restore/{version_id}")
async def admin_brief_restore(name: str, version_id: str):
    """Restore a historical brief version. The current live brief is itself
    snapshotted first, so the rollback is reversible."""
    res = restore_brief_version(version_id=version_id, client_name=name, saved_by="admin")
    if not res:
        raise HTTPException(404, "Version not found or invalid snapshot")
    health = brief_health(client_name=name)
    return {"success": True, **res, "health": health}


@router.post("/clients/{name}/intake")
async def admin_intake(name: str, payload: IntakePayload):
    client = _get_client_by_name(name)
    vertical = client.get("vertical") or "general"
    result = await assist_intake(
        vertical=vertical,
        url=payload.url,
        free_text=payload.free_text,
        questions_answers=payload.questions_answers,
    )
    if payload.save:
        brief = BusinessBrief(**{k: v for k, v in result["brief"].items() if k in BusinessBrief.model_fields})
        update_brief(brief=brief, client_name=name)
    return result


# ─── Portal: client briefs ───────────────────────────────────────────────────

@public_router.get("/{token}")
async def portal_get_brief(token: str):
    client = _get_client_by_token(token)
    info = get_brief(client_id=str(client["_id"]))
    health = brief_health(client_id=str(client["_id"]))
    return {
        "client_name": client.get("name"),
        "vertical": client.get("vertical"),
        "business_brief": (info or {}).get("business_brief") or {},
        "closer_brief": (info or {}).get("closer_brief") or {},
        "health": health,
    }


@public_router.put("/{token}")
async def portal_put_brief(token: str, brief: BusinessBrief):
    client = _get_client_by_token(token)
    res = update_brief(brief=brief, client_id=str(client["_id"]))
    health = brief_health(client_id=str(client["_id"]))
    return {"success": True, **res, "health": health}


@public_router.get("/{token}/health")
async def portal_health(token: str):
    client = _get_client_by_token(token)
    return brief_health(client_id=str(client["_id"]))


@public_router.post("/{token}/intake")
async def portal_intake(token: str, payload: IntakePayload):
    client = _get_client_by_token(token)
    vertical = client.get("vertical") or "general"
    result = await assist_intake(
        vertical=vertical,
        url=payload.url,
        free_text=payload.free_text,
        questions_answers=payload.questions_answers,
    )
    if payload.save:
        brief = BusinessBrief(**{k: v for k, v in result["brief"].items() if k in BusinessBrief.model_fields})
        update_brief(brief=brief, client_id=str(client["_id"]))
    return result
