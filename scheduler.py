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
            result = await campaign.run(max_new_contacts=20, dry_run=False, hitl_mode=True)
            log.info("nightly_vertical_done", vertical=vertical, result=result)
        except Exception as e:
            log.error("nightly_vertical_failed", vertical=vertical, error=str(e))


async def _followup_run():
    """Follow-up run — sends second touch to non-responders."""
    log.info("followup_run_start")

    for vertical, CampaignClass in CAMPAIGN_REGISTRY.items():
        try:
            campaign = CampaignClass()
            result = await campaign.run_followups(dry_run=False, hitl_mode=True)
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


async def _invoice_reminder_run():
    """Daily invoice collection — sends WhatsApp reminders for overdue invoices."""
    from tools.invoices import get_due_reminders, record_reminder_sent, REMINDER_SEQUENCE
    from agent import generate_invoice_reminder
    from tools.outreach import send_whatsapp
    from datetime import datetime, timezone

    log.info("invoice_reminder_run_start")
    reminders = get_due_reminders()
    sent = 0
    errors = 0

    for invoice in reminders:
        # Determine which tone/stage to use based on current status
        stages = [s["stage"] for s in REMINDER_SEQUENCE]
        current_status = invoice.get("status", "pending")

        # Find the next stage in sequence
        if current_status == "pending":
            next_stage = REMINDER_SEQUENCE[0]
        else:
            try:
                idx = stages.index(current_status)
                if idx + 1 >= len(REMINDER_SEQUENCE):
                    continue  # Completed sequence
                next_stage = REMINDER_SEQUENCE[idx + 1]
            except ValueError:
                continue

        due_date = invoice.get("due_date")
        now = datetime.now(timezone.utc)
        days_overdue = (now - due_date).days if due_date else 0

        try:
            message = generate_invoice_reminder(
                client_name=invoice["client_name"],
                debtor_name=invoice["debtor_name"],
                amount_ngn=invoice["amount_ngn"],
                description=invoice.get("description", ""),
                days_overdue=days_overdue,
                tone=next_stage["tone"],
                reminder_count=invoice.get("reminder_count", 0),
            )
            result = await send_whatsapp(phone=invoice["debtor_phone"], message=message)
            if result.get("success", True):
                record_reminder_sent(invoice["id"], next_stage["stage"])
                sent += 1
                log.info("invoice_reminder_sent",
                    debtor=invoice["debtor_name"],
                    stage=next_stage["stage"],
                    amount=invoice["amount_ngn"],
                )
            else:
                errors += 1
        except Exception as e:
            log.error("invoice_reminder_failed", invoice_id=invoice["id"], error=str(e))
            errors += 1

    log.info("invoice_reminder_run_done", sent=sent, errors=errors)


async def _system_sweep():
    """Daily system sweep — checks all integrations and pipeline health at 7am."""
    from tools.system_sweep import run_and_notify
    log.info("system_sweep_start")
    try:
        report = await run_and_notify()
        log.info("system_sweep_done", overall=report["overall"],
                 failed=report["failed"], warned=report["warned"])
    except Exception as e:
        log.error("system_sweep_failed", error=str(e))


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

    # System sweep: every day at 7am Lagos time (before morning brief)
    scheduler.add_job(
        _system_sweep,
        CronTrigger(hour=7, minute=0, timezone="Africa/Lagos"),
        id="system_sweep",
        replace_existing=True,
        misfire_grace_time=300,
    )

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

    # Invoice reminders: every day at 9am Lagos time
    scheduler.add_job(
        _invoice_reminder_run,
        CronTrigger(hour=9, minute=0, timezone="Africa/Lagos"),
        id="invoice_reminder_run",
        replace_existing=True,
        misfire_grace_time=300,
    )

    return scheduler
