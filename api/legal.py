"""
Legal pack API — PDF download + per-client acceptance tracking.

Routes:
  Admin (Basic Auth):
    GET  /admin/legal/docs                                   list docs + current versions
    GET  /admin/legal/docs/{slug}.pdf                        stream the PDF
    GET  /admin/legal/clients/{name}                         per-client acceptance status
    POST /admin/legal/clients/{name}/accept                  record acceptance for one doc
    POST /admin/legal/clients/{name}/revoke                  revoke a previous acceptance

  Portal (token-gated, no Basic Auth):
    GET  /portal-legal/{token}/docs                          list docs + this client's status
    GET  /portal-legal/{token}/docs/{slug}.pdf               stream PDF for the client
    POST /portal-legal/{token}/accept                        client confirms acceptance

A client must have accepted MSA + DPA + NDA (and CLOSER_ADDENDUM if real_estate
+ closer_enabled) before prospecting outreach is allowed. The check is
exposed via `is_legal_pack_complete()` for use in the brief gate / campaign
runner.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING

from database import get_db
import structlog

log = structlog.get_logger()

router        = APIRouter(prefix="/admin/legal",  tags=["Legal Pack — Admin"])
public_router = APIRouter(prefix="/portal-legal", tags=["Legal Pack — Portal"])


# Mapping of doc slug to (display_name, applies_to_filter, current_version).
# Bump version when the underlying PDF changes — clients are then prompted to
# re-accept the new version.
LEGAL_DOCS: dict[str, dict] = {
    "MSA":             {"name": "Master Service Agreement",  "version": "1.0", "required_for": "all"},
    "DPA":             {"name": "Data Processing Agreement", "version": "1.0", "required_for": "all"},
    "MUTUAL_NDA":      {"name": "Mutual NDA",                "version": "1.0", "required_for": "all"},
    "CLOSER_ADDENDUM": {"name": "Closer Addendum",           "version": "1.0", "required_for": "closer"},
}

PDF_DIR = Path(__file__).parent.parent / "legal" / "pdfs"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_by_name(name: str) -> dict:
    client = get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{name}' not found")
    return client


def _client_by_token(token: str) -> dict:
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    return client


def _required_docs_for(client: dict) -> list[str]:
    """Which docs this client has to sign — based on suite enablement."""
    required = ["MSA", "DPA", "MUTUAL_NDA"]
    if client.get("vertical") == "real_estate" and client.get("closer_enabled"):
        required.append("CLOSER_ADDENDUM")
    return required


def _list_status(client: dict) -> dict:
    """Per-doc acceptance state for this client."""
    accepts = list(
        get_db()["client_legal_acceptances"]
        .find({"client_id": client["_id"]})
        .sort("accepted_at", DESCENDING)
    )
    by_slug: dict[str, dict] = {}
    for a in accepts:
        slug = a.get("doc_slug")
        if not slug or slug in by_slug:
            continue  # take the most recent only
        if a.get("revoked_at"):
            by_slug[slug] = {"status": "revoked", "version": a.get("version"), "at": a.get("accepted_at"), "revoked_at": a.get("revoked_at")}
        else:
            by_slug[slug] = {"status": "accepted", "version": a.get("version"), "at": a.get("accepted_at"), "by": a.get("accepter")}

    required = _required_docs_for(client)
    out_docs = []
    for slug, meta in LEGAL_DOCS.items():
        applies = (
            meta["required_for"] == "all"
            or (meta["required_for"] == "closer" and slug in required)
        )
        if not applies and slug not in required and meta["required_for"] != "all":
            # Closer addendum only shows for closer-enabled clients
            continue
        state = by_slug.get(slug, {"status": "pending"})
        accepted_version_ok = (
            state.get("status") == "accepted"
            and state.get("version") == meta["version"]
        )
        out_docs.append({
            "slug": slug,
            "name": meta["name"],
            "current_version": meta["version"],
            "required": slug in required,
            **state,
            "current_version_accepted": accepted_version_ok,
        })

    all_required_accepted = all(
        any(d["slug"] == slug and d["current_version_accepted"] for d in out_docs)
        for slug in required
    )
    return {
        "client_name": client.get("name"),
        "vertical": client.get("vertical"),
        "required": required,
        "docs": out_docs,
        "complete": all_required_accepted,
    }


def is_legal_pack_complete(*, client_id: Optional[str] = None, client_name: Optional[str] = None) -> bool:
    """Public helper for gates elsewhere (e.g. campaign runner)."""
    if client_id:
        client = get_db()["clients"].find_one({"_id": ObjectId(client_id)})
    else:
        client = get_db()["clients"].find_one(
            {"name": {"$regex": f"^{re.escape(client_name or '')}$", "$options": "i"}}
        )
    if not client:
        return False
    return _list_status(client)["complete"]


def ensure_legal_indexes() -> None:
    col = get_db()["client_legal_acceptances"]
    col.create_index([("client_id", ASCENDING), ("doc_slug", ASCENDING)])
    col.create_index([("accepted_at", DESCENDING)])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class AcceptPayload(BaseModel):
    doc_slug: str = Field(..., description="MSA | DPA | MUTUAL_NDA | CLOSER_ADDENDUM")
    accepter: Optional[str] = Field(default=None, description="Name or email of the human accepting")
    version: Optional[str] = None  # if omitted, accepts current version


class RevokePayload(BaseModel):
    doc_slug: str
    reason: Optional[str] = None


# ─── Admin: docs + acceptance ────────────────────────────────────────────────

@router.get("/docs")
async def admin_list_docs():
    """Catalogue of the legal pack — slugs, names, versions, applicability."""
    return {"docs": [{"slug": s, **m} for s, m in LEGAL_DOCS.items()]}


@router.get("/docs/{slug}.pdf")
async def admin_download_pdf(slug: str):
    if slug not in LEGAL_DOCS:
        raise HTTPException(404, "Unknown legal document")
    pdf_path = PDF_DIR / f"{slug}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF not generated. Run `python -m legal.build_pdfs` first.")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"reachng-{slug.lower()}.pdf",
    )


@router.get("/clients/{name}")
async def admin_client_status(name: str):
    client = _client_by_name(name)
    return _list_status(client)


@router.post("/clients/{name}/accept")
async def admin_accept(name: str, payload: AcceptPayload, request: Request):
    if payload.doc_slug not in LEGAL_DOCS:
        raise HTTPException(400, "Unknown doc_slug")
    client = _client_by_name(name)
    version = payload.version or LEGAL_DOCS[payload.doc_slug]["version"]
    accepter = payload.accepter or "admin"
    ip = request.client.host if request.client else None

    get_db()["client_legal_acceptances"].insert_one({
        "client_id":   client["_id"],
        "client_name": client.get("name"),
        "doc_slug":    payload.doc_slug,
        "version":     version,
        "accepter":    accepter,
        "accepter_ip": ip,
        "accepted_at": datetime.now(timezone.utc),
        "via":         "admin",
    })
    log.info("legal_accepted_admin", client=client.get("name"), doc=payload.doc_slug, version=version)
    return {"success": True, **_list_status(client)}


@router.post("/clients/{name}/revoke")
async def admin_revoke(name: str, payload: RevokePayload):
    if payload.doc_slug not in LEGAL_DOCS:
        raise HTTPException(400, "Unknown doc_slug")
    client = _client_by_name(name)
    now = datetime.now(timezone.utc)
    res = get_db()["client_legal_acceptances"].update_many(
        {
            "client_id": client["_id"],
            "doc_slug":  payload.doc_slug,
            "revoked_at": {"$exists": False},
        },
        {"$set": {"revoked_at": now, "revoke_reason": payload.reason}},
    )
    log.warning("legal_revoked_admin", client=client.get("name"), doc=payload.doc_slug, count=res.modified_count)
    return {"success": True, "revoked_count": res.modified_count, **_list_status(client)}


# ─── Portal: docs + acceptance ───────────────────────────────────────────────

@public_router.get("/{token}/docs")
async def portal_list_docs(token: str):
    client = _client_by_token(token)
    return _list_status(client)


@public_router.get("/{token}/docs/{slug}.pdf")
async def portal_download_pdf(token: str, slug: str):
    _client_by_token(token)
    if slug not in LEGAL_DOCS:
        raise HTTPException(404, "Unknown legal document")
    pdf_path = PDF_DIR / f"{slug}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF not generated.")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"reachng-{slug.lower()}.pdf",
    )


@public_router.post("/{token}/accept")
async def portal_accept(token: str, payload: AcceptPayload, request: Request):
    if payload.doc_slug not in LEGAL_DOCS:
        raise HTTPException(400, "Unknown doc_slug")
    client = _client_by_token(token)
    if not payload.accepter:
        raise HTTPException(422, "Provide your name or title in 'accepter' so we can record the signatory.")
    version = payload.version or LEGAL_DOCS[payload.doc_slug]["version"]
    ip = request.client.host if request.client else None

    get_db()["client_legal_acceptances"].insert_one({
        "client_id":   client["_id"],
        "client_name": client.get("name"),
        "doc_slug":    payload.doc_slug,
        "version":     version,
        "accepter":    payload.accepter,
        "accepter_ip": ip,
        "accepted_at": datetime.now(timezone.utc),
        "via":         "portal",
    })
    log.info("legal_accepted_portal", client=client.get("name"), doc=payload.doc_slug, version=version)
    return {"success": True, **_list_status(client)}
