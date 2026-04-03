"""
ReachNG — AI-powered outreach machine for Lagos businesses.
Three verticals: Real Estate | Recruitment | Events
"""
import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from database import ensure_indexes
from services.data_liberation.store import ensure_data_indexes
from scheduler import setup_scheduler
from api import campaigns_router, contacts_router, clients_router, dashboard_router, data_router, approvals_router, roi_router, social_router, hooks_router, portal_router, ab_router, referrals_router, competitors_router, invoices_router
from auth import require_auth
from mcp_server import mcp
from config import get_settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    log.info("reachng_starting", env=settings.app_env)
    ensure_indexes()
    ensure_data_indexes()
    from tools.hitl import ensure_approval_indexes
    from tools.roi import ensure_roi_indexes
    from tools.social import ensure_social_indexes
    from tools.hooks import ensure_hooks_indexes
    from tools.ab_testing import ensure_ab_indexes
    from tools.referral import ensure_referral_indexes
    from tools.competitor import ensure_competitor_indexes
    from tools.invoices import ensure_invoice_indexes
    ensure_approval_indexes()
    ensure_roi_indexes()
    ensure_social_indexes()
    ensure_hooks_indexes()
    ensure_ab_indexes()
    ensure_referral_indexes()
    ensure_competitor_indexes()
    ensure_invoice_indexes()
    scheduler = setup_scheduler()
    scheduler.start()
    log.info("scheduler_started", jobs=[job.id for job in scheduler.get_jobs()])
    yield
    # Shutdown
    scheduler.shutdown(wait=False)
    log.info("reachng_stopped")


app = FastAPI(
    title="ReachNG",
    description="AI-powered outreach machine for Lagos businesses — Real Estate, Recruitment, Events",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
            "https://api.apollo.io/v1/mixed_people/search",
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
