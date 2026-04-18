"""
APScheduler — automated recurring jobs for the ReachNG suites.

Loops scheduled:
  07:00  System health sweep
  08:00  Morning WhatsApp brief to owner
  08–23  Unipile reply polling (every 30 min)
  09:00  Invoice chaser — queue overdue-invoice WhatsApp drafts to HITL
  09:30  Debt collector — queue escalating debt-recovery drafts to HITL
  10:00  Fleet dispatcher — alert on incidents pending >4h
  10:30  Market OS — run buy/sell alert checks and notify owner

Legacy SDR outreach loops (nightly discovery + 48h follow-up) have been
retired. The product is the 12 revenue suites now; HITL queues per suite.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from tools.reply_router import process_replies
from tools.brief import compile_morning_brief
from tools.notifier import notify_owner
import structlog

log = structlog.get_logger()

scheduler = AsyncIOScheduler(timezone="Africa/Lagos")


async def _reply_poll():
    """Poll Unipile for inbound replies and route them to contacts."""
    log.info("reply_poll_start")
    try:
        result = await process_replies()
        log.info("reply_poll_done", **result)
    except Exception as e:
        log.error("reply_poll_failed", error=str(e))


async def _invoice_reminder_run():
    """Daily invoice collection — queues WhatsApp reminders for overdue invoices into HITL."""
    from tools.invoices import get_due_reminders, REMINDER_SEQUENCE
    from agent import generate_invoice_reminder
    from tools.hitl import queue_draft
    from bson import ObjectId
    from datetime import datetime, timezone

    log.info("invoice_reminder_run_start")
    reminders = get_due_reminders()
    queued = 0
    errors = 0

    for invoice in reminders:
        stages = [s["stage"] for s in REMINDER_SEQUENCE]
        current_status = invoice.get("status", "pending")

        if current_status == "pending":
            next_stage = REMINDER_SEQUENCE[0]
        else:
            try:
                idx = stages.index(current_status)
                if idx + 1 >= len(REMINDER_SEQUENCE):
                    continue
                next_stage = REMINDER_SEQUENCE[idx + 1]
            except ValueError:
                continue

        # Skip invoices that are missing the debtor link — they shouldn't exist,
        # but an orphan ObjectId fallback pollutes the queue. Log and move on.
        if not invoice.get("debtor_id"):
            log.warning("invoice_reminder_orphan", invoice_id=invoice.get("id"))
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
            queue_draft(
                contact_id=str(invoice["debtor_id"]),
                contact_name=invoice["debtor_name"],
                vertical="invoice_chaser",
                channel="whatsapp",
                message=message,
                phone=invoice.get("debtor_phone"),
                source="invoice",
            )
            queued += 1
        except Exception as e:
            log.error("invoice_reminder_failed", invoice_id=invoice.get("id"), error=str(e))
            errors += 1

    log.info("invoice_reminder_run_done", queued=queued, errors=errors)


async def _debt_collector_run():
    """Daily debt recovery — queue escalating WhatsApp drafts per overdue case."""
    from services.debt_collector.store import get_due_cases, record_reminder
    from services.debt_collector.engine import generate_recovery_message
    from tools.hitl import queue_draft
    from bson import ObjectId
    from datetime import datetime, timezone

    log.info("debt_collector_run_start")
    cases = get_due_cases()
    queued = 0
    errors = 0

    for case in cases:
        try:
            due_date = case.get("original_due_date")
            now = datetime.now(timezone.utc)
            if due_date:
                if due_date.tzinfo is None:
                    due_date = due_date.replace(tzinfo=timezone.utc)
                days_overdue = max(0, (now - due_date).days)
            else:
                days_overdue = 0

            result = generate_recovery_message(
                creditor_name=case["client_name"],
                debtor_name=case["debtor_name"],
                debtor_business=case.get("debtor_business", ""),
                amount_ngn=case["amount_ngn"],
                description=case.get("description", ""),
                original_due_date=str(due_date.date()) if due_date else "",
                days_overdue=days_overdue,
                relationship_context=case.get("relationship_context", ""),
                prior_responses=case.get("prior_responses", ""),
            )

            queue_draft(
                contact_id=str(ObjectId()),
                contact_name=case["debtor_name"],
                vertical="debt_collector",
                channel="whatsapp",
                message=result["message"],
                phone=case.get("debtor_phone"),
                source="debt_case",
            )
            record_reminder(case["_id"], result["stage"], result["message"])
            queued += 1
        except Exception as e:
            log.error("debt_collector_failed", case_id=case.get("_id"), error=str(e))
            errors += 1

    log.info("debt_collector_run_done", queued=queued, errors=errors)


async def _fleet_escalation_check():
    """Notify owner when a fleet incident has been pending >4h without action."""
    from services.fleet_dispatcher.store import list_incidents
    from datetime import datetime, timezone, timedelta

    log.info("fleet_escalation_check_start")
    try:
        pending = list_incidents(status="pending", limit=50)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
        stale = []
        for inc in pending:
            created = inc.get("created_at")
            if not created:
                continue
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except Exception:
                    continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                stale.append(inc)

        if stale:
            lines = [f"*{len(stale)} fleet incident(s) need your call:*"]
            for s in stale[:5]:
                lines.append(f"• {s.get('truck_plate','?')} — {s.get('driver_name','?')} — ₦{s.get('amount_requested_ngn',0):,}")
            await notify_owner("\n".join(lines))

        log.info("fleet_escalation_check_done", stale=len(stale))
    except Exception as e:
        log.error("fleet_escalation_check_failed", error=str(e))


async def _rent_period_open():
    """On the 1st of every month, open rent charges for the current month."""
    from services.estate.rent_roll import open_charges_for_period
    from datetime import datetime
    period = datetime.now().strftime("%Y-%m")
    log.info("rent_period_open_start", period=period)
    try:
        opened = open_charges_for_period(period)
        log.info("rent_period_open_done", period=period, opened=opened)
    except Exception as e:
        log.error("rent_period_open_failed", error=str(e))


async def _rent_chase_run():
    """Daily rent chase — queue overdue-rent WhatsApp drafts to HITL."""
    import httpx
    from config import get_settings

    log.info("rent_chase_run_start")
    try:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=60) as client:
            auth = (settings.dashboard_user, settings.dashboard_pass) if settings.dashboard_user else None
            r = await client.post(
                f"http://127.0.0.1:{settings.app_port}/estate/rent/chase/run",
                auth=auth,
            )
            result = r.json() if r.status_code == 200 else {"error": r.status_code}
        log.info("rent_chase_run_done", **result)
    except Exception as e:
        log.error("rent_chase_run_failed", error=str(e))


async def _probation_alerts():
    """Daily check — WhatsApp the manager 7 days before a staff probation confirmation."""
    from database.mongo import get_db
    from datetime import date, timedelta
    from tools.outreach import send_whatsapp

    log.info("probation_alerts_start")
    try:
        today = date.today()
        target = (today + timedelta(days=7)).isoformat()
        rows = list(get_db()["hr_probation"].find({"status": "active", "confirmation_date": target}))
        for r in rows:
            phone = r.get("manager_phone")
            if not phone:
                continue
            msg = (f"Probation alert: {r['staff_name']} ({r.get('role','')}) is due for "
                   f"confirmation on {target}. Review performance and confirm or extend.")
            try:
                await send_whatsapp(phone=phone, message=msg)
            except Exception as e:
                log.warning("probation_alert_send_failed", staff=r.get("staff_name"), error=str(e))
        log.info("probation_alerts_done", fired=len(rows))
    except Exception as e:
        log.error("probation_alerts_failed", error=str(e))


async def _market_alerts_run():
    """Check commodity price thresholds and notify owner of triggered alerts."""
    from services.market_os.engine import check_buy_alerts

    log.info("market_alerts_run_start")
    try:
        triggered = check_buy_alerts()
        if triggered:
            lines = [f"*{len(triggered)} MarketOS alert(s) firing:*"]
            for t in triggered[:8]:
                lines.append(f"• {t.get('commodity','?')} @ {t.get('market','?')} — ₦{t.get('price_ngn',0):,}/{t.get('unit','kg')}")
            await notify_owner("\n".join(lines))
        log.info("market_alerts_run_done", triggered=len(triggered))
    except Exception as e:
        log.error("market_alerts_run_failed", error=str(e))


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

    scheduler.add_job(
        _system_sweep,
        CronTrigger(hour=7, minute=0, timezone="Africa/Lagos"),
        id="system_sweep", replace_existing=True, misfire_grace_time=300,
    )

    scheduler.add_job(
        _morning_brief,
        CronTrigger(hour=8, minute=0, timezone="Africa/Lagos"),
        id="morning_brief", replace_existing=True, misfire_grace_time=300,
    )

    scheduler.add_job(
        _reply_poll,
        CronTrigger(hour="8-23", minute="*/30", timezone="Africa/Lagos"),
        id="reply_poll", replace_existing=True, misfire_grace_time=120,
    )

    scheduler.add_job(
        _invoice_reminder_run,
        CronTrigger(hour=9, minute=0, timezone="Africa/Lagos"),
        id="invoice_reminder_run", replace_existing=True, misfire_grace_time=300,
    )

    scheduler.add_job(
        _debt_collector_run,
        CronTrigger(hour=9, minute=30, timezone="Africa/Lagos"),
        id="debt_collector_run", replace_existing=True, misfire_grace_time=300,
    )

    scheduler.add_job(
        _fleet_escalation_check,
        CronTrigger(hour="8-20", minute=0, timezone="Africa/Lagos"),
        id="fleet_escalation_check", replace_existing=True, misfire_grace_time=120,
    )

    scheduler.add_job(
        _market_alerts_run,
        CronTrigger(hour="9,13,17", minute=0, timezone="Africa/Lagos"),
        id="market_alerts_run", replace_existing=True, misfire_grace_time=180,
    )

    # Rent roll: open monthly charges on the 1st at 00:30
    scheduler.add_job(
        _rent_period_open,
        CronTrigger(day=1, hour=0, minute=30, timezone="Africa/Lagos"),
        id="rent_period_open", replace_existing=True, misfire_grace_time=600,
    )

    # Rent chase: daily at 09:45 — generate drafts → HITL
    scheduler.add_job(
        _rent_chase_run,
        CronTrigger(hour=9, minute=45, timezone="Africa/Lagos"),
        id="rent_chase_run", replace_existing=True, misfire_grace_time=300,
    )

    # Probation alerts: daily at 08:30 — WhatsApp manager 7 days before confirmation
    scheduler.add_job(
        _probation_alerts,
        CronTrigger(hour=8, minute=30, timezone="Africa/Lagos"),
        id="probation_alerts", replace_existing=True, misfire_grace_time=300,
    )

    return scheduler
