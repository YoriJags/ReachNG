"""
Client Knowledge Base routes.

Two access paths:
  • Admin (Basic Auth) — `/api/v1/clients/{client_id}/kb/...` — operator manages
    every client's KB from the dashboard.
  • Client portal (token) — `/portal/{token}/kb/...` — the client uploads their
    own docs from their portal.

All routes scope-lock by `client_id` resolved either from the URL or the portal
token. No bypass.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from auth import require_auth as _admin_auth
from database import get_db
from services.knowledge_base import (
    add_document, list_documents, delete_document,
    search_kb, KBScopeViolationError,
)

router = APIRouter(tags=["Knowledge Base"])


# ─── Models ───────────────────────────────────────────────────────────────────

class PasteDocRequest(BaseModel):
    title: str
    text: str
    tags: Optional[list[str]] = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 4


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_from_token(token: str) -> dict:
    """Resolve a portal token to a client doc. 404 if not found / inactive."""
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "portal not found")
    return client


# ─── Admin routes ─────────────────────────────────────────────────────────────

@router.get("/api/v1/clients/{client_id}/kb")
async def admin_list_kb(client_id: str, _: str = Depends(_admin_auth)):
    try:
        return {"documents": list_documents(client_id)}
    except KBScopeViolationError as e:
        raise HTTPException(400, str(e))


@router.post("/api/v1/clients/{client_id}/kb/paste")
async def admin_paste_kb(client_id: str, payload: PasteDocRequest,
                          _: str = Depends(_admin_auth)):
    try:
        doc = add_document(
            client_id=client_id,
            title=payload.title,
            raw_text=payload.text,
            tags=payload.tags or [],
        )
    except KBScopeViolationError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"doc_id": doc.doc_id, "title": doc.title, "chunks": doc.chunk_count}


@router.post("/api/v1/clients/{client_id}/kb/upload")
async def admin_upload_kb(
    client_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    _: str = Depends(_admin_auth),
):
    content = await file.read()
    try:
        doc = add_document(
            client_id=client_id,
            title=title or file.filename or "Untitled",
            file_bytes=content,
            filename=file.filename,
            mime_type=file.content_type,
            tags=[t.strip() for t in (tags or "").split(",") if t.strip()] or None,
        )
    except KBScopeViolationError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"doc_id": doc.doc_id, "title": doc.title, "chunks": doc.chunk_count}


@router.delete("/api/v1/clients/{client_id}/kb/{doc_id}")
async def admin_delete_kb(client_id: str, doc_id: str,
                            _: str = Depends(_admin_auth)):
    n = delete_document(client_id, doc_id)
    return {"deleted": n}


@router.post("/api/v1/clients/{client_id}/kb/search")
async def admin_search_kb(client_id: str, payload: SearchRequest,
                            _: str = Depends(_admin_auth)):
    hits = search_kb(client_id, payload.query, top_k=payload.top_k)
    return {"hits": [{"text": h.text, "doc_title": h.doc_title, "score": h.score} for h in hits]}


# ─── Portal routes (client-facing) ────────────────────────────────────────────

@router.get("/portal/{token}/kb")
async def portal_list_kb(token: str):
    client = _client_from_token(token)
    return {"documents": list_documents(str(client["_id"]))}


@router.post("/portal/{token}/kb/paste")
async def portal_paste_kb(token: str, payload: PasteDocRequest):
    client = _client_from_token(token)
    try:
        doc = add_document(
            client_id=str(client["_id"]),
            title=payload.title,
            raw_text=payload.text,
            tags=payload.tags or [],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"doc_id": doc.doc_id, "title": doc.title, "chunks": doc.chunk_count}


@router.post("/portal/{token}/kb/upload")
async def portal_upload_kb(
    token: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    client = _client_from_token(token)
    content = await file.read()
    try:
        doc = add_document(
            client_id=str(client["_id"]),
            title=title or file.filename or "Untitled",
            file_bytes=content,
            filename=file.filename,
            mime_type=file.content_type,
            tags=[t.strip() for t in (tags or "").split(",") if t.strip()] or None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"doc_id": doc.doc_id, "title": doc.title, "chunks": doc.chunk_count}


@router.delete("/portal/{token}/kb/{doc_id}")
async def portal_delete_kb(token: str, doc_id: str):
    client = _client_from_token(token)
    n = delete_document(str(client["_id"]), doc_id)
    return {"deleted": n}
