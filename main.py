"""
ReachNG — AI-powered outreach machine for Lagos businesses.
Three verticals: Real Estate | Recruitment | Events
"""
import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import RedirectResponse
from tools.log_buffer import buffer_processor

# Configure structlog to capture logs into the dashboard buffer
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        buffer_processor,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from posthog import Posthog
from database import ensure_indexes
from services.data_liberation.store import ensure_data_indexes
from scheduler import setup_scheduler
from api import campaigns_router, contacts_router, clients_router, dashboard_router, data_router, approvals_router, approvals_public_router, roi_router, social_router, hooks_router, portal_router, ab_router, referrals_router, competitors_router, invoices_router, b2c_router, b2c_public_router, invoice_chaser_router, school_fees_router, webhooks_router, plans_router, legal_review_router, loan_officer_router, debt_collector_router, market_credit_router, product_auth_router, material_check_router, fuel_reprice_router, float_optimizer_router, fx_salary_router, moonlighting_router, salary_erosion_router, fx_lock_router, hr_suite_router, estate_router, portal_estate_router, portal_talent_router, closer_router, closer_public_router, brief_router, brief_public_router, legal_router, legal_public_router
from api.venue_capacity import router as venue_capacity_router, ensure_capacity_indexes
from api.paystack import router as paystack_router
from api.fleet_dispatcher import router as fleet_dispatcher_router
from api.market_os import router as market_os_router
from api.payroll import router as payroll_router
from api.rent_roll import router as rent_roll_router
from api.plans import seed_plans_if_empty
from auth import require_auth
from mcp_server import mcp
from config import get_settings

log = structlog.get_logger()

_posthog: Posthog | None = None


def get_posthog() -> Posthog | None:
    return _posthog


def _validate_env(settings) -> None:
    """Fail fast with a clear message if critical env vars are missing or placeholder."""
    placeholder_prefixes = ("sk-ant-...", "AIza...", "mongodb+srv://...", "...")
    issues = []

    checks = {
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "MONGODB_URI": settings.mongodb_uri,
    }
    for name, val in checks.items():
        if not val or any(val.startswith(p) for p in placeholder_prefixes):
            issues.append(f"  ✗ {name} is missing or still a placeholder")

    if settings.app_env == "production":
        if not settings.dashboard_user or not settings.dashboard_pass:
            issues.append("  ✗ DASHBOARD_USER / DASHBOARD_PASS must be set in production")

    if issues:
        msg = "\n".join(["[ReachNG] Cannot start — fix your .env:\n"] + issues)
        raise SystemExit(msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _posthog
    # Startup
    settings = get_settings()
    _validate_env(settings)
    log.info("reachng_starting", env=settings.app_env)
    if settings.posthog_api_key:
        _posthog = Posthog(
            api_key=settings.posthog_api_key,
            host=settings.posthog_host,
        )
        _posthog.capture("reachng", event="server_started", properties={"env": settings.app_env})
        log.info("posthog_initialized", host=settings.posthog_host)
    try:
        ensure_indexes()
        ensure_data_indexes()
        seed_plans_if_empty()
    except Exception as exc:
        raise SystemExit(
            f"[ReachNG] Cannot connect to MongoDB.\n"
            f"  Check MONGODB_URI in your .env\n"
            f"  Error: {exc}"
        ) from exc
    from tools.hitl import ensure_approval_indexes
    from tools.roi import ensure_roi_indexes
    from tools.social import ensure_social_indexes
    from tools.hooks import ensure_hooks_indexes
    from tools.ab_testing import ensure_ab_indexes
    from tools.referral import ensure_referral_indexes
    from tools.competitor import ensure_competitor_indexes
    from tools.invoices import ensure_invoice_indexes
    from tools.csv_import import ensure_b2c_indexes
    from api.b2c import _ensure_lead_imports_indexes
    ensure_approval_indexes()
    ensure_roi_indexes()
    ensure_social_indexes()
    ensure_hooks_indexes()
    ensure_ab_indexes()
    ensure_referral_indexes()
    ensure_competitor_indexes()
    ensure_invoice_indexes()
    ensure_b2c_indexes()
    _ensure_lead_imports_indexes()
    from api.school_fees import ensure_school_fees_indexes
    ensure_school_fees_indexes()
    from services.fleet_dispatcher.store import ensure_indexes as ensure_fleet_indexes
    ensure_fleet_indexes()
    from services.legal_review.store import ensure_legal_indexes
    ensure_legal_indexes()
    from services.loan_officer.store import ensure_indexes as ensure_loan_indexes
    ensure_loan_indexes()
    from services.hr_suite.payroll import ensure_payroll_indexes
    from services.estate.rent_roll import ensure_rent_indexes
    from services.closer import ensure_closer_indexes
    from services.brief import ensure_brief_indexes, seed_default_primers
    from api.legal import ensure_legal_indexes
    ensure_payroll_indexes()
    ensure_rent_indexes()
    ensure_closer_indexes()
    ensure_brief_indexes()
    seed_default_primers()
    ensure_legal_indexes()
    ensure_capacity_indexes()
    scheduler = setup_scheduler()
    scheduler.start()
    log.info("scheduler_started", jobs=[job.id for job in scheduler.get_jobs()])
    yield
    # Shutdown
    scheduler.shutdown(wait=False)
    if _posthog:
        _posthog.shutdown()
    log.info("reachng_stopped")


app = FastAPI(
    title="ReachNG",
    description="AI-powered outreach machine for Lagos businesses — Real Estate, Recruitment, Events",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.templates = Jinja2Templates(directory="templates")

# CORS: restrict to configured origins in production.
# Set ALLOWED_ORIGINS=https://yourdomain.com in Railway env vars.
# Falls back to wildcard in development only.
_raw_origins = getattr(get_settings(), "allowed_origins", "") or ""
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

@app.middleware("http")
async def posthog_request_middleware(request: Request, call_next):
    response = await call_next(request)
    ph = get_posthog()
    if ph and request.url.path.startswith("/api/"):
        ph.capture(
            "reachng",
            event="api_request",
            properties={
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
            },
        )
    return response


# REST API routes — all protected by Basic Auth
_auth = {"dependencies": [Depends(require_auth)]}

app.include_router(campaigns_router,   prefix="/api/v1", **_auth)
app.include_router(contacts_router,    prefix="/api/v1", **_auth)
app.include_router(clients_router,     prefix="/api/v1", **_auth)
app.include_router(data_router,        prefix="/api/v1", **_auth)
app.include_router(approvals_router,   prefix="/api/v1", **_auth)
app.include_router(approvals_public_router, prefix="/api/v1")  # token-gated, no Basic Auth
app.include_router(roi_router,         prefix="/api/v1", **_auth)
app.include_router(social_router,      prefix="/api/v1", **_auth)
app.include_router(hooks_router,       prefix="/api/v1", **_auth)
app.include_router(ab_router,          prefix="/api/v1", **_auth)
app.include_router(referrals_router,   prefix="/api/v1", **_auth)
app.include_router(competitors_router, prefix="/api/v1", **_auth)
app.include_router(invoices_router,    prefix="/api/v1", **_auth)
app.include_router(b2c_router,            prefix="/api/v1", **_auth)
app.include_router(b2c_public_router,     prefix="/api/v1")  # token-gated, no Basic Auth
app.include_router(invoice_chaser_router, prefix="/api/v1", **_auth)
app.include_router(school_fees_router,    prefix="/api/v1", **_auth)
app.include_router(plans_router,          prefix="/api/v1", **_auth)
app.include_router(webhooks_router,       prefix="/api/v1")  # No Basic Auth — Unipile posts freely
app.include_router(portal_router)        # Portal uses token auth — no Basic Auth
app.include_router(legal_review_router)  # /legal/... — public demo (no Basic Auth)
app.include_router(loan_officer_router)  # /loan/portal public; /loan/apply + management require Basic Auth
app.include_router(debt_collector_router,   **_auth)
app.include_router(market_credit_router,    **_auth)
app.include_router(product_auth_router,     **_auth)
app.include_router(material_check_router,   **_auth)
app.include_router(fuel_reprice_router,     **_auth)
app.include_router(float_optimizer_router,  **_auth)
app.include_router(fx_salary_router,        **_auth)
app.include_router(moonlighting_router,     **_auth)
app.include_router(salary_erosion_router,   **_auth)
app.include_router(fx_lock_router,          **_auth)
app.include_router(hr_suite_router,         **_auth)
app.include_router(estate_router,           **_auth)
app.include_router(portal_estate_router)   # Token-gated — no Basic Auth
app.include_router(portal_talent_router)   # Token-gated — no Basic Auth
app.include_router(paystack_router,          prefix="/api/v1", **_auth)
app.include_router(venue_capacity_router,    prefix="/api/v1")
app.include_router(fleet_dispatcher_router,  prefix="/api/v1", **_auth)
app.include_router(market_os_router,         prefix="/api/v1", **_auth)
app.include_router(payroll_router,            **_auth)
app.include_router(rent_roll_router,          **_auth)
# Closer admin: brief edits, cross-client lead mgmt — Basic Auth.
app.include_router(closer_router,             prefix="/api/v1", **_auth)
app.include_router(brief_router,               prefix="/api/v1", **_auth)
app.include_router(brief_public_router,        prefix="/api/v1")  # token-gated, no Basic Auth
app.include_router(legal_router,               prefix="/api/v1", **_auth)
app.include_router(legal_public_router,        prefix="/api/v1")  # token-gated, no Basic Auth
# Closer public: token-gated intake (webhook + email stub) + portal reads — no Basic Auth.
app.include_router(closer_public_router,      prefix="/api/v1")
app.include_router(dashboard_router, **_auth)

# Mount MCP server — exposes tools to Claude
app.mount("/mcp", mcp.http_app())


@app.get("/")
async def root(request: Request):
    # Browsers land on the dashboard; API/health probes get JSON.
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return RedirectResponse(url="/dashboard", status_code=302)
    return {
        "service": "ReachNG",
        "status": "running",
        "verticals": ["real_estate", "recruitment", "events"],
        "docs": "/docs",
        "mcp": "/mcp",
        "dashboard": "/dashboard",
    }


@app.get("/health")
async def health():
    from database import get_db
    try:
        get_db().command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@app.get("/api/v1/logs/recent", dependencies=[Depends(require_auth)])
async def recent_logs(limit: int = 100):
    """Return recent backend log entries for the dashboard live log panel."""
    from tools.log_buffer import get_recent
    return get_recent(limit=min(limit, 200))


@app.delete("/api/v1/logs/clear", dependencies=[Depends(require_auth)])
async def clear_logs():
    from tools.log_buffer import clear
    clear()
    return {"cleared": True}


@app.post("/api/v1/demo/seed-landlord", dependencies=[Depends(require_auth)])
async def seed_demo_landlord(wipe: bool = False):
    """Seed a realistic Lagos demo landlord with 5 units, 4 tenants, mixed ledger.

    Use for sales/demo pitches — idempotent. Pass wipe=true to reset.
    Returns the portal path so you can open the EstateOS portal directly.
    """
    from scripts.seed_demo_landlord import seed, wipe as wipe_fn, DEMO_NAME
    if wipe:
        wipe_fn()
    token = seed()
    return {
        "client":     DEMO_NAME,
        "portal_url": f"/portal/{token}",
        "estate_url": f"/portal/estate/{token}",
        "token":      token,
        "wiped":      wipe,
    }


@app.post("/api/v1/demo/seed-talent", dependencies=[Depends(require_auth)])
async def seed_demo_talent(wipe: bool = False):
    """Seed a realistic Lagos demo company with TalentOS data (staff, leave, PENCOM, probation).

    Idempotent. Pass wipe=true to reset. Shares portal_token with seed-landlord if run after it.
    """
    from scripts.seed_demo_talent import seed, wipe as wipe_fn, DEMO_NAME
    if wipe:
        wipe_fn()
    token = seed()
    return {
        "client":     DEMO_NAME,
        "talent_url": f"/portal/talent/{token}",
        "token":      token,
        "wiped":      wipe,
    }



@app.post("/api/v1/demo/seed-all", dependencies=[Depends(require_auth)])
async def seed_demo_all(wipe: bool = False):
    """Seed both EstateOS and TalentOS demo data under one 'ReachNG Demo' client.

    Single portal_token — one 'View Portal' button opens both ReachNG portals.
    """
    from scripts.seed_demo_landlord import seed as seed_estate, wipe as wipe_estate, DEMO_NAME
    from scripts.seed_demo_talent import seed as seed_talent, wipe as wipe_talent
    if wipe:
        wipe_estate()
        wipe_talent()
    token = seed_estate()   # creates/upserts the single 'ReachNG Demo' client
    seed_talent()           # seeds HR data under the same client, reuses token
    return {
        "client":      DEMO_NAME,
        "estate_url":  f"/portal/estate/{token}",
        "talent_url":  f"/portal/talent/{token}",
        "token":       token,
        "wiped":       wipe,
    }


@app.post("/api/v1/clients/backfill-tokens", dependencies=[Depends(require_auth)])
async def backfill_portal_tokens():
    """Generate portal_token for any active client that doesn't have one yet."""
    import secrets as _secrets
    from datetime import datetime, timezone
    db = get_db()
    updated = []
    for c in db["clients"].find({"active": True, "portal_token": {"$exists": False}}):
        token = _secrets.token_urlsafe(24)
        db["clients"].update_one(
            {"_id": c["_id"]},
            {"$set": {"portal_token": token, "portal_created_at": datetime.now(timezone.utc)}},
        )
        updated.append(c["name"])
    return {"backfilled": len(updated), "clients": updated}


@app.get("/api/v1/health", dependencies=[Depends(require_auth)])
async def rich_health():
    """Detailed integration health check for the onboarding wizard and dashboard."""
    import httpx
    from config import get_settings
    settings = get_settings()
    result = {}

    # Auth configured
    result["auth_configured"] = bool(settings.dashboard_user and settings.dashboard_pass)

    # Claude
    result["claude"] = "ok" if settings.anthropic_api_key and not settings.anthropic_api_key.startswith("sk-ant-...") else "missing"

    # MongoDB
    try:
        from database import get_db
        get_db().command("ping")
        result["mongodb"] = "ok"
    except Exception:
        result["mongodb"] = "error"

    # Google Maps
    try:
        if not settings.google_maps_api_key:
            result["maps"] = "missing"
        else:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    "https://maps.googleapis.com/maps/api/place/textsearch/json",
                    params={"query": "restaurant Lagos", "key": settings.google_maps_api_key},
                )
                result["maps"] = "ok" if r.status_code == 200 and r.json().get("status") in ("OK", "ZERO_RESULTS") else "error"
    except Exception:
        result["maps"] = "error"

    # Apollo
    try:
        if not settings.apollo_api_key:
            result["apollo"] = "missing"
        else:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.post(
                    "https://api.apollo.io/v1/mixed_companies/search",
                    json={"q_organization_name": "test", "page": 1, "per_page": 1},
                    headers={"x-api-key": settings.apollo_api_key, "Content-Type": "application/json"},
                )
                # 200 = success, 422 = valid key bad params, 403 = valid key plan-limited
                result["apollo"] = "ok" if r.status_code in (200, 422, 403) else "error"
    except Exception:
        result["apollo"] = "error"

    # Unipile
    # Meta WhatsApp
    result["whatsapp"] = "ok" if (settings.meta_phone_number_id and settings.meta_access_token) else "missing"

    # Gmail
    result["email"] = "ok" if (settings.gmail_address and settings.gmail_app_password) else "missing"

    overall = "ok" if all(v == "ok" for v in result.values() if v != True) else "degraded"
    result["status"] = overall
    return result


@app.post("/api/v1/system/sweep", dependencies=[Depends(require_auth)])
async def trigger_system_sweep():
    """Run a full system health sweep on demand. Returns structured report."""
    from tools.system_sweep import run_sweep
    return await run_sweep()


@app.get("/debug/apollo", dependencies=[Depends(require_auth)])
async def debug_apollo():
    """Hit Apollo API directly and return the raw response for diagnostics."""
    import httpx
    settings = get_settings()
    api_key = getattr(settings, "apollo_api_key", None)
    if not api_key:
        return {"error": "APOLLO_API_KEY not set in environment"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.apollo.io/v1/mixed_companies/search",
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": api_key},
            json={
                "q_keywords": "real estate property development",
                "organization_locations": ["Lagos, Nigeria"],
                "page": 1,
                "per_page": 5,
            },
        )
    data = resp.json()
    orgs = data.get("organizations", [])
    return {
        "http_status": resp.status_code,
        "orgs_count": len(orgs),
        "error": data.get("error"),
        "message": data.get("message"),
        "first_org": orgs[0].get("name") if orgs else None,
        "key_prefix": api_key[:8] + "...",
    }


@app.get("/debug/maps", dependencies=[Depends(require_auth)])
async def debug_maps():
    """Hit Google Places API directly and return the raw response for diagnostics."""
    import httpx
    settings = get_settings()
    api_key = getattr(settings, "google_maps_api_key", None)
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY not set in environment"}
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": "real estate agency Lagos Nigeria", "key": api_key, "region": "ng"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
    return {
        "status": data.get("status"),
        "error_message": data.get("error_message"),
        "results_count": len(data.get("results", [])),
        "first_result": data.get("results", [{}])[0].get("name") if data.get("results") else None,
        "key_prefix": api_key[:8] + "...",
    }


@app.get("/debug/apify", dependencies=[Depends(require_auth)])
async def debug_apify():
    """Verify Apify token and test TikTok scraper with a single hashtag."""
    import httpx
    settings = get_settings()
    token = getattr(settings, "apify_api_token", None)
    if not token:
        return {"error": "APIFY_API_TOKEN not set in environment"}

    url = "https://api.apify.com/v2/acts/clockworks~tiktok-scraper/run-sync-get-dataset-items"
    params = {"token": token, "timeout": 30, "memory": 256}
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(url, json={
                "hashtags": ["lagosrealestate"],
                "resultsPerPage": 3,
                "shouldDownloadVideos": False,
                "shouldDownloadCovers": False,
            }, params=params)
        items = resp.json() if resp.status_code == 200 else []
        return {
            "http_status": resp.status_code,
            "token_prefix": token[:8] + "...",
            "items_returned": len(items) if isinstance(items, list) else 0,
            "first_item_author": items[0].get("authorMeta", {}).get("name") if items and isinstance(items, list) else None,
            "error": items.get("error") if isinstance(items, dict) else None,
        }
    except Exception as e:
        return {"error": str(e), "token_prefix": token[:8] + "..."}


if __name__ == "__main__":
    import os
    settings = get_settings()
    port = int(os.environ.get("PORT", settings.app_port))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
