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


def _generate_action_items(replies: dict, approvals: int, pipeline: dict) -> str:
    """Ask Claude Haiku for 3 concrete actions based on today's data."""
    try:
        import anthropic
        from config import get_settings
        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        interested = replies["by_intent"].get("interested", 0)
        total_replies = replies["total"]
        pipeline_summary = ", ".join(
            f"{v}: {s['contacted']} sent / {s['replied']} replied"
            for v, s in list(pipeline.items())[:3]
        ) or "No activity yet"

        prompt = (
            f"You are the AI advisor for ReachNG, a Nigerian B2B outreach platform. "
            f"Based on today's data, give exactly 3 short, specific action items the owner should do today.\n\n"
            f"Data:\n"
            f"- Overnight replies: {total_replies} total, {interested} marked Interested\n"
            f"- Drafts awaiting approval: {approvals}\n"
            f"- Pipeline: {pipeline_summary}\n\n"
            f"Format: numbered list, one line each, under 12 words per item. Be direct and specific."
        )

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        log.warning("brief_action_items_failed", error=str(e))
        return ""


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
        "agriculture": "🌾 Agriculture",
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

    # ── AI action items ──
    action_items = _generate_action_items(replies, approvals, pipeline)
    action_block = f"\n\n🎯 *TODAY'S 3 ACTIONS*\n{action_items}" if action_items else ""

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
{chr(10).join(pipeline_lines) if pipeline_lines else "  No contacts yet — run a campaign to get started"}{action_block}

🔔 Run outreach manually from the Campaigns tab when ready.
→ Open dashboard to review and approve drafts before they go out"""

    return brief.strip()
