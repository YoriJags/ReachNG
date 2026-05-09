"""
Live pipeline dashboard — served at GET /dashboard
HTML is rendered from templates/dashboard.html via Jinja2.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/dashboard/flow", response_class=HTMLResponse)
async def operations_flow(request: Request):
    """Operations flow viewer — Mermaid-rendered system diagrams.
    Same auth as dashboard (Basic Auth via dashboard_router wrapper in main.py).
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "operations_flow.html")
