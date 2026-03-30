"""
ReachNG — AI-powered outreach machine for Lagos businesses.
Three verticals: Real Estate | Recruitment | Events
"""
import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import ensure_indexes
from services.data_liberation.store import ensure_data_indexes
from scheduler import setup_scheduler
from api import campaigns_router, contacts_router, clients_router, dashboard_router, data_router, approvals_router, roi_router, social_router, hooks_router
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
    ensure_approval_indexes()
    ensure_roi_indexes()
    ensure_social_indexes()
    ensure_hooks_indexes()
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

# REST API routes
app.include_router(campaigns_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(clients_router, prefix="/api/v1")
app.include_router(data_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(roi_router, prefix="/api/v1")
app.include_router(social_router, prefix="/api/v1")
app.include_router(hooks_router, prefix="/api/v1")
app.include_router(dashboard_router)

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
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
