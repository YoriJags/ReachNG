"""
Public marketing site — landing, pricing, how-it-works, about, contact, vertical landers.

Public routes — no auth. Mounted at root via main.py without auth wrapper.
SEO essentials: sitemap.xml, robots.txt, canonical URLs, schema.org.

Also handles self-serve signup → Paystack → auto-provision flow.
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

log = structlog.get_logger()
router = APIRouter(tags=["Marketing"])

PAYSTACK_BASE = "https://api.paystack.co"

# Plan tier → monthly fee in naira.
# DEPRECATED hardcoded constant — kept only for any legacy importer; live
# pricing reads from `services.platform_settings.get_plan_pricing()` and is
# editable from the Control Tower → Pricing tab (no deploy needed).
PLAN_PRICING = {
    "starter": {"label": "Starter", "ngn": 80_000},
    "growth":  {"label": "Growth",  "ngn": 150_000},
    "scale":   {"label": "Scale",   "ngn": 300_000},
}


def _live_pricing() -> dict:
    """Always-fresh pricing read. Falls back to PLAN_PRICING on any error."""
    try:
        from services.platform_settings import get_plan_pricing
        return get_plan_pricing()
    except Exception:
        return PLAN_PRICING


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


class LeakageCalc(BaseModel):
    enquiries_per_week: int = Field(..., ge=1, le=2000)
    avg_deal_value_naira: int = Field(..., ge=1000, le=1_000_000_000)
    email: Optional[str] = Field(None, max_length=120)
    business_name: Optional[str] = Field(None, max_length=120)


@router.post("/api/v1/calculator/leakage", include_in_schema=False)
async def calculator_leakage(payload: LeakageCalc, request: Request):
    """Compute weekly + monthly revenue leakage and (optionally) email the
    result. Anchor: HBR's "5-minute rule" — leads that wait >5 min are 9x
    less likely to close. We use 30% as the leakage rate (conservative)
    for prospects who aren't replying within 5 minutes.
    """
    LEAKAGE_RATE = 0.30  # conservative; the HBR 9x gap implies more
    weekly_loss  = int(payload.enquiries_per_week * payload.avg_deal_value_naira * LEAKAGE_RATE)
    monthly_loss = weekly_loss * 4

    response = {
        "weekly_loss":   weekly_loss,
        "monthly_loss":  monthly_loss,
        "leakage_rate":  LEAKAGE_RATE,
        "emailed":       False,
    }

    if payload.email and "@" in payload.email:
        # Fire-and-forget email via Resend (same path as waitlist confirmations).
        try:
            from tools.outreach import send_email
            biz = (payload.business_name or "your business").strip()
            first_name = biz.split(" ")[0] if biz else "there"
            subject = f"Your WhatsApp leakage estimate · ~₦{monthly_loss//1_000_000}M/month"
            text = (
                f"Hi,\n\n"
                f"EYO here from ReachNG. You ran the WhatsApp leakage calculator for {biz}.\n\n"
                f"At {payload.enquiries_per_week} enquiries/week × ₦{payload.avg_deal_value_naira:,} avg deal\n"
                f"× 30% conservative leakage from slow replies, you're losing roughly:\n\n"
                f"  • ₦{weekly_loss:,} per week\n"
                f"  • ₦{monthly_loss:,} per month\n\n"
                f"Why 30%? HBR found that leads not replied to within 5 minutes are\n"
                f"9× less likely to close. WhatsApp Business penetration in Nigeria is\n"
                f"95%+, so customers expect minute-level replies. Most Lagos owners\n"
                f"can't physically maintain that — and lose the deal to whoever can.\n\n"
                f"What EYO does about it:\n"
                f"  1. Replies first, in your voice, with your price + bank details\n"
                f"  2. Carries the conversation — qualifies, follows up, catches payments\n"
                f"  3. Brings you in only at the moment a human handshake matters\n\n"
                f"If you'd like to see how this would run on your actual enquiries,\n"
                f"join early access: https://www.reachng.ng/waitlist\n\n"
                f"— EYO\n"
                f"   On behalf of the team at ReachNG\n"
                f"   hello@reachng.ng · Lagos"
            )
            html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#FAF6EE;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#1a1a1a;">
<table role="presentation" width="100%" style="background:#FAF6EE;padding:40px 16px;"><tr><td align="center">
<table role="presentation" width="560" style="max-width:560px;background:#fff;border-radius:14px;border:1px solid #E8DEC8;overflow:hidden;">
  <tr><td style="padding:32px 36px 18px 36px;border-bottom:1px solid #F1E8D4;">
    <div style="font-family:Georgia,serif;font-size:22px;font-weight:600;letter-spacing:-0.5px;">Reach<span style="color:#B85C38;">NG</span></div>
  </td></tr>
  <tr><td style="padding:32px 36px 8px 36px;">
    <div style="font-size:11px;letter-spacing:1.5px;font-weight:600;color:#7a6a3f;text-transform:uppercase;margin-bottom:8px;">WhatsApp leakage estimate</div>
    <div style="font-family:Georgia,serif;font-size:32px;font-weight:600;line-height:1.15;">{biz}: roughly ₦{monthly_loss//1_000_000}M/month leaking.</div>
  </td></tr>
  <tr><td style="padding:18px 36px 0 36px;font-size:14px;line-height:1.65;color:#3d3a33;">
    <p style="margin:0 0 12px 0;">Based on what you entered:</p>
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#FBF8F1;border:1px solid #F1E8D4;border-radius:10px;padding:14px 16px;margin-bottom:18px;">
      <tr><td style="font-size:13px;padding:4px 0;color:#7a6a3f;">Enquiries / week</td><td align="right" style="font-weight:700;">{payload.enquiries_per_week}</td></tr>
      <tr><td style="font-size:13px;padding:4px 0;color:#7a6a3f;">Avg deal value</td><td align="right" style="font-weight:700;">₦{payload.avg_deal_value_naira:,}</td></tr>
      <tr><td style="font-size:13px;padding:4px 0;color:#7a6a3f;">Conservative leakage</td><td align="right" style="font-weight:700;">30%</td></tr>
      <tr><td style="font-size:13px;padding:4px 0;color:#7a6a3f;border-top:1px solid #E8DEC8;padding-top:10px;">Weekly loss</td><td align="right" style="border-top:1px solid #E8DEC8;padding-top:10px;font-weight:700;color:#c62828;">₦{weekly_loss:,}</td></tr>
      <tr><td style="font-size:13px;padding:4px 0;color:#7a6a3f;">Monthly loss</td><td align="right" style="font-weight:700;color:#c62828;">₦{monthly_loss:,}</td></tr>
    </table>
    <p style="margin:0 0 12px 0;font-weight:600;">Why 30%?</p>
    <p style="margin:0 0 16px 0;">HBR found that leads not replied to within 5 minutes are <strong>9× less likely</strong> to close. Nigeria has 95%+ WhatsApp Business penetration, so customers expect minute-level replies. Most Lagos owners physically can't — and lose the deal to whoever can.</p>
    <p style="margin:24px 0 12px 0;font-weight:600;">What EYO does about it</p>
    <ol style="margin:0 0 18px 0;padding-left:20px;">
      <li style="margin-bottom:6px;">Replies first, in your voice, with your price + bank details</li>
      <li style="margin-bottom:6px;">Carries the conversation — qualifies, follows up, catches payments</li>
      <li>Brings you in only when a human handshake matters</li>
    </ol>
  </td></tr>
  <tr><td style="padding:8px 36px 32px 36px;" align="left">
    <a href="https://www.reachng.ng/waitlist" style="display:inline-block;background:#1a1a1a;color:#FAF6EE;text-decoration:none;padding:12px 22px;border-radius:8px;font-size:14px;font-weight:600;">See how it would handle your enquiries →</a>
  </td></tr>
  <tr><td style="padding:0 36px 32px 36px;font-size:14px;color:#3d3a33;border-top:1px solid #F1E8D4;padding-top:24px;">
    — EYO<br><span style="color:#7a6a3f;">On behalf of the team at ReachNG</span><br>
    <a href="mailto:hello@reachng.ng" style="color:#B85C38;text-decoration:none;">hello@reachng.ng</a> · Lagos
  </td></tr>
</table>
</td></tr></table></body></html>"""
            await send_email(
                to_email=payload.email,
                subject=subject,
                body=text,
                html=html,
                reply_to="hello@reachng.ng",
                force_smtp=True,
            )
            response["emailed"] = True
            log.info("calculator_leakage_emailed", to=payload.email,
                     weekly=weekly_loss, monthly=monthly_loss)
        except Exception as e:
            log.warning("calculator_leakage_email_failed", error=str(e))

    return response


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


# ─── Signup flow (self-serve) ────────────────────────────────────────────────

@router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
async def signup_page(request: Request, plan: Optional[str] = None):
    return _templates(request).TemplateResponse(request, "marketing/signup.html", {
        "selected_plan": (plan or "growth").lower(),
        "plans": _live_pricing(),
    })


@router.get("/signup/success", response_class=HTMLResponse, include_in_schema=False)
async def signup_success(request: Request, reference: Optional[str] = None):
    """Landed here after Paystack callback. We verify the reference and show the portal link."""
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
                        # Look up the provisioned client by Paystack reference
                        signup = get_db()["signups"].find_one({"paystack_reference": reference})
                        if signup and signup.get("portal_token"):
                            portal_path = f"/portal/{signup['portal_token']}"
                            business = signup.get("business_name")
                        else:
                            # Webhook hasn't fired yet — show pending state
                            error = "Payment confirmed. Provisioning your portal — check your WhatsApp + email in 60 seconds."
                    else:
                        error = f"Payment status: {data.get('status', 'unknown')}. Contact us if this is wrong."
                else:
                    error = "Could not verify payment with Paystack."
        except Exception as exc:
            log.error("signup_verify_failed", error=str(exc), reference=reference)
            error = "Verification failed. Don't worry — if you paid, we'll provision you within 5 minutes."

    return _templates(request).TemplateResponse(request, "marketing/signup_success.html", {
        "portal_path": portal_path,
        "business": business,
        "error": error,
        "reference": reference,
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
    annual: bool = False  # 15% off when true


@router.post("/api/v1/signup")
async def signup_initialize(payload: SignupPayload, request: Request):
    """Start a signup. Validates inputs, creates a pending signup row, initialises Paystack,
    returns the authorization URL the browser redirects to.
    """
    settings = get_settings()
    if not settings.paystack_secret_key:
        raise HTTPException(503, "Payments not configured. Email hello@reachng.ng to sign up directly.")

    vertical = payload.vertical.strip().lower()
    if vertical not in SUPPORTED_SIGNUP_VERTICALS:
        raise HTTPException(400, f"Vertical '{payload.vertical}' not supported. Try one of: {sorted(SUPPORTED_SIGNUP_VERTICALS)}")

    plan_info = _live_pricing()[payload.plan]
    base_ngn = plan_info["ngn"]
    if payload.annual:
        # Annual = 12 months × 0.85 (15% off)
        amount_ngn = int(base_ngn * 12 * 0.85)
        plan_label = f"{plan_info['label']} (Annual — 15% off)"
    else:
        amount_ngn = base_ngn
        plan_label = f"{plan_info['label']} (Monthly)"

    reference = f"RNG-SU-{uuid.uuid4().hex[:10].upper()}"
    base_url = str(request.base_url).rstrip("/")
    callback_url = f"{base_url}/signup/success?reference={reference}"

    body = {
        "email":     payload.owner_email,
        "amount":    amount_ngn * 100,  # kobo
        "reference": reference,
        "currency":  "NGN",
        "callback_url": callback_url,
        "metadata": {
            "kind":          "signup",
            "business_name": payload.business_name,
            "vertical":      vertical,
            "owner_name":    payload.owner_name,
            "owner_phone":   payload.owner_phone,
            "plan":          payload.plan,
            "plan_label":    plan_label,
            "annual":        payload.annual,
            "amount_ngn":    amount_ngn,
        },
    }

    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json=body,
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}", "Content-Type": "application/json"},
        )
    if r.status_code != 200 or not r.json().get("status"):
        log.error("paystack_init_failed", status=r.status_code, body=r.text[:500])
        raise HTTPException(502, "Could not initialise payment. Try again or email hello@reachng.ng.")

    data = r.json()["data"]

    # Stash a pending signup record so the webhook can stitch back later
    get_db()["signups"].insert_one({
        "paystack_reference": reference,
        "business_name": payload.business_name,
        "vertical": vertical,
        "owner_name": payload.owner_name,
        "owner_phone": payload.owner_phone,
        "owner_email": payload.owner_email,
        "plan": payload.plan,
        "plan_label": plan_label,
        "amount_ngn": amount_ngn,
        "annual": payload.annual,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })
    log.info("signup_initialised", business=payload.business_name, plan=payload.plan, reference=reference)

    return {"authorization_url": data["authorization_url"], "reference": reference}


@router.post("/webhooks/paystack", include_in_schema=False)
async def paystack_webhook(request: Request):
    """Paystack webhook → on charge.success, provision the client doc + portal token.
    Sends welcome message via Unipile (if configured) and writes the welcome to client_audit_log.
    """
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
        # Other Paystack flow (existing client invoice etc) — not our concern here
        return {"ok": True, "ignored": "non-signup"}

    reference = data.get("reference")
    db = get_db()
    signup = db["signups"].find_one({"paystack_reference": reference})
    if not signup:
        log.warning("paystack_signup_not_found", reference=reference)
        return {"ok": True, "ignored": "no-pending-signup"}
    if signup.get("status") == "provisioned":
        return {"ok": True, "ignored": "already-provisioned"}

    # ── Provision the client ──────────────────────────────────────────
    portal_token = pysecrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    paid_until = now + (timedelta(days=365) if signup.get("annual") else timedelta(days=30))

    clients = db["clients"]
    existing = clients.find_one({"name": signup["business_name"]})
    client_doc = {
        "name":            signup["business_name"],
        "vertical":        signup["vertical"],
        "brief":           "",
        "active":          True,
        "plan":            signup["plan"],
        "payment_status":  "paid",
        "monthly_fee_ngn": _live_pricing().get(signup["plan"], {}).get("ngn"),
        "paid_until":      paid_until,
        "owner_name":      signup["owner_name"],
        "owner_phone":     signup["owner_phone"],
        "owner_email":     signup["owner_email"],
        "agent_name":        "EYO",        # T0.2.6 — Lagos default, client can rename
        "preferred_channel": "whatsapp",
        "autopilot":       False,
        "signal_listening": False,
        "holding_message": "",
        "portal_token":    portal_token,
        "portal_created_at": now,
        "onboarded_at":    now,
        "updated_at":      now,
    }
    if existing:
        # Existing client (re-up or upgrade) — preserve token + briefs but refresh payment
        portal_token = existing.get("portal_token") or portal_token
        client_doc["portal_token"] = portal_token
        client_doc.pop("portal_created_at", None)
        clients.update_one({"_id": existing["_id"]}, {"$set": client_doc})
    else:
        clients.insert_one(client_doc)

    # Mark signup provisioned + stash portal token for the success page
    db["signups"].update_one(
        {"_id": signup["_id"]},
        {"$set": {
            "status": "provisioned",
            "portal_token": portal_token,
            "provisioned_at": now,
        }},
    )

    log.info("client_provisioned_from_signup", business=signup["business_name"], plan=signup["plan"], reference=reference)

    # ── Best-effort welcome message ──────────────────────────────────
    try:
        from tools.outreach import send_whatsapp_for_client
        portal_url = f"{request.base_url}portal/{portal_token}".replace("//portal", "/portal")
        welcome = (
            f"Welcome to ReachNG, {signup.get('owner_name', 'there')}! 🎉\n\n"
            f"Your {signup.get('plan_label', 'subscription')} is active until {paid_until.strftime('%d %b %Y')}.\n\n"
            f"Your portal: {portal_url}\n\n"
            f"Next step: open the portal, fill your Business Brief (5 mins), and we'll set up your WhatsApp pairing on a quick call. "
            f"Reply here when you're ready and we'll send the pairing link."
        )
        await send_whatsapp_for_client(phone=signup["owner_phone"], message=welcome)
    except Exception as exc:
        log.warning("signup_welcome_failed", error=str(exc), business=signup["business_name"])

    return {"ok": True, "provisioned": True, "portal_token": portal_token}


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
        ("/signup", "0.95", "monthly"),
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
