"""
Client Rules + Scenario activation + Sandbox preview.

Routes:
  Admin (Basic Auth)
    GET    /api/v1/clients/{client_id}/rules
    POST   /api/v1/clients/{client_id}/rules
    PATCH  /api/v1/clients/{client_id}/rules/{rule_id}
    DELETE /api/v1/clients/{client_id}/rules/{rule_id}
    POST   /api/v1/clients/{client_id}/scenarios/activate
    POST   /api/v1/clients/{client_id}/sandbox/preview

  Portal (token)
    GET    /portal/{token}/rules
    POST   /portal/{token}/rules
    PATCH  /portal/{token}/rules/{rule_id}
    DELETE /portal/{token}/rules/{rule_id}
    GET    /portal/{token}/scenarios
    POST   /portal/{token}/scenarios/{scenario_key}/activate
    POST   /portal/{token}/sandbox/preview

All routes scope-lock by client_id (URL param) or portal token. No bypass.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_auth as _admin_auth
from database import get_db
from services.client_rules import (
    add_rule, list_rules, update_rule, delete_rule,
    fetch_rules_block, RulesScopeViolationError,
)
from services.scenario_library import (
    list_for_vertical, list_all, activate_scenario,
)

router = APIRouter(tags=["Client Rules"])


# ─── Models ───────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str
    behavior_text: str = Field(..., min_length=4)
    trigger_keywords: Optional[list[str]] = None
    trigger_intent: Optional[str] = None
    escalate_to_owner: bool = False


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    behavior_text: Optional[str] = None
    trigger_keywords: Optional[list[str]] = None
    trigger_intent: Optional[str] = None
    escalate_to_owner: Optional[bool] = None
    active: Optional[bool] = None


class ActivateScenario(BaseModel):
    scenario_key: str


class SandboxPreview(BaseModel):
    inbound_text: str = Field(..., min_length=2)
    contact_name: Optional[str] = "Guest"
    phone: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_from_token(token: str) -> dict:
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "portal not found")
    return client


def _client_doc_by_id(client_id: str) -> dict:
    from bson import ObjectId
    try:
        client = get_db()["clients"].find_one({"_id": ObjectId(client_id)})
    except Exception:
        client = None
    if not client:
        raise HTTPException(404, "client not found")
    return client


# ─── Sandbox runner (shared between admin + portal) ───────────────────────────

def _run_sandbox(client_doc: dict, inbound_text: str, contact_name: str = "Guest",
                  phone: Optional[str] = None) -> dict:
    """Run the full drafting pipeline without persisting any HITL draft.

    Returns {draft, escalate_flag, fired_rules, kb_hits, memory_block}.
    """
    from agent.brain import generate_b2c_message
    from services.knowledge_base import fetch_kb_block
    from services.client_rules import fetch_rules_block, match_rules
    from services.client_memory import fetch_memory_block

    client_id = str(client_doc["_id"])
    client_name = client_doc.get("name")
    vertical = client_doc.get("vertical") or "general"

    rules_block, escalate = fetch_rules_block(client_id, inbound_text)
    kb_block = fetch_kb_block(client_id, inbound_text)
    mem_block = ""
    if phone:
        try:
            mem_block = fetch_memory_block(client_id=client_id, contact_phone=phone,
                                            requested_by="sandbox_preview")
        except Exception:
            mem_block = ""

    # Build a notes payload that bundles everything (rules + KB + memory)
    notes_pieces = [p for p in (rules_block, kb_block, mem_block) if p]
    notes = "\n\n".join(notes_pieces) if notes_pieces else None

    try:
        out = generate_b2c_message(
            customer_name=contact_name,
            channel="whatsapp",
            vertical=vertical,
            client_name=client_name,
            notes=notes,
            phone=phone,
        )
        draft_text = out.get("message", "") if isinstance(out, dict) else str(out)
    except Exception as e:
        draft_text = f"(sandbox error: {e})"

    fired = []
    try:
        for h in match_rules(client_id, inbound_text):
            fired.append({"name": h.name, "escalate": h.escalate_to_owner})
    except Exception:
        pass

    return {
        "draft":         draft_text,
        "escalate":      escalate,
        "fired_rules":   fired,
        "kb_used":       bool(kb_block),
        "memory_used":   bool(mem_block),
    }


# ─── Admin: rules ─────────────────────────────────────────────────────────────

@router.get("/api/v1/clients/{client_id}/rules")
async def admin_list_rules(client_id: str, _: str = Depends(_admin_auth)):
    try:
        return {"rules": list_rules(client_id)}
    except RulesScopeViolationError as e:
        raise HTTPException(400, str(e))


@router.post("/api/v1/clients/{client_id}/rules")
async def admin_add_rule(client_id: str, payload: RuleCreate,
                          _: str = Depends(_admin_auth)):
    rid = add_rule(client_id=client_id, **payload.model_dump(exclude_none=True))
    return {"rule_id": rid}


@router.patch("/api/v1/clients/{client_id}/rules/{rule_id}")
async def admin_update_rule(client_id: str, rule_id: str, payload: RuleUpdate,
                             _: str = Depends(_admin_auth)):
    n = update_rule(client_id, rule_id, **payload.model_dump(exclude_none=True))
    return {"updated": n}


@router.delete("/api/v1/clients/{client_id}/rules/{rule_id}")
async def admin_delete_rule(client_id: str, rule_id: str,
                              _: str = Depends(_admin_auth)):
    n = delete_rule(client_id, rule_id)
    return {"deleted": n}


@router.post("/api/v1/clients/{client_id}/scenarios/activate")
async def admin_activate_scenario(client_id: str, payload: ActivateScenario,
                                    _: str = Depends(_admin_auth)):
    client = _client_doc_by_id(client_id)
    result = activate_scenario(client_id, client.get("vertical") or "", payload.scenario_key)
    return result


@router.get("/api/v1/clients/{client_id}/scenarios")
async def admin_list_scenarios(client_id: str, _: str = Depends(_admin_auth)):
    client = _client_doc_by_id(client_id)
    return {"vertical": client.get("vertical"),
            "scenarios": list_for_vertical(client.get("vertical") or "")}


@router.post("/api/v1/clients/{client_id}/sandbox/preview")
async def admin_sandbox(client_id: str, payload: SandboxPreview,
                         _: str = Depends(_admin_auth)):
    client = _client_doc_by_id(client_id)
    return _run_sandbox(client, payload.inbound_text,
                         payload.contact_name or "Guest", payload.phone)


# ─── Portal: rules ────────────────────────────────────────────────────────────

@router.get("/portal/{token}/rules")
async def portal_list_rules(token: str):
    client = _client_from_token(token)
    return {"rules": list_rules(str(client["_id"]))}


@router.post("/portal/{token}/rules")
async def portal_add_rule(token: str, payload: RuleCreate):
    client = _client_from_token(token)
    rid = add_rule(client_id=str(client["_id"]), **payload.model_dump(exclude_none=True))
    return {"rule_id": rid}


@router.patch("/portal/{token}/rules/{rule_id}")
async def portal_update_rule(token: str, rule_id: str, payload: RuleUpdate):
    client = _client_from_token(token)
    n = update_rule(str(client["_id"]), rule_id, **payload.model_dump(exclude_none=True))
    return {"updated": n}


@router.delete("/portal/{token}/rules/{rule_id}")
async def portal_delete_rule(token: str, rule_id: str):
    client = _client_from_token(token)
    n = delete_rule(str(client["_id"]), rule_id)
    return {"deleted": n}


@router.get("/portal/{token}/scenarios")
async def portal_list_scenarios(token: str):
    client = _client_from_token(token)
    return {"vertical": client.get("vertical"),
            "scenarios": list_for_vertical(client.get("vertical") or "")}


@router.post("/portal/{token}/scenarios/{scenario_key}/activate")
async def portal_activate_scenario(token: str, scenario_key: str):
    client = _client_from_token(token)
    return activate_scenario(str(client["_id"]), client.get("vertical") or "", scenario_key)


@router.post("/portal/{token}/sandbox/preview")
async def portal_sandbox(token: str, payload: SandboxPreview):
    client = _client_from_token(token)
    return _run_sandbox(client, payload.inbound_text,
                         payload.contact_name or "Guest", payload.phone)
