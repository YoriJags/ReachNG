"""
Admin Docs — printable HTML render of ECONOMICS / PRICING / INVESTOR markdown.

Why
---
Yori needs to share these with investors / advisors / lawyers. Markdown in
the repo is fine for engineers, useless for everyone else. Browser
print-to-PDF is the universal export.

Routes
------
  GET /admin/docs              — index linking to the three docs
  GET /admin/docs/{slug}       — render one of: economics | pricing | investor

All gated by the same Basic Auth wrapper as the rest of /admin/*.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import require_auth as _admin_auth

router = APIRouter(prefix="/admin/docs", tags=["AdminDocs"])

# Files live at the project root. We resolve from this file's location.
_ROOT = Path(__file__).resolve().parent.parent

DOCS = {
    "economics": {
        "title": "ReachNG · Unit Economics",
        "path":  _ROOT / "ECONOMICS.md",
        "subtitle": "Vendor-anchored per-call costs, per-client floors, dashboard gaps",
    },
    "pricing": {
        "title": "ReachNG · Pricing Working Doc",
        "path":  _ROOT / "PRICING.md",
        "subtitle": "Three ladder options modelled. Locked: ₦150k / ₦300k / ₦600k",
    },
    "investor": {
        "title": "ReachNG · Investor Brief",
        "path":  _ROOT / "INVESTOR.md",
        "subtitle": "Road to 1,000 clients · Lagos + Abuja premium SME tier",
    },
}


def _templates(request: Request):
    return request.app.state.templates


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def docs_index(request: Request, _: str = Depends(_admin_auth)):
    return _templates(request).TemplateResponse(
        request, "admin_docs_index.html", {"docs": DOCS}
    )


@router.get("/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def docs_render(slug: str, request: Request, _: str = Depends(_admin_auth)):
    meta = DOCS.get(slug)
    if not meta:
        raise HTTPException(404, f"Unknown doc: {slug}")
    path = meta["path"]
    if not path.exists():
        raise HTTPException(404, f"Missing source: {path.name}")
    raw = path.read_text(encoding="utf-8")

    # markdown lib is in requirements.txt; import lazily so missing-dep failures
    # surface a useful error instead of a 500 at app boot.
    try:
        import markdown as _md
    except ImportError:
        raise HTTPException(503, "markdown package not installed. Run pip install markdown.")

    html_body = _md.markdown(
        raw,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
    )

    return _templates(request).TemplateResponse(
        request, "admin_docs.html",
        {
            "title":    meta["title"],
            "subtitle": meta["subtitle"],
            "body_html": html_body,
            "slug":     slug,
        },
    )
