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
    track_signup_failed, track_paystack_webhook_ignored,
)

log = structlog.get_logger()
router = APIRouter(tags=["Marketing"])

PAYSTACK_BASE = "https://api.paystack.co"

PLAN_PRICING = {
    "starter": {"label": "Solo",   "ngn":  60_000},
    "growth":  {"label": "Team",   "ngn": 120_000},
    "scale":   {"label": "Empire", "ngn": 250_000},
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
    track_page_viewed(page="signup_success", path="/signup/success",
                      referrer=request.headers.get("referer", ""),
                      has_reference=bool(reference))
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
        track_signup_failed(stage="config", reason="paystack_not_configured",
                            email=payload.owner_email, plan=payload.plan,
                            vertical=payload.vertical.strip().lower(), status_code=503)
        raise HTTPException(503, "Payments not configured. Email hello@reachng.ng to sign up directly.")
    vertical = payload.vertical.strip().lower()
    if vertical not in SUPPORTED_SIGNUP_VERTICALS:
        track_signup_failed(stage="validation", reason="unsupported_vertical",
                            email=payload.owner_email, plan=payload.plan,
                            vertical=vertical, status_code=400)
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
        track_signup_failed(stage="paystack_init", reason="paystack_rejected",
                            email=payload.owner_email, plan=payload.plan,
                            vertical=vertical, reference=reference, status_code=r.status_code)
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
        track_paystack_webhook_ignored(reason="bad_signature")
        raise HTTPException(401, "Invalid signature")
    payload = (await request.json()) if body_bytes else {}
    event = payload.get("event")
    data = payload.get("data", {})
    if event != "charge.success":
        track_paystack_webhook_ignored(reason="non_charge_success", event=event,
                                         reference=data.get("reference"))
        return {"ok": True, "ignored": event}
    metadata = data.get("metadata") or {}
    if metadata.get("kind") != "signup":
        track_paystack_webhook_ignored(reason="non_signup", event=event,
                                         reference=data.get("reference"))
        return {"ok": True, "ignored": "non-signup"}
    reference = data.get("reference")
    db = get_db()
    signup = db["signups"].find_one({"paystack_reference": reference})
    if not signup:
        log.warning("paystack_signup_not_found", reference=reference)
        track_paystack_webhook_ignored(reason="no_pending_signup", event=event,
                                         reference=reference)
        return {"ok": True, "ignored": "no-pending-signup"}
    if signup.get("status") == "provisioned":
        track_paystack_webhook_ignored(reason="already_provisioned", event=event,
                                         reference=reference)
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
    # Portal URL — prefer configured app_base_url over request.base_url so
    # links work even when the webhook arrives via the Railway internal host.
    base = (settings.app_base_url or str(request.base_url)).rstrip("/")
    portal_url = f"{base}/portal/{portal_token}"
    owner_name = signup.get("owner_name", "there")
    plan_label = signup.get("plan_label", "subscription")
    paid_until_str = paid_until.strftime("%d %b %Y")

    # 1) WhatsApp welcome — best-effort. Only fires if a WhatsApp connector
    #    (Meta Cloud API or Unipile) is configured; otherwise silently skipped.
    try:
        from tools.outreach import send_whatsapp_for_client
        wa_msg = (
            f"Welcome to ReachNG, {owner_name}!\n\n"
            f"Your {plan_label} is active until {paid_until_str}.\n\n"
            f"Your portal: {portal_url}\n\nNext step: open the portal, fill your Business Brief (5 mins), "
            f"and we'll set up your WhatsApp pairing on a quick call. "
            f"Reply here when you're ready and we'll send the pairing link."
        )
        await send_whatsapp_for_client(phone=signup["owner_phone"], message=wa_msg)
    except Exception as exc:
        log.warning("signup_welcome_whatsapp_failed", error=str(exc), business=signup["business_name"])

    # 2) Email welcome via Resend (hello@reachng.ng) — independent of WhatsApp
    #    so the customer always gets the portal link even before pairing.
    try:
        from tools.outreach import send_email
        owner_email = signup.get("owner_email")
        if owner_email:
            subject = f"Welcome to ReachNG — your portal is ready, {owner_name}"
            text = (
                f"Hi {owner_name},\n\n"
                f"Your ReachNG {plan_label} is now active until {paid_until_str}.\n\n"
                f"Open your portal: {portal_url}\n\n"
                f"Next step: log into the portal and fill your Business Brief (5 minutes). "
                f"Once that's in, we'll send a WhatsApp pairing link so EYO can start drafting "
                f"replies in your voice.\n\n"
                f"Anything urgent — reply to this email or WhatsApp +234 816 458 3657.\n\n"
                f"— EYO from ReachNG\nhello@reachng.ng\n"
            )
            html = f"""<!doctype html>
<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#f8f4ec;color:#14110d;margin:0;padding:32px 16px;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e8ddc8;border-radius:14px;padding:32px;">
    <div style="font-size:11px;letter-spacing:0.18em;color:#ff5500;text-transform:uppercase;font-weight:700;margin-bottom:18px;">Welcome to ReachNG</div>
    <h1 style="font-family:Georgia,serif;font-size:26px;font-weight:600;letter-spacing:-0.5px;margin:0 0 18px;">Your portal is ready, {owner_name}.</h1>
    <p style="font-size:15px;line-height:1.65;color:#3a342b;margin:0 0 22px;">Your <strong>{plan_label}</strong> is active until <strong>{paid_until_str}</strong>.</p>
    <p style="margin:0 0 28px;">
      <a href="{portal_url}" style="display:inline-block;background:#14110d;color:#fff;text-decoration:none;padding:14px 22px;border-radius:8px;font-size:14px;font-weight:600;">Open your portal →</a>
    </p>
    <p style="font-size:14px;line-height:1.7;color:#3a342b;margin:0 0 18px;"><strong>Next step:</strong> log into the portal and fill your Business Brief (5 minutes). Once that's in, we'll send a WhatsApp pairing link so EYO can start drafting replies in your voice.</p>
    <p style="font-size:13px;line-height:1.7;color:#6b6356;margin:24px 0 0;border-top:1px solid #eee3cf;padding-top:18px;">Anything urgent — reply to this email or WhatsApp <a href="https://wa.me/2348164583657" style="color:#ff5500;text-decoration:none;">+234 816 458 3657</a>.</p>
    <p style="font-size:12px;color:#9b917f;margin:18px 0 0;">— EYO from ReachNG · hello@reachng.ng</p>
  </div>
</body></html>"""
            await send_email(
                to_email=owner_email, subject=subject, body=text, html=html,
                force_smtp=True,  # routes via Resend from hello@reachng.ng
            )
            log.info("signup_welcome_email_sent", business=signup["business_name"], email=owner_email)
    except Exception as exc:
        log.warning("signup_welcome_email_failed", error=str(exc), business=signup["business_name"])

    # 3) Branded subscription receipt via Resend (separate from the Paystack auto-receipt).
    #    Built into services/subscription_invoice.py; this is the wire-up so it actually fires.
    try:
        from services.subscription_invoice import generate_receipt, email_receipt
        receipt = generate_receipt(signup=signup, client_id=str(existing["_id"]) if existing else None, paid_at=now)
        await email_receipt(receipt)
        log.info("subscription_receipt_dispatched",
                 receipt_no=receipt.get("receipt_number"),
                 business=signup["business_name"])
    except Exception as exc:
        log.warning("subscription_receipt_failed", error=str(exc), business=signup["business_name"])

    return {"ok": True, "provisioned": True, "portal_token": portal_token}


# Public founder-slots counter — drives the live scarcity strip on /pricing.
# Visible-scarcity converts better than abstract "first 50" phrasing.
FOUNDER_CAP = 50
_SLOTS_CACHE: dict = {"taken": None, "expires_at": None}

@router.get("/api/v1/founder-slots", include_in_schema=False)
async def founder_slots():
    """Returns {cap, taken, remaining} based on count of active paying clients.
    Cached 5 minutes so a viral spike doesn't hammer Mongo."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    cached_until = _SLOTS_CACHE.get("expires_at")
    if cached_until and now < cached_until and _SLOTS_CACHE.get("taken") is not None:
        taken = _SLOTS_CACHE["taken"]
    else:
        try:
            taken = get_db()["clients"].count_documents({"active": True, "payment_status": "paid"})
        except Exception:
            taken = 0
        _SLOTS_CACHE["taken"] = taken
        _SLOTS_CACHE["expires_at"] = now + timedelta(minutes=5)
    return {
        "cap":       FOUNDER_CAP,
        "taken":     taken,
        "remaining": max(0, FOUNDER_CAP - taken),
        "sold_out":  taken >= FOUNDER_CAP,
    }


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
