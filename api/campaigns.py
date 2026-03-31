from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from campaigns import CAMPAIGN_REGISTRY
from tools import get_pipeline_stats, get_daily_send_count, is_daily_limit_reached

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


class RunCampaignRequest(BaseModel):
    vertical: str = Field(..., description="real_estate | recruitment | events")
    max_contacts: int = Field(default=30, ge=1, le=60)
    dry_run: bool = Field(default=True, description="Set to false to actually send messages")
    query_override: Optional[str] = Field(default=None, description="Custom Google Maps search query")
    client_name: Optional[str] = Field(default=None, description="Client name for agency mode — scopes the campaign to their brief")


class RunAllRequest(BaseModel):
    max_per_vertical: int = Field(default=20, ge=1, le=60)
    dry_run: bool = Field(default=True)


@router.post("/run")
async def run_campaign(body: RunCampaignRequest, background_tasks: BackgroundTasks):
    if body.vertical not in CAMPAIGN_REGISTRY:
        raise HTTPException(400, f"Unknown vertical. Choose from: {list(CAMPAIGN_REGISTRY.keys())}")

    if is_daily_limit_reached() and not body.dry_run:
        raise HTTPException(429, "Daily send limit reached. Try again tomorrow.")

    campaign = CAMPAIGN_REGISTRY[body.vertical]()

    # Run in background for large batches
    if body.max_contacts > 10 and not body.dry_run:
        background_tasks.add_task(
            campaign.run,
            max_new_contacts=body.max_contacts,
            dry_run=body.dry_run,
            query_override=body.query_override,
        )
        return {"status": "started", "vertical": body.vertical, "message": "Campaign running in background"}

    result = await campaign.run(
        max_new_contacts=body.max_contacts,
        dry_run=body.dry_run,
        query_override=body.query_override,
        client_name=body.client_name,
    )
    return result


@router.post("/run-all")
async def run_all_campaigns(body: RunAllRequest, background_tasks: BackgroundTasks):
    results = {}
    for vertical, CampaignClass in CAMPAIGN_REGISTRY.items():
        if is_daily_limit_reached() and not body.dry_run:
            results[vertical] = {"skipped": "daily_limit_reached"}
            continue
        campaign = CampaignClass()
        results[vertical] = await campaign.run(
            max_new_contacts=body.max_per_vertical,
            dry_run=body.dry_run,
        )
    return results


@router.post("/{vertical}/followups")
async def run_followups(vertical: str, dry_run: bool = True):
    if vertical not in CAMPAIGN_REGISTRY:
        raise HTTPException(400, f"Unknown vertical: {vertical}")
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
