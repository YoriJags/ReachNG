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
