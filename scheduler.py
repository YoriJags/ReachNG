"""
APScheduler — automated nightly campaign runs.
Runs at 10pm Lagos time (UTC+1) every day.
Mounted into the FastAPI app lifecycle.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from campaigns import CAMPAIGN_REGISTRY
from tools import is_daily_limit_reached
from tools.reply_router import process_replies
from tools.brief import compile_morning_brief
from tools.notifier import notify_owner
import structlog

log = structlog.get_logger()

scheduler = AsyncIOScheduler(timezone="Africa/Lagos")


async def _nightly_outreach():
    """Main campaign run — discovers new contacts and sends outreach."""
    log.info("nightly_outreach_start")

    for vertical, CampaignClass in CAMPAIGN_REGISTRY.items():
        if is_daily_limit_reached():
            log.info("daily_limit_reached_scheduler", vertical=vertical)
            break
        try:
            campaign = CampaignClass()
            result = await campaign.run(max_new_contacts=20, dry_run=False)
            log.info("nightly_vertical_done", vertical=vertical, result=result)
        except Exception as e:
            log.error("nightly_vertical_failed", vertical=vertical, error=str(e))


async def _followup_run():
    """Follow-up run — sends second touch to non-responders."""
    log.info("followup_run_start")

    for vertical, CampaignClass in CAMPAIGN_REGISTRY.items():
        try:
            campaign = CampaignClass()
            result = await campaign.run_followups(dry_run=False)
            log.info("followup_vertical_done", vertical=vertical, result=result)
        except Exception as e:
            log.error("followup_vertical_failed", vertical=vertical, error=str(e))


async def _reply_poll():
    """Poll Unipile for inbound replies and route them to contacts."""
    log.info("reply_poll_start")
    try:
        result = await process_replies()
        log.info("reply_poll_done", **result)
    except Exception as e:
        log.error("reply_poll_failed", error=str(e))


async def _morning_brief():
    """Compile overnight stats and send WhatsApp brief to owner at 8am Lagos time."""
    log.info("morning_brief_start")
    try:
        brief = compile_morning_brief()
        await notify_owner(brief)
        log.info("morning_brief_sent")
    except Exception as e:
        log.error("morning_brief_failed", error=str(e))


def setup_scheduler():
    """Register all jobs and return configured scheduler."""

    # Morning brief: every day at 8am Lagos time
    scheduler.add_job(
        _morning_brief,
        CronTrigger(hour=8, minute=0, timezone="Africa/Lagos"),
        id="morning_brief",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Reply polling: every 30 minutes between 8am and midnight Lagos time
    scheduler.add_job(
        _reply_poll,
        CronTrigger(hour="8-23", minute="*/30", timezone="Africa/Lagos"),
        id="reply_poll",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Main outreach: every night at 10pm Lagos time
    scheduler.add_job(
        _nightly_outreach,
        CronTrigger(hour=22, minute=0, timezone="Africa/Lagos"),
        id="nightly_outreach",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Follow-ups: every day at 2pm (48h after the prior evening's sends)
    scheduler.add_job(
        _followup_run,
        CronTrigger(hour=14, minute=0, timezone="Africa/Lagos"),
        id="followup_run",
        replace_existing=True,
        misfire_grace_time=300,
    )

    return scheduler
