"""
Operator pipeline view — kanban of Yori's own prospect/client funnel.

Routes
------
GET  /api/v1/admin/pipeline    JSON shape for SPA fetches
GET  /admin/pipeline           Standalone HTML kanban page
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from auth import require_auth as _admin_auth
from services.pipeline import get_pipeline
from services.waitlist import mark_invited

router = APIRouter(tags=["Pipeline"])


@router.get("/api/v1/admin/pipeline")
async def admin_pipeline_json(_: str = Depends(_admin_auth)):
    return get_pipeline()


@router.post("/api/v1/admin/pipeline/invite/{position}")
async def admin_pipeline_invite(position: int, _: str = Depends(_admin_auth)):
    """Convenience action from the kanban — mark a waitlist entry as invited."""
    ok = mark_invited(position)
    return {"position": position, "invited": bool(ok)}


@router.get("/admin/pipeline", response_class=HTMLResponse)
async def admin_pipeline_page(request: Request, _: str = Depends(_admin_auth)):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "admin/pipeline.html", {"pipeline": get_pipeline()}
    )
