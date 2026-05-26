"""
Outreach analytics — funnel + per-prospect drilldown for cold campaigns.

Joins three collections to produce the conversion funnel:
  outreach_log     — every email that left the building (sent, opened,
                     clicked, bounced; populated by Resend webhook)
  outreach_links   — the /hi/{slug} clicks (independent counter,
                     attributable to a recipient even if they cleared
                     the cookie or shared the link)
  waitlist + pilot — downstream conversions (attributed back via slug)

Routes (Basic Auth):
  GET /api/v1/admin/outreach-analytics/funnel
    ?client_name=ReachNG+Self-Outreach&days=30
    Returns sent/delivered/opened/clicked/replied/joined-waitlist counts
    with percentages relative to the previous step.

  GET /api/v1/admin/outreach-analytics/timeline
    ?client_name=...&days=30
    Daily series: sent, delivered, opened, clicked, joined.

  GET /api/v1/admin/outreach-analytics/per-prospect
    ?client_name=...&limit=100
    One row per recipient with their full event chain — what was sent,
    when, whether they opened/clicked, whether they joined the waitlist.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from auth import require_auth
from database import get_db


router = APIRouter(
    prefix="/api/v1/admin/outreach-analytics",
    tags=["OutreachAnalytics"],
    dependencies=[Depends(require_auth)],
)


def _window_match(client_name: Optional[str], days: int) -> dict:
    q: dict = {
        "sent_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=max(1, min(365, days)))},
    }
    if client_name:
        q["client_name"] = client_name
    return q


@router.get("/funnel")
async def funnel(client_name: Optional[str] = None, days: int = 30,
                  channel: Optional[str] = "email"):
    """Returns the conversion funnel counts + rates."""
    db = get_db()
    match = _window_match(client_name, days)
    if channel:
        match["channel"] = channel

    log_col = db["outreach_log"]
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":           None,
            "sent":          {"$sum": 1},
            "delivered":     {"$sum": {"$cond": [{"$ifNull": ["$delivered_at", False]}, 1, 0]}},
            "opened":        {"$sum": {"$cond": [{"$ifNull": ["$opened_at",    False]}, 1, 0]}},
            "clicked":       {"$sum": {"$cond": [{"$ifNull": ["$clicked_at",   False]}, 1, 0]}},
            "bounced":       {"$sum": {"$cond": [{"$ifNull": ["$bounced_at",   False]}, 1, 0]}},
            "open_events":   {"$sum": {"$ifNull": ["$open_count",  0]}},
            "click_events":  {"$sum": {"$ifNull": ["$click_count", 0]}},
        }},
    ]
    agg = list(log_col.aggregate(pipeline))
    base = agg[0] if agg else {
        "sent": 0, "delivered": 0, "opened": 0, "clicked": 0,
        "bounced": 0, "open_events": 0, "click_events": 0,
    }

    # /hi/{slug} clicks — independent of the email pixel. Useful when the
    # recipient blocks images but does click the link.
    slug_clicks = 0
    try:
        slug_pipeline = [
            {"$match": {
                "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=days)},
                "variant":    "hi",
            }},
            {"$group": {"_id": None, "clicks": {"$sum": {"$ifNull": ["$clicks", 0]}}}},
        ]
        slug_agg = list(db["outreach_links"].aggregate(slug_pipeline))
        slug_clicks = (slug_agg[0]["clicks"] if slug_agg else 0)
    except Exception:
        pass

    # Waitlist joins attributed back to this client's outreach window.
    waitlist_joins = 0
    try:
        waitlist_q = {"created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=days)}}
        if client_name:
            waitlist_q["source"] = {"$in": ["outreach", "founder_cohort", client_name]}
        waitlist_joins = db["waitlist"].count_documents(waitlist_q)
    except Exception:
        pass

    def _pct(n, d):
        return round((n / d * 100), 1) if d else 0.0

    return {
        "client_name":    client_name,
        "channel":        channel,
        "window_days":    days,
        "sent":           base["sent"],
        "delivered":      base["delivered"],
        "opened":         base["opened"],
        "clicked":        base["clicked"],
        "bounced":        base["bounced"],
        "open_events":    base["open_events"],
        "click_events":   base["click_events"],
        "slug_clicks":    slug_clicks,
        "waitlist_joins": waitlist_joins,
        "rates": {
            "delivery_rate":   _pct(base["delivered"], base["sent"]),
            "open_rate":       _pct(base["opened"],    base["delivered"] or base["sent"]),
            "click_rate":      _pct(base["clicked"],   base["opened"]    or 1),
            "click_to_open":   _pct(base["click_events"], base["open_events"]),
            "bounce_rate":     _pct(base["bounced"],   base["sent"]),
            "conversion_rate": _pct(waitlist_joins,    base["sent"]),
        },
    }


@router.get("/timeline")
async def timeline(client_name: Optional[str] = None, days: int = 30,
                    channel: Optional[str] = "email"):
    """Daily series: sent / opened / clicked. For sparkline rendering."""
    db = get_db()
    match = _window_match(client_name, days)
    if channel:
        match["channel"] = channel

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "y": {"$year":  "$sent_at"},
                "m": {"$month": "$sent_at"},
                "d": {"$dayOfMonth": "$sent_at"},
            },
            "sent":    {"$sum": 1},
            "opened":  {"$sum": {"$cond": [{"$ifNull": ["$opened_at",  False]}, 1, 0]}},
            "clicked": {"$sum": {"$cond": [{"$ifNull": ["$clicked_at", False]}, 1, 0]}},
        }},
        {"$sort": {"_id.y": 1, "_id.m": 1, "_id.d": 1}},
    ]
    rows = list(db["outreach_log"].aggregate(pipeline))
    return {
        "client_name": client_name,
        "days": [
            {
                "date":    f"{r['_id']['y']:04d}-{r['_id']['m']:02d}-{r['_id']['d']:02d}",
                "sent":    r["sent"],
                "opened":  r["opened"],
                "clicked": r["clicked"],
            }
            for r in rows
        ],
    }


@router.get("/per-prospect")
async def per_prospect(client_name: Optional[str] = None,
                        days: int = 30, limit: int = 100):
    """One row per recipient with their event chain."""
    db = get_db()
    match = _window_match(client_name, days)
    match["channel"] = "email"
    rows = list(db["outreach_log"].find(
        match,
        {
            "to_email": 1, "subject": 1, "sent_at": 1, "delivered_at": 1,
            "opened_at": 1, "open_count": 1, "first_open_at": 1,
            "clicked_at": 1, "click_count": 1, "bounced_at": 1,
            "bounce_reason": 1, "outreach_slug": 1, "contact_id": 1,
            "client_name": 1,
        },
    ).sort("sent_at", -1).limit(min(limit, 500)))

    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else v

    out = []
    for r in rows:
        slug = r.get("outreach_slug")
        slug_clicks = 0
        if slug:
            sd = db["outreach_links"].find_one({"slug": slug}, {"clicks": 1})
            slug_clicks = (sd or {}).get("clicks", 0)
        out.append({
            "to_email":      r.get("to_email"),
            "subject":       r.get("subject"),
            "sent_at":       _iso(r.get("sent_at")),
            "delivered_at":  _iso(r.get("delivered_at")),
            "opened":        bool(r.get("opened_at")),
            "open_count":    r.get("open_count") or 0,
            "first_open_at": _iso(r.get("first_open_at")),
            "clicked":       bool(r.get("clicked_at")) or slug_clicks > 0,
            "click_count":   r.get("click_count") or 0,
            "slug_clicks":   slug_clicks,
            "bounced":       bool(r.get("bounced_at")),
            "bounce_reason": r.get("bounce_reason"),
            "outreach_slug": slug,
            "client_name":   r.get("client_name"),
        })
    return {"rows": out, "count": len(out)}
