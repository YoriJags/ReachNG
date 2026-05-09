"""
Public marketing site — landing, pricing, how-it-works, about, contact, vertical landers.

Public routes — no auth. Mounted at root via main.py without auth wrapper.
SEO essentials: sitemap.xml, robots.txt, canonical URLs, schema.org.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, RedirectResponse
from pydantic import BaseModel, Field
from typing import Optional
import structlog

from database import get_db
from services.marketing_content import get_vertical_content, list_canonical_slugs

log = structlog.get_logger()
router = APIRouter(tags=["Marketing"])


def _templates(request: Request):
    return request.app.state.templates


# ─── Pages ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing(request: Request):
    """Public landing page. Browsers see marketing site; API/health probes get JSON via the
    main.py root handler — but we let the marketing page take precedence on text/html."""
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" not in accept:
        return Response(
            content='{"service":"ReachNG","status":"running","docs":"/docs","health":"/health"}',
            media_type="application/json",
        )
    return _templates(request).TemplateResponse(request, "marketing/landing.html")


@router.get("/how-it-works", response_class=HTMLResponse, include_in_schema=False)
async def how_it_works(request: Request):
    return _templates(request).TemplateResponse(request, "marketing/how_it_works.html")


@router.get("/pricing", response_class=HTMLResponse, include_in_schema=False)
async def pricing(request: Request):
    return _templates(request).TemplateResponse(request, "marketing/pricing.html")


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
async def about(request: Request):
    return _templates(request).TemplateResponse(request, "marketing/about.html")


@router.get("/contact", response_class=HTMLResponse, include_in_schema=False)
async def contact(request: Request):
    return _templates(request).TemplateResponse(request, "marketing/contact.html")


@router.get("/for/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def vertical_lander(slug: str, request: Request):
    """Per-vertical marketing landing page. Same template, vertical-tailored content."""
    content = get_vertical_content(slug)
    if not content:
        # Unknown vertical → bounce to landing rather than 404 (better UX)
        return RedirectResponse(url="/", status_code=302)
    ctx = {**content}
    return _templates(request).TemplateResponse(request, "marketing/vertical.html", ctx)


# ─── Contact form submission ─────────────────────────────────────────────────

class ContactSubmission(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    business: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=4, max_length=40)
    vertical: str = Field(min_length=1, max_length=80)
    message: Optional[str] = Field(default="", max_length=4000)


@router.post("/api/v1/contact", include_in_schema=False)
async def contact_submit(payload: ContactSubmission):
    """Capture inbound contact form submissions. Stored to MongoDB; operator gets a
    notification via the existing 7am brief / dashboard widget.
    """
    db = get_db()
    db["contact_submissions"].insert_one({
        "name": payload.name.strip(),
        "business": payload.business.strip(),
        "phone": payload.phone.strip(),
        "vertical": payload.vertical.strip().lower(),
        "message": (payload.message or "").strip(),
        "received_at": datetime.now(timezone.utc),
        "handled": False,
    })
    log.info("contact_submission_received", business=payload.business, vertical=payload.vertical)
    return {"ok": True, "message": "Got it. We'll be in touch within 30 minutes during Lagos business hours."}


# ─── SEO assets ──────────────────────────────────────────────────────────────

@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots_txt(request: Request):
    base = str(request.base_url).rstrip("/")
    return f"""User-agent: *
Allow: /
Allow: /portal/demo
Disallow: /dashboard
Disallow: /admin
Disallow: /api/
Disallow: /webhooks
Disallow: /portal/data/
Disallow: /docs
Disallow: /openapi.json
Disallow: /mcp
Sitemap: {base}/sitemap.xml
"""


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(request: Request):
    base = str(request.base_url).rstrip("/")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pages = [
        ("/", "1.0", "weekly"),
        ("/how-it-works", "0.9", "monthly"),
        ("/pricing", "0.9", "monthly"),
        ("/about", "0.7", "monthly"),
        ("/contact", "0.8", "monthly"),
        ("/portal/demo", "0.8", "weekly"),
    ]
    for slug in list_canonical_slugs():
        pages.append((f"/for/{slug}", "0.85", "monthly"))

    # Demo portals (each vertical gets its own URL)
    for vertical in ["hospitality", "real_estate", "education", "professional_services", "small_business"]:
        pages.append((f"/portal/demo/{vertical}", "0.7", "weekly"))

    urls = []
    for path, priority, freq in pages:
        urls.append(
            f"  <url>\n"
            f"    <loc>{base}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return Response(content=body, media_type="application/xml")
