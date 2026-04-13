"""
Daily system sweep — checks all integrations, pipeline health, and error counts.
Runs at 7am Lagos time. Also callable via POST /api/v1/system/sweep.
Sends a WhatsApp/Slack alert to the owner summarising status.
"""
import httpx
import structlog
from datetime import datetime, timezone, timedelta
from config import get_settings
from database import get_db, get_contacts, get_outreach_log

log = structlog.get_logger()

STATUS_OK   = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"


async def run_sweep() -> dict:
    """
    Run all health checks and return a structured report.
    Each check returns {"status": ok|warn|fail, "detail": str}.
    """
    settings = get_settings()
    checks: dict[str, dict] = {}

    # ── 1. MongoDB ──────────────────────────────────────────────────────────────
    try:
        get_db().command("ping")
        checks["mongodb"] = {"status": STATUS_OK, "detail": "Reachable"}
    except Exception as e:
        checks["mongodb"] = {"status": STATUS_FAIL, "detail": str(e)}

    # ── 2. Google Maps ──────────────────────────────────────────────────────────
    try:
        if not settings.google_maps_api_key:
            checks["google_maps"] = {"status": STATUS_WARN, "detail": "Key not set"}
        else:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    "https://maps.googleapis.com/maps/api/place/textsearch/json",
                    params={"query": "restaurant Lagos", "key": settings.google_maps_api_key},
                )
                maps_status = r.json().get("status", "")
                if maps_status in ("OK", "ZERO_RESULTS"):
                    checks["google_maps"] = {"status": STATUS_OK, "detail": maps_status}
                else:
                    checks["google_maps"] = {"status": STATUS_FAIL, "detail": maps_status}
    except Exception as e:
        checks["google_maps"] = {"status": STATUS_FAIL, "detail": str(e)}

    # ── 3. Apollo ───────────────────────────────────────────────────────────────
    try:
        if not settings.apollo_api_key:
            checks["apollo"] = {"status": STATUS_WARN, "detail": "Key not set"}
        else:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.post(
                    "https://api.apollo.io/v1/mixed_companies/search",
                    json={"q_organization_name": "test", "page": 1, "per_page": 1},
                    headers={"x-api-key": settings.apollo_api_key, "Content-Type": "application/json"},
                )
                if r.status_code in (200, 422, 403):
                    checks["apollo"] = {"status": STATUS_OK, "detail": f"HTTP {r.status_code}"}
                else:
                    checks["apollo"] = {"status": STATUS_FAIL, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        checks["apollo"] = {"status": STATUS_FAIL, "detail": str(e)}

    # ── 4. Apify (social discovery) ─────────────────────────────────────────────
    try:
        if not settings.apify_api_token:
            checks["apify"] = {"status": STATUS_WARN, "detail": "Token not set"}
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://api.apify.com/v2/users/me",
                    params={"token": settings.apify_api_token},
                )
                if r.status_code == 200:
                    checks["apify"] = {"status": STATUS_OK, "detail": "Token valid"}
                else:
                    checks["apify"] = {"status": STATUS_FAIL, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        checks["apify"] = {"status": STATUS_FAIL, "detail": str(e)}

    # ── 5. Meta WhatsApp ────────────────────────────────────────────────────────
    if settings.meta_phone_number_id and settings.meta_access_token:
        checks["meta_whatsapp"] = {"status": STATUS_OK, "detail": "Credentials present"}
    else:
        checks["meta_whatsapp"] = {"status": STATUS_WARN, "detail": "META_PHONE_NUMBER_ID or META_ACCESS_TOKEN not set"}

    # ── 6. Claude / Anthropic ───────────────────────────────────────────────────
    if settings.anthropic_api_key and not settings.anthropic_api_key.startswith("sk-ant-..."):
        checks["claude"] = {"status": STATUS_OK, "detail": "Key present"}
    else:
        checks["claude"] = {"status": STATUS_FAIL, "detail": "Key missing or placeholder"}

    # ── 7. Pipeline health ──────────────────────────────────────────────────────
    try:
        contacts = get_contacts()
        total = contacts.count_documents({})
        contacted = contacts.count_documents({"status": "contacted"})
        errors_24h = _count_recent_errors()
        hitl_backlog = _count_hitl_backlog()

        pipeline_status = STATUS_OK
        pipeline_details = []

        if errors_24h > 10:
            pipeline_status = STATUS_FAIL
            pipeline_details.append(f"{errors_24h} errors in last 24h")
        elif errors_24h > 3:
            pipeline_status = STATUS_WARN
            pipeline_details.append(f"{errors_24h} errors in last 24h")

        if hitl_backlog > 20:
            pipeline_status = STATUS_WARN
            pipeline_details.append(f"{hitl_backlog} messages pending HITL approval")

        checks["pipeline"] = {
            "status": pipeline_status,
            "detail": ", ".join(pipeline_details) if pipeline_details else "Healthy",
            "total_contacts": total,
            "contacted": contacted,
            "errors_24h": errors_24h,
            "hitl_backlog": hitl_backlog,
        }
    except Exception as e:
        checks["pipeline"] = {"status": STATUS_FAIL, "detail": str(e)}

    # ── 8. Daily send quota ─────────────────────────────────────────────────────
    try:
        from tools.memory import get_daily_send_count
        sent_today = get_daily_send_count()
        limit = settings.daily_send_limit
        pct = (sent_today / limit * 100) if limit else 0
        quota_status = STATUS_WARN if pct >= 90 else STATUS_OK
        checks["daily_quota"] = {
            "status": quota_status,
            "detail": f"{sent_today}/{limit} sent ({pct:.0f}%)",
            "sent": sent_today,
            "limit": limit,
        }
    except Exception as e:
        checks["daily_quota"] = {"status": STATUS_WARN, "detail": str(e)}

    # ── Summary ─────────────────────────────────────────────────────────────────
    statuses = [c["status"] for c in checks.values()]
    if STATUS_FAIL in statuses:
        overall = STATUS_FAIL
    elif STATUS_WARN in statuses:
        overall = STATUS_WARN
    else:
        overall = STATUS_OK

    failed  = [k for k, v in checks.items() if v["status"] == STATUS_FAIL]
    warned  = [k for k, v in checks.items() if v["status"] == STATUS_WARN]

    report = {
        "overall": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "failed": failed,
        "warned": warned,
        "checks": checks,
    }

    log.info("system_sweep_complete", overall=overall, failed=failed, warned=warned)
    return report


def _count_recent_errors() -> int:
    """Count outreach log entries with errors in the last 24 hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        return get_outreach_log().count_documents({
            "sent_at": {"$gte": since},
            "error": {"$exists": True},
        })
    except Exception:
        return 0


def _count_hitl_backlog() -> int:
    """Count messages pending human approval."""
    try:
        return get_db()["hitl_queue"].count_documents({"status": "pending"})
    except Exception:
        return 0


def _format_sweep_message(report: dict) -> str:
    """Format sweep report into a WhatsApp-friendly message."""
    icon = {"ok": "✅", "warn": "⚠️", "fail": "❌"}.get(report["overall"], "?")
    lines = [f"{icon} *ReachNG Daily Sweep*"]

    if report["failed"]:
        lines.append(f"\n*FAILED:* {', '.join(report['failed'])}")
    if report["warned"]:
        lines.append(f"*WARNINGS:* {', '.join(report['warned'])}")

    lines.append("\n*Checks:*")
    for name, check in report["checks"].items():
        s = {"ok": "✅", "warn": "⚠️", "fail": "❌"}.get(check["status"], "?")
        lines.append(f"{s} {name.replace('_', ' ').title()}: {check['detail']}")

    if "pipeline" in report["checks"]:
        p = report["checks"]["pipeline"]
        lines.append(f"\n*Pipeline:* {p.get('total_contacts', 0)} contacts | {p.get('contacted', 0)} contacted | {p.get('errors_24h', 0)} errors (24h)")

    return "\n".join(lines)


async def run_and_notify() -> dict:
    """Run sweep and send WhatsApp/Slack alert to owner if anything is broken."""
    report = await run_sweep()

    # Only notify if there's something to flag (warn or fail)
    if report["overall"] != STATUS_OK:
        from tools.notifier import notify_owner
        message = _format_sweep_message(report)
        await notify_owner(
            contact_name="System Sweep",
            vertical="system",
            channel="system",
            reply_text=message,
            intent="unknown",
            urgency="high" if report["overall"] == STATUS_FAIL else "medium",
            summary=message,
        )
    return report
