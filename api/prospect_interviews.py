"""
Prospect interviews API — admin-only (Basic Auth).

Routes:
  GET    /api/v1/admin/prospect-interviews
  POST   /api/v1/admin/prospect-interviews
  PATCH  /api/v1/admin/prospect-interviews/{id}
  DELETE /api/v1/admin/prospect-interviews/{id}
  GET    /api/v1/admin/prospect-interviews/stats
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_auth
from services.prospect_interviews import (
    create_interview, list_interviews, update_interview, delete_interview, stats,
)

router = APIRouter(prefix="/api/v1/admin", tags=["ProspectInterviews"],
                   dependencies=[Depends(require_auth)])


class InterviewCreate(BaseModel):
    prospect_name:           str = Field(min_length=1, max_length=120)
    business_name:           str = Field(min_length=1, max_length=120)
    vertical:                Optional[str] = None
    channel:                 str = "whatsapp"
    pain_today:              str = ""
    what_theyd_pay_for:      str = ""
    killer_quote:            str = ""
    decision_maker_role:     Optional[str] = None
    current_tool:            Optional[str] = None
    monthly_whatsapp_volume: Optional[int] = None
    sentiment:               str = "warm"
    next_step:               str = ""
    contact_id:              Optional[str] = None
    notes:                   str = ""


class InterviewPatch(BaseModel):
    pain_today:              Optional[str] = None
    what_theyd_pay_for:      Optional[str] = None
    killer_quote:            Optional[str] = None
    decision_maker_role:     Optional[str] = None
    current_tool:            Optional[str] = None
    monthly_whatsapp_volume: Optional[int] = None
    sentiment:               Optional[str] = None
    next_step:               Optional[str] = None
    notes:                   Optional[str] = None


@router.get("/prospect-interviews")
async def list_route(limit: int = 100,
                     sentiment: Optional[str] = None,
                     vertical:  Optional[str] = None):
    return {"interviews": list_interviews(limit=limit, sentiment=sentiment, vertical=vertical)}


@router.get("/prospect-interviews/stats")
async def stats_route():
    return stats()


@router.post("/prospect-interviews")
async def create_route(payload: InterviewCreate):
    iid = create_interview(**payload.model_dump())
    return {"id": iid}


@router.patch("/prospect-interviews/{interview_id}")
async def patch_route(interview_id: str, payload: InterviewPatch):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_interview(interview_id, patch):
        raise HTTPException(404, "Interview not found or no valid fields to update")
    return {"ok": True}


@router.delete("/prospect-interviews/{interview_id}")
async def delete_route(interview_id: str):
    if not delete_interview(interview_id):
        raise HTTPException(404, "Interview not found")
    return {"ok": True}
