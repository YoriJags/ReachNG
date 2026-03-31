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
