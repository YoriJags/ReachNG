"""
Co-pilot API — operator-only.

  POST /api/v1/copilot/ask
    body: {client_id: str, question: str}

The operator picks WHICH client they're asking about (no cross-client queries
in v1 — preserves the isolation we built into client_memory + scorecard).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_auth as _admin_auth
from services.copilot import ask, CopilotScopeError

router = APIRouter(prefix="/api/v1/copilot", tags=["Copilot"])


class AskPayload(BaseModel):
    client_id: str = Field(..., min_length=1)
    question:  str = Field(..., min_length=1, max_length=400)


@router.post("/ask")
async def copilot_ask(payload: AskPayload, _: str = Depends(_admin_auth)):
    try:
        return ask(client_id=payload.client_id, question=payload.question)
    except CopilotScopeError as e:
        raise HTTPException(400, str(e))
