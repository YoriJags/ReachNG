"""
FastMCP server — exposes ReachNG tools to Claude for agentic campaign runs.
Claude can call these tools in natural language to orchestrate full campaigns.

Run standalone: python -m mcp.server
Or mount into FastAPI via mcp.server.app
"""
from fastmcp import FastMCP
from typing import Optional
from tools import (
    get_pipeline_stats, get_followup_candidates,
    get_daily_send_count, is_daily_limit_reached,
    mark_replied, mark_converted, mark_opted_out,
)
from campaigns import CAMPAIGN_REGISTRY

mcp = FastMCP(
    name="ReachNG",
    instructions=(
        "You are the ReachNG campaign operator. "
        "Use these tools to run outreach campaigns for Lagos businesses. "
        "Always check the daily limit before running campaigns. "
        "Always confirm before sending to more than 20 contacts at once."
    ),
)


# ─── Campaign tools ───────────────────────────────────────────────────────────

@mcp.tool()
async def run_campaign(
    vertical: str,
    max_contacts: int = 30,
    dry_run: bool = True,
) -> dict:
    """
    Run an outreach campaign for a vertical.

    Args:
        vertical: One of "real_estate", "recruitment", "events"
        max_contacts: Maximum number of new contacts to reach (default 30, max 60)
        dry_run: If True, generate messages but do NOT send. Always start with dry_run=True.

    Returns campaign summary with sent/skipped/error counts.
    """
    if vertical not in CAMPAIGN_REGISTRY:
        return {"error": f"Unknown vertical '{vertical}'. Choose from: {list(CAMPAIGN_REGISTRY.keys())}"}

    max_contacts = min(max_contacts, 60)  # Hard cap
    campaign = CAMPAIGN_REGISTRY[vertical]()
    return await campaign.run(max_new_contacts=max_contacts, dry_run=dry_run)


@mcp.tool()
async def run_followups(vertical: str, dry_run: bool = True) -> dict:
    """
    Send follow-up messages to contacts who haven't replied after 48 hours.

    Args:
        vertical: One of "real_estate", "recruitment", "events"
        dry_run: If True, generate messages but do NOT send.
    """
    if vertical not in CAMPAIGN_REGISTRY:
        return {"error": f"Unknown vertical: {vertical}"}

    campaign = CAMPAIGN_REGISTRY[vertical]()
    return await campaign.run_followups(dry_run=dry_run)


@mcp.tool()
async def run_all_campaigns(dry_run: bool = True, max_per_vertical: int = 20) -> dict:
    """
    Run campaigns for all three verticals in sequence.

    Args:
        dry_run: If True, generate messages but do NOT send.
        max_per_vertical: Max contacts per vertical (default 20).
    """
    results = {}
    for vertical, CampaignClass in CAMPAIGN_REGISTRY.items():
        if is_daily_limit_reached():
            results[vertical] = {"skipped": "daily_limit_reached"}
            continue
        campaign = CampaignClass()
        results[vertical] = await campaign.run(
            max_new_contacts=max_per_vertical,
            dry_run=dry_run,
        )
    return results


# ─── Status tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_stats(vertical: Optional[str] = None) -> dict:
    """
    Get pipeline stats — contacts per status, daily send count.

    Args:
        vertical: Filter by vertical, or None for all verticals combined.
    """
    return get_pipeline_stats(vertical=vertical)


@mcp.tool()
def check_daily_limit() -> dict:
    """Check how many messages have been sent today vs. the daily limit."""
    from config import get_settings
    settings = get_settings()
    sent = get_daily_send_count()
    return {
        "sent_today": sent,
        "daily_limit": settings.daily_send_limit,
        "remaining": max(0, settings.daily_send_limit - sent),
        "limit_reached": is_daily_limit_reached(),
    }


@mcp.tool()
def get_followups_due(vertical: Optional[str] = None) -> list[dict]:
    """
    List contacts currently due for a follow-up message.

    Args:
        vertical: Filter by vertical, or None for all.
    """
    candidates = get_followup_candidates(vertical=vertical)
    # Sanitise ObjectIds for JSON serialisation
    return [
        {
            "id": str(c["_id"]),
            "name": c["name"],
            "vertical": c["vertical"],
            "phone": c.get("phone"),
            "outreach_count": c.get("outreach_count", 0),
            "last_contacted_at": str(c.get("last_contacted_at", "")),
        }
        for c in candidates
    ]


# ─── Contact management tools ─────────────────────────────────────────────────

@mcp.tool()
def mark_contact_replied(contact_id: str) -> dict:
    """Mark a contact as having replied — removes them from follow-up queue."""
    mark_replied(contact_id)
    return {"success": True, "contact_id": contact_id, "status": "replied"}


@mcp.tool()
def mark_contact_converted(contact_id: str) -> dict:
    """Mark a contact as converted (became a paying client)."""
    mark_converted(contact_id)
    return {"success": True, "contact_id": contact_id, "status": "converted"}


@mcp.tool()
def mark_contact_opted_out(contact_id: str) -> dict:
    """Mark a contact as opted out — they will never be contacted again."""
    mark_opted_out(contact_id)
    return {"success": True, "contact_id": contact_id, "status": "opted_out"}
