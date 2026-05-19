"""
Public marketing site - landing, pricing, how-it-works, about, contact, vertical landers.
Also handles self-serve signup -> Paystack -> auto-provision flow.
"""
import hmac
import hashlib
import secrets as pysecrets
import uuid
from datetime import datetime, timedelta, timezone
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, RedirectResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
import structlog

from config import get_settings
from database import get_db
from services.marketing_content import get_vertical_content, list_canonical_slugs
from services.analytics import (
    track_page_viewed, track_vertical_lander, track_contact_submitted,
    track_signup_page, track_signup_initiated,
    track_payment_verified, track_client_provisioned,
)

log = structlog.get_logger()
router = APIRouter(tags=["Marketing"])

PAYSTACK_BASE = "https://api.paystack.co"

PLAN_PRICING = {
    "starter": {"label": "Starter", "ngn": 80_000},
    "growth":  {"label": "Growth",  "ngn": 150_000},
    "scale":   {"label": "Scale",   "ngn": 300_000},
}


def _live_pricing() -> dict:
    try:
        from services.platform_settings import get_plan_pricing
        return get_plan_pricing()
    except Exception:
        return PLAN_PRICING


def _templates(request: Request):
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" not in accept:
        return Response(
            content='{"service":"ReachNG","status":"running","docs":"/docs","health":"/health"}',
            media_type="application/json",
        )
    track_page_viewed(
        page="landing", path="/",
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_medium=request.query_params.get("utm_medium"),
        utm_campaign=request.query_params.get("utm_campaign"),
        user_agent=request.headers.get("user-agent", ""),
    )
    return _templates(request).TemplateResponse(request, "marketing/landing.html")


@router.get("/how-it-works", response_class=HTMLResponse, include_in_schema=False)
async def how_it_works(request: Request):
    track_page_viewed(page="how_it_works", path="/how-it-works",
                      referrer=request.headers.get("referer", ""))
    return _templates(request).TemplateResponse(request, "marketing/how_it_works.html")


@router.get("/pricing", response_class=HTMLResponse, include_in_schema=False)
async def pricing(request: Request):
    track_page_viewed(page="pricing", path="/pricing",
                      referrer=request.headers.get("referer", ""),
                      utm_source=request.query_params.get("utm_source"))
    return _templates(request).TemplateResponse(request, "marketing/pricing.html")


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
async def about(request: Request):
    track_page_viewed(page="about", path="/about",
                      referrer=request.headers.get("referer", ""))
    return _templates(request).TemplateResponse(request, "marketing/about.html")


@router.get("/contact", response_class=HTMLResponse, include_in_schema=False)
async def contact(request: Request):
    track_page_viewed(page="contact", path="/contact",
                      referrer=request.headers.get("referer", ""))
    return _templates(request).TemplateResponse(request, "marketing/contact.html")


@router.get("/for/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def vertical_lander(slug: str, request: Request):
    content = get_vertical_content(slug)
    if not content:
        return RedirectResponse(url="/", status_code=302)
    track_vertical_lander(
        vertical=slug, path=f"/for/{slug}",
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_campaign=request.query_params.get("utm_campaign"),
    )
    return _templates(request).TemplateResponse(request, "marketing/vertical.html", {**content})


class ContactSubmission(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    business: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=4, max_length=40)
    vertical: str = Field(min_length=1, max_length=80)
    message: Optional[str] = Field(default="", max_length=4000)


@router.post("/api/v1/contact", include_in_schema=False)
async def contact_submit(payload: ContactSubmission):
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
    track_contact_submitted(vertical=payload.vertical.strip().lower(),
                            has_message=bool(payload.message))
    return {"ok": True, "message": "Got it. We'll be in touch within 30 minutes during Lagos business hours."}


@router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
async def signup_page(request: Request, plan: Optional[str] = None):
    selected = (plan or "growth").lower()
    track_signup_page(
        selected_plan=selected,
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_campaign=request.query_params.get("utm_campaign"),
    )
    return _templates(request).TemplateResponse(request, "marketing/signup.html", {
        "selected_plan": selected,
        "plans": _live_pricing(),
    })


@router.get("/signup/success", response_class=HTMLResponse, include_in_schema=False)
async def signup_success(request: Request, reference: Optional[str] = None):
    portal_path = None
    business = None
    error = None
    if reference:
        try:
            settings = get_settings()
            if not settings.paystack_secret_key:
                error = "Paystack not configured on server."
            else:
                async with httpx.AsyncClient(timeout=15.0) as cli:
                    r = await cli.get(
                        f"{PAYSTACK_BASE}/transaction/verify/{reference}",
                        headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
                    )
                if r.status_code == 200:
                    data = r.json().get("data", {})
                    if data.get("status") == "success":
                        signup = get_db()["signups"].find_one({"paystack_reference": reference})
                        if signup and signup.get("portal_token"):
                            portal_path = f"/portal/{signup['portal_token']}"
                            business = signup.get("business_name")
                            track_payment_verified(
                                email=signup.get("owner_email"), reference=reference,
                                plan=signup.get("plan"), vertical=signup.get("vertical"),
                                amount_ngn=signup.get("amount_ngn"), annual=signup.get("annual"),
                                portal_provisioned=True,
                            )
                        else:
                            error = "Payment confirmed. Provisioning your portal - check your WhatsApp + email in 60 seconds."
                            track_payment_verified(
                                email=None, reference=reference,
                                plan=None, vertical=None, amount_ngn=None, annual=None,
                                portal_provisioned=False, state="pending_webhook",
                            )
                    else:
                        error = f"Payment status: {data.get('status', 'unknown')}. Contact us if this is wrong."
                else:
                    error = "Could not verify payment with Paystack."
        except Exception as exc:
            log.error("signup_verify_failed", error=str(exc), reference=reference)
            error = "Verification failed. Don't worry - if you paid, we'll provision you within 5 minutes."
    return _templates(request).TemplateResponse(request, "marketing/signup_success.html", {
        "portal_path": portal_path, "business": business,
        "error": error, "reference": reference,
    })


SUPPORTED_SIGNUP_VERTICALS = {
    "hospitality", "real_estate", "education", "professional_services",
    "small_business", "fitness", "events", "auto", "cooperatives",
    "legal", "insurance", "recruitment", "general",
}


class SignupPayload(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    vertical: str = Field(min_length=1, max_length=80)
    owner_name: str = Field(min_length=1, max_length=200)
    owner_phone: str = Field(min_length=4, max_length=40)
    owner_email: str = Field(min_length=4, max_length=200)
    plan: Literal["starter", "growth", "scale"] = "growth"
    annual: bool = False


@router.post("/api/v1/signup")
async def signup_initialize(payload: SignupPayload, request: Request):
    settings = get_settings()
    if not settings.paystack_secret_key:
        raise HTTPException(503, "Payments not configured. Email hello@reachng.ng to sign up directly.")
    vertical = payload.vertical.strip().lower()
    if vertical not in SUPPORTED_SIGNUP_VERTICALS:
        raise HTTPException(400, f"Vertical '{payload.vertical}' not supported.")
    plan_info = _live_pricing()[payload.plan]
    base_ngn = plan_info["ngn"]
    if payload.annual:
        amount_ngn = int(base_ngn * 12 * 0.85)
        plan_label = f"{plan_info['label']} (Annual - 15% off)"
    else:
        amount_ngn = base_ngn
        plan_label = f"{plan_info['label']} (Monthly)"
    reference = f"RNG-SU-{uuid.uuid4().hex[:10].upper()}"
    base_url = str(request.base_url).rstrip("/")
    callback_url = f"{base_url}/signup/success?reference={reference}"
    body = {
        "email": payload.owner_email, "amount": amount_ngn * 100,
        "reference": reference, "currency": "NGN",
        "callback_url": callback_url,
        "metadata": {
            "kind": "signup", "business_name": payload.business_name,
            "vertical": vertical, "owner_name": payload.owner_name,
            "owner_phone": payload.owner_phone, "plan": payload.plan,
            "plan_label": plan_label, "annual": payload.annual, "amount_ngn": amount_ngn,
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.post(
            f"{PAYSTACK_BASE}/transaction/initialize", json=body,
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}",
                     "Content-Type": "application/json"},
        )
    if r.status_code != 200 or not r.json().get("status"):
        log.error("paystack_init_failed", status=r.status_code, body=r.text[:500])
        raise HTTPException(502, "Could not initialise payment. Try again or email hello@reachng.ng.")
    data = r.json()["data"]
    get_db()["signups"].insert_one({
        "paystack_reference": reference, "business_name": payload.business_name,
        "vertical": vertical, "owner_name": payload.owner_name,
        "owner_phone": payload.owner_phone, "owner_email": payload.owner_email,
        "plan": payload.plan, "plan_label": plan_label, "amount_ngn": amount_ngn,
        "annual": payload.annual, "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })
    log.info("signup_initialised", business=payload.business_name,
             plan=payload.plan, reference=reference)
    track_signup_initiated(
        email=payload.owner_email, plan=payload.plan, plan_label=plan_label,
        vertical=vertical, amount_ngn=amount_ngn, annual=payload.annual, reference=reference,
    )
    return {"authorization_url": data["authorization_url"], "reference": reference}


@router.post("/webhooks/paystack", include_in_schema=False)
async def paystack_webhook(request: Request):
    settings = get_settings()
    secret = settings.paystack_secret_key
    if not secret:
        raise HTTPException(503, "Paystack not configured")
    body_bytes = await request.body()
    sig_header = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(sig_header, expected):
        log.warning("paystack_webhook_bad_signature")
        raise HTTPException(401, "Invalid signature")
    payload = (await request.json()) if body_bytes else {}
    event = payload.get("event")
    data = payload.get("data", {})
    if event != "charge.success":
        return {"ok": True, "ignored": event}
    metadata = data.get("metadata") or {}
    if metadata.get("kind") != "signup":
        return {"ok": True, "ignored": "non-signup"}
    reference = data.get("reference")
    db = get_db()
    signup = db["signups"].find_one({"paystack_reference": reference})
    if not signup:
        log.warning("paystack_signup_not_found", reference=reference)
        return {"ok": True, "ignored": "no-pending-signup"}
    if signup.get("status") == "provisioned":
        return {"ok": True, "ignored": "already-provisioned"}
    portal_token = pysecrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    paid_until = now + (timedelta(days=365) if signup.get("annual") else timedelta(days=30))
    clients = db["clients"]
    existing = clients.find_one({"name": signup["business_name"]})
    client_doc = {
        "name": signup["business_name"], "vertical": signup["vertical"],
        "brief": "", "active": True, "plan": signup["plan"],
        "payment_status": "paid",
        "monthly_fee_ngn": _live_pricing().get(signup["plan"], {}).get("ngn"),
        "paid_until": paid_until, "owner_name": signup["owner_name"],
        "owner_phone": signup["owner_phone"], "owner_email": signup["owner_email"],
        "agent_name": "EYO", "preferred_channel": "whatsapp",
        "autopilot": False, "signal_listening": False, "holding_message": "",
        "portal_token": portal_token, "portal_created_at": now,
        "onboarded_at": now, "updated_at": now,
    }
    if existing:
        portal_token = existing.get("portal_token") or portal_token
        client_doc["portal_token"] = portal_token
        client_doc.pop("portal_created_at", None)
        clients.update_one({"_id": existing["_id"]}, {"$set": client_doc})
    else:
        clients.insert_one(client_doc)
    db["signups"].update_one(
        {"_id": signup["_id"]},
        {"$set": {"status": "provisioned", "portal_token": portal_token,
                  "provisioned_at": now}},
    )
    log.info("client_provisioned_from_signup", business=signup["business_name"],
             plan=signup["plan"], reference=reference)
    track_client_provisioned(
        email=signup.get("owner_email"), reference=reference,
        plan=signup["plan"], vertical=signup["vertical"],
        business_name=signup["business_name"],
        amount_ngn=signup.get("amount_ngn"), annual=signup.get("annual"),
    )
    try:
        from tools.outreach import send_whatsapp_for_client
        portal_url = f"{request.base_url}portal/{portal_token}".replace("//portal", "/portal")
        welcome = (
            f"Welcome to ReachNG, {signup.get('owner_name', 'there')}!\n\n"
            f"Your {signup.get('plan_label', 'subscription')} is active until {paid_until.strftime('%d %b %Y')}.\n\n"
            f"Your portal: {portal_url}\n\nNext step: open the portal, fill your Business Brief (5 mins), "
            f"and we'll set up your WhatsApp pairing on a quick call. "
            f"Reply here when you're ready and we'll send the pairing link."
        )
        await send_whatsapp_for_client(phone=signup["owner_phone"], message=welcome)
    except Exception as exc:
        log.warning("signup_welcome_failed", error=str(exc), business=signup["business_name"])
    return {"ok": True, "provisioned": True, "portal_token": portal_token}


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
        ("/", "1.0", "weekly"), ("/how-it-works", "0.9", "monthly"),
        ("/pricing", "0.9", "monthly"), ("/signup", "0.95", "monthly"),
        ("/about", "0.7", "monthly"), ("/contact", "0.8", "monthly"),
        ("/portal/demo", "0.8", "weekly"),
    ]
    for slug in list_canonical_slugs():
        pages.append((f"/for/{slug}", "0.85", "monthly"))
    for vertical in ["hospitality", "real_estate", "education", "professional_services", "small_business"]:
        pages.append((f"/portal/demo/{vertical}", "0.7", "weekly"))
    urls = []
    for path, priority, freq in pages:
        urls.append(
            f"  <url>\n    <loc>{base}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n  </url>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n"
    )
    return Response(content=body, media_type="application/xml")
