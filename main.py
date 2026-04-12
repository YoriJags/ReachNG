"""
ReachNG — AI-powered outreach machine for Lagos businesses.
Three verticals: Real Estate | Recruitment | Events
"""
import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from posthog import Posthog
from database import ensure_indexes
from services.data_liberation.store import ensure_data_indexes
from scheduler import setup_scheduler
from api import campaigns_router, contacts_router, clients_router, dashboard_router, data_router, approvals_router, roi_router, social_router, hooks_router, portal_router, ab_router, referrals_router, competitors_router, invoices_router, b2c_router, invoice_chaser_router, school_fees_router, webhooks_router
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
        "UNIPILE_API_KEY": settings.unipile_api_key,
        "UNIPILE_DSN": settings.unipile_dsn,
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
    ensure_approval_indexes()
    ensure_roi_indexes()
    ensure_social_indexes()
    ensure_hooks_indexes()
    ensure_ab_indexes()
    ensure_referral_indexes()
    ensure_competitor_indexes()
    ensure_invoice_indexes()
    ensure_b2c_indexes()
    from api.school_fees import ensure_school_fees_indexes
    ensure_school_fees_indexes()
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
app.include_router(roi_router,         prefix="/api/v1", **_auth)
app.include_router(social_router,      prefix="/api/v1", **_auth)
app.include_router(hooks_router,       prefix="/api/v1", **_auth)
app.include_router(ab_router,          prefix="/api/v1", **_auth)
app.include_router(referrals_router,   prefix="/api/v1", **_auth)
app.include_router(competitors_router, prefix="/api/v1", **_auth)
app.include_router(invoices_router,    prefix="/api/v1", **_auth)
app.include_router(b2c_router,            prefix="/api/v1", **_auth)
app.include_router(invoice_chaser_router, prefix="/api/v1", **_auth)
app.include_router(school_fees_router,    prefix="/api/v1", **_auth)
app.include_router(webhooks_router,       prefix="/api/v1")  # No Basic Auth — Unipile posts freely
app.include_router(portal_router)        # Portal uses token auth — no Basic Auth
app.include_router(dashboard_router, **_auth)

# Mount MCP server — exposes tools to Claude
app.mount("/mcp", mcp.http_app())


@app.get("/")
async def root():
    return {
        "service": "ReachNG",
        "status": "running",
        "verticals": ["real_estate", "recruitment", "events"],
        "docs": "/docs",
        "mcp": "/mcp",
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
                result["apollo"] = "ok" if r.status_code in (200, 422) else "error"
    except Exception:
        result["apollo"] = "error"

    # Unipile
    try:
        if not settings.unipile_api_key or not settings.unipile_dsn:
            result["unipile"] = "missing"
        else:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    f"https://{settings.unipile_dsn}/api/v1/accounts",
                    headers={"X-API-KEY": settings.unipile_api_key},
                )
                result["unipile"] = "ok" if r.status_code in (200, 401) else "error"
    except Exception:
        result["unipile"] = "error"

    overall = "ok" if all(v == "ok" for v in result.values() if v != True) else "degraded"
    result["status"] = overall
    return result


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
