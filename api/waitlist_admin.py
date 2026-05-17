"""
Admin UI for the waitlist — list, invite, delete, wipe.

Auth: same Basic Auth as dashboard. Routes are mounted under /admin/waitlist.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from services.waitlist import (
    _col,
    list_waitlist,
    mark_invited,
    waitlist_total,
    waitlist_public_counter,
)

router = APIRouter(prefix="/admin/waitlist", tags=["waitlist-admin"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def waitlist_page(request: Request, _: str = Depends(require_auth)) -> HTMLResponse:
    rows     = list_waitlist(limit=500)
    counter  = waitlist_public_counter()
    return templates.TemplateResponse(
        "admin/waitlist.html",
        {
            "request":       request,
            "rows":          rows,
            "total":         counter["total"],
            "top_verticals": counter["top_verticals"],
        },
    )


@router.post("/{position}/invite")
def waitlist_invite(position: int, _: str = Depends(require_auth)) -> JSONResponse:
    ok = mark_invited(position)
    if not ok:
        raise HTTPException(404, "position not found or already invited")
    return JSONResponse({"ok": True, "position": position})


@router.delete("/{position}")
def waitlist_delete(position: int, _: str = Depends(require_auth)) -> JSONResponse:
    res = _col().delete_one({"position": position})
    if res.deleted_count == 0:
        raise HTTPException(404, "position not found")
    return JSONResponse({"ok": True, "position": position})


@router.post("/wipe")
def waitlist_wipe(_: str = Depends(require_auth)) -> JSONResponse:
    """Destructive — wipes the entire waitlist collection. Use only pre-launch."""
    res = _col().delete_many({})
    return JSONResponse({"ok": True, "deleted": res.deleted_count})
