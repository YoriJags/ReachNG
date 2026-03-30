"""
Morning Brief compiler — aggregates overnight activity into a single WhatsApp message.
Sent at 8am Lagos time every day via the scheduler.
"""
from datetime import datetime, timezone, timedelta
from tools.roi import get_roi_summary
from tools.social import get_social_signals
from database import get_db
import structlog

log = structlog.get_logger()


def _overnight_window() -> tuple[datetime, datetime]:
    """Returns midnight-to-now window in UTC."""
    now   = datetime.now(timezone.utc)
    lagos_offset = timedelta(hours=1)
    today_lagos  = (now + lagos_offset).replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc = today_lagos - lagos_offset
    return midnight_utc, now


def _get_overnight_signals() -> dict:
    """Count social signals found since midnight."""
    since, _ = _overnight_window()
    col = get_db()["social_signals"]
    total = col.count_documents({"found_at": {"$gte": since}})
    by_platform = list(col.aggregate([
        {"$match": {"found_at": {"$gte": since}}},
        {"$group": {"_id": "$platform", "count": {"$sum": 1}}},
    ]))
    breakdown = {r["_id"]: r["count"] for r in by_platform}
    return {"total": total, "breakdown": breakdown}


def _get_overnight_replies() -> dict:
    """Count replies and their intents since midnight."""
    since, _ = _overnight_window()
    col = get_db()["replies"]
    total = col.count_documents({"received_at": {"$gte": since}})
    by_intent = list(col.aggregate([
        {"$match": {"received_at": {"$gte": since}}},
        {"$group": {"_id": "$intent", "count": {"$sum": 1}}},
    ]))
    return {"total": total, "by_intent": {r["_id"]: r["count"] for r in by_intent}}


def _get_pending_approvals_count() -> int:
    from tools.hitl import get_approval_stats
    stats = get_approval_stats()
    return stats.get("pending", 0)


def _get_pipeline_snapshot() -> dict:
    """Per-vertical contacted/replied/converted counts."""
    col = get_db()["contacts"]
    rows = list(col.aggregate([
        {"$group": {
            "_id": "$vertical",
            "contacted": {"$sum": {"$cond": [{"$in": ["$status", ["contacted", "replied", "converted"]]}, 1, 0]}},
            "replied":   {"$sum": {"$cond": [{"$eq": ["$status", "replied"]}, 1, 0]}},
            "converted": {"$sum": {"$cond": [{"$eq": ["$status", "converted"]}, 1, 0]}},
        }}
    ]))
    return {r["_id"]: {"contacted": r["contacted"], "replied": r["replied"], "converted": r["converted"]}
            for r in rows if r["_id"]}


def _fmt_ngn(n: int) -> str:
    if n >= 1_000_000:
        return f"₦{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"₦{n / 1_000:.0f}k"
    return f"₦{n}"


def _intent_emoji(intent: str) -> str:
    return {"interested": "🔥", "not_now": "⏳", "opted_out": "🚫", "referral": "🤝", "question": "❓"}.get(intent, "💬")


def compile_morning_brief() -> str:
    """Build the full morning brief message string."""
    now_lagos = datetime.now(timezone.utc) + timedelta(hours=1)
    day_str   = now_lagos.strftime("%A, %d %b")

    signals   = _get_overnight_signals()
    replies   = _get_overnight_replies()
    approvals = _get_pending_approvals_count()
    roi       = get_roi_summary(days=30)
    pipeline  = _get_pipeline_snapshot()

    # ── Signals line ──
    sig_parts = []
    for plat, icon in [("instagram", "📸"), ("twitter", "🐦"), ("facebook", "📘")]:
        n = signals["breakdown"].get(plat, 0)
        if n:
            sig_parts.append(f"{n} {icon}")
    sig_line = f"{signals['total']} new signals ({', '.join(sig_parts)})" if sig_parts else f"{signals['total']} new signals"

    # ── Replies line ──
    reply_parts = []
    for intent, count in replies["by_intent"].items():
        reply_parts.append(f"{count} {_intent_emoji(intent)} {intent.replace('_', ' ')}")
    reply_line = ", ".join(reply_parts) if reply_parts else "none"

    # ── Pipeline lines ──
    VERTICAL_LABELS = {
        "real_estate": "🏠 Real Estate", "recruitment": "👥 Recruitment",
        "events": "🎉 Events", "fintech": "💳 Fintech",
        "legal": "⚖️ Legal", "logistics": "🚚 Logistics",
    }
    pipeline_lines = []
    for v, stats in pipeline.items():
        label = VERTICAL_LABELS.get(v, v.replace("_", " ").title())
        pipeline_lines.append(
            f"  {label}: {stats['contacted']} contacted | {stats['replied']} replied | {stats['converted']} converted"
        )

    # ── ROI line ──
    roi_line = roi.get("roi_label", "No sends yet this month")

    # ── Approval nudge ──
    approval_line = (
        f"⚠️ {approvals} draft{'s' if approvals != 1 else ''} waiting for your approval"
        if approvals else "✅ Approval queue is clear"
    )

    brief = f"""🌅 *ReachNG Morning Brief*
{day_str}

📬 *OVERNIGHT*
• {sig_line}
• Replies: {reply_line}
• {approval_line}

💰 *THIS MONTH*
• {roi_line}
• Sent: {roi.get('messages_sent', 0)} messages | AI cost: {_fmt_ngn(roi.get('api_cost_ngn', 0))}

⚡ *PIPELINE*
{chr(10).join(pipeline_lines) if pipeline_lines else "  No contacts yet — run a campaign to get started"}

🔔 Next campaign run tonight at 10pm
→ Open dashboard to approve drafts"""

    return brief.strip()
