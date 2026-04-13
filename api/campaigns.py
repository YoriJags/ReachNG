from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Literal, Optional
from campaigns import CAMPAIGN_REGISTRY
from tools import get_pipeline_stats, get_daily_send_count, is_daily_limit_reached

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

VerticalType = Literal["real_estate", "recruitment", "events", "fintech", "legal", "logistics", "agriculture", "agency_sales"]


class RunCampaignRequest(BaseModel):
    vertical: VerticalType = Field(..., description="real_estate | recruitment | events | fintech | legal | logistics | agriculture")
    max_contacts: int = Field(default=30, ge=1, le=60)
    dry_run: bool = Field(default=True, description="Set to false to actually send messages")
    query_override: Optional[str] = Field(default=None, description="Custom Google Maps search query")
    client_name: Optional[str] = Field(default=None, description="Client name for agency mode — scopes the campaign to their brief")
    hitl_mode: bool = Field(default=False, description="Queue messages for human review before sending")
    cities: list[str] = Field(default=[], max_length=10, description="Run discovery across multiple cities. e.g. ['Lagos', 'Abuja', 'Port Harcourt']")
    target_sectors: list[str] = Field(default=[], description="agency_sales only: limit discovery to these sectors e.g. ['real_estate','recruitment']")
    min_rating: Optional[float] = Field(default=None, ge=1.0, le=5.0, description="Only contact businesses with Google rating >= this value")


class RunAllRequest(BaseModel):
    max_per_vertical: int = Field(default=20, ge=1, le=60)
    dry_run: bool = Field(default=True)


@router.post("/run")
async def run_campaign(body: RunCampaignRequest, background_tasks: BackgroundTasks):
    if is_daily_limit_reached() and not body.dry_run:
        raise HTTPException(429, "Daily send limit reached. Try again tomorrow.")

    campaign = CAMPAIGN_REGISTRY[body.vertical]()

    # Only go background for very large batches (>30) on live non-HITL runs
    # Smaller runs wait and return the full result including discovery breakdown
    if body.max_contacts > 30 and not body.dry_run and not body.hitl_mode:
        background_tasks.add_task(
            campaign.run,
            max_new_contacts=body.max_contacts,
            dry_run=body.dry_run,
            query_override=body.query_override,
            client_name=body.client_name,
            hitl_mode=body.hitl_mode,
            cities=body.cities or None,
            target_sectors=body.target_sectors or None,
            min_rating=body.min_rating,
        )
        return {
            "status": "started",
            "vertical": body.vertical,
            "message": f"Large campaign ({body.max_contacts} contacts) running in background. Check Live Logs for progress.",
            "discovery": {},
        }

    result = await campaign.run(
        max_new_contacts=body.max_contacts,
        dry_run=body.dry_run,
        query_override=body.query_override,
        client_name=body.client_name,
        hitl_mode=body.hitl_mode,
        cities=body.cities or None,
        target_sectors=body.target_sectors or None,
        min_rating=body.min_rating,
    )
    return result


@router.post("/run-all")
async def run_all_campaigns(body: RunAllRequest, background_tasks: BackgroundTasks):
    results = {}
    all_skipped = True
    for vertical, CampaignClass in CAMPAIGN_REGISTRY.items():
        if is_daily_limit_reached() and not body.dry_run:
            results[vertical] = {"skipped": "daily_limit_reached"}
            continue
        all_skipped = False
        campaign = CampaignClass()
        results[vertical] = await campaign.run(
            max_new_contacts=body.max_per_vertical,
            dry_run=body.dry_run,
        )
    if all_skipped and not body.dry_run:
        raise HTTPException(429, "Daily send limit reached. No campaigns ran.")
    return results


@router.post("/{vertical}/followups")
async def run_followups(vertical: VerticalType, dry_run: bool = True):
    campaign = CAMPAIGN_REGISTRY[vertical]()
    return await campaign.run_followups(dry_run=dry_run)


@router.get("/stats")
async def get_stats(vertical: Optional[str] = None):
    return get_pipeline_stats(vertical=vertical)


@router.get("/daily-limit")
async def daily_limit_status():
    from config import get_settings
    settings = get_settings()
    sent = get_daily_send_count()
    return {
        "sent_today": sent,
        "daily_limit": settings.daily_send_limit,
        "remaining": max(0, settings.daily_send_limit - sent),
        "limit_reached": is_daily_limit_reached(),
    }
