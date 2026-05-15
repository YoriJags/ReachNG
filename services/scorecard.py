"""
Outcomes Scorecard — per-client KPIs computed from raw events.

What this measures
------------------
For one client over their tenure on ReachNG:
  • ngn_closed         — cash flowing through ReachNG-handled flows
                          (closer leads booked + invoices claimed_paid +
                           rent claimed_paid + school fees claimed_paid)
  • bookings_closed    — count of the above
  • drafts_generated   — total drafts queued (approval status doesn't matter)
  • drafts_approved    — approved or auto-sent
  • approval_rate      — approved / actioned (excl. pending)
  • hours_saved        — approved drafts × estimated manual typing time (2 min each)
  • median_response_s  — median time between inbound and first outbound for that thread
  • api_cost_estimate  — approved drafts × ~₦8 per draft (Haiku pricing rough)

Materialisation
---------------
Live mode: compute on every API call (cheap for most clients, all queries are
scoped by client_id and indexed). Nightly mode: stash the result in
`scorecard_snapshots` so the dashboard can chart trend lines.

Scope: every function REQUIRES client_id. Operator dashboard reads cohort-wide
aggregates from `cohort_stats` (a separate service in services/cohort_stats.py).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Constants ────────────────────────────────────────────────────────────────

# Estimated minutes a Lagos SME owner would have spent typing a single
# personalised WhatsApp reply manually. 2 minutes is conservative.
MINUTES_PER_MANUAL_REPLY = 2.0

# Rough Haiku 4.5 cost per draft in naira (input + output, conservative).
NGN_PER_DRAFT_API_COST = 8.0


# ─── Errors ───────────────────────────────────────────────────────────────────

class ScorecardScopeError(Exception):
    """Refuses scorecard ops without a client_id."""


# ─── Collection accessors ────────────────────────────────────────────────────

def _db():
    return get_db()


def get_snapshots_col():
    return _db()["scorecard_snapshots"]


def ensure_scorecard_indexes() -> None:
    snap = get_snapshots_col()
    snap.create_index([("client_id", ASCENDING), ("snapshot_at", DESCENDING)])


# ─── Data class ──────────────────────────────────────────────────────────────

@dataclass
class Scorecard:
    client_id:               str
    client_name:             Optional[str]
    period_start:            datetime
    period_end:              datetime
    onboarded_at:            Optional[datetime]
    days_active:             int

    # Cash
    ngn_closed:              float            = 0.0
    bookings_closed:         int              = 0
    ngn_pending:             float            = 0.0       # claimed but not yet verified

    # Activity
    inbound_messages:        int              = 0
    drafts_generated:        int              = 0
    drafts_approved:         int              = 0
    drafts_edited:           int              = 0
    drafts_skipped:          int              = 0
    approval_rate:           float            = 0.0

    # Time / cost savings
    hours_saved:             float            = 0.0
    api_cost_ngn:            float            = 0.0
    cost_per_booking_ngn:    Optional[float]  = None

    # Speed
    median_response_seconds: Optional[float]  = None

    # Component breakdown
    breakdown: dict           = field(default_factory=dict)


# ─── Scope guard ──────────────────────────────────────────────────────────────

def _require(client_id: Optional[str]) -> str:
    if not client_id or not str(client_id).strip():
        raise ScorecardScopeError("scorecard requires client_id")
    return str(client_id).strip()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_doc(client_id: str) -> Optional[dict]:
    try:
        return _db()["clients"].find_one({"_id": ObjectId(client_id)})
    except Exception:
        return None


# ─── Cash side ────────────────────────────────────────────────────────────────

def _closer_bookings(client_id: str, since: datetime) -> tuple[int, float]:
    """Closer leads that reached stage='booked' inside the period."""
    cursor = _db()["closer_leads"].find({
        "client_id":   client_id,
        "stage":       "booked",
        "updated_at":  {"$gte": since},
    }, {"booked_amount_ngn": 1, "deposit_amount_ngn": 1})
    count = 0
    total = 0.0
    for d in cursor:
        count += 1
        total += float(d.get("booked_amount_ngn") or d.get("deposit_amount_ngn") or 0)
    return count, total


def _invoices_claimed(client_name: Optional[str], since: datetime) -> tuple[int, float, float]:
    """(count_paid, total_paid, total_pending_claim) for invoices linked to this client."""
    if not client_name:
        return 0, 0.0, 0.0
    q = {"client_name": client_name, "claim_received_at": {"$gte": since}}
    n_paid = 0
    paid = 0.0
    pending = 0.0
    for inv in _db()["chased_invoices"].find(q, {"amount_ngn": 1, "claimed_paid": 1, "paid": 1}):
        amt = float(inv.get("amount_ngn") or 0)
        if inv.get("paid"):
            n_paid += 1
            paid += amt
        elif inv.get("claimed_paid"):
            pending += amt
    return n_paid, paid, pending


def _rent_claimed(client_id: str, since: datetime) -> tuple[int, float, float]:
    """Rent charges marked claimed_paid / paid via this client's tenants."""
    # Estate scopes by landlord_company == client name. We'll keep it simple here.
    client = _client_doc(client_id)
    cname = (client or {}).get("name")
    if not cname:
        return 0, 0.0, 0.0
    # Tenants belonging to this landlord
    tenants = list(_db()["estate_tenants"].find(
        {"landlord_company": {"$regex": f"^{cname}$", "$options": "i"}},
        {"_id": 1},
    ))
    if not tenants:
        return 0, 0.0, 0.0
    tenant_ids = [str(t["_id"]) for t in tenants]
    q = {"tenant_id": {"$in": tenant_ids}, "claim_received_at": {"$gte": since}}
    n_paid = 0
    paid = 0.0
    pending = 0.0
    for charge in _db()["estate_rent_ledger"].find(q, {"amount_ngn": 1, "status": 1, "claimed_paid": 1}):
        amt = float(charge.get("amount_ngn") or 0)
        if charge.get("status") == "paid":
            n_paid += 1; paid += amt
        elif charge.get("claimed_paid"):
            pending += amt
    return n_paid, paid, pending


def _school_fees_claimed(client_id: str, since: datetime) -> tuple[int, float, float]:
    """School fees claimed via this school's roster."""
    q = {"school_id": client_id, "claim_received_at": {"$gte": since}}
    n_paid = 0
    paid = 0.0
    pending = 0.0
    for s in _db()["sf_students"].find(q, {"amount_paid": 1, "fee_amount": 1, "paid": 1, "claimed_paid": 1}):
        amt = float(s.get("amount_paid") or s.get("fee_amount") or 0)
        if s.get("paid"):
            n_paid += 1; paid += amt
        elif s.get("claimed_paid"):
            pending += amt
    return n_paid, paid, pending


# ─── Activity / drafts ────────────────────────────────────────────────────────

def _draft_counts(client_name: Optional[str], since: datetime) -> dict:
    if not client_name:
        return {"generated": 0, "approved": 0, "edited": 0, "skipped": 0, "pending": 0}
    pipeline = [
        {"$match": {"client_name": client_name, "created_at": {"$gte": since}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    counts = {"generated": 0, "approved": 0, "edited": 0, "skipped": 0, "pending": 0,
              "auto_sent": 0}
    for row in _db()["pending_approvals"].aggregate(pipeline):
        key = (row["_id"] or "pending").lower()
        counts[key] = counts.get(key, 0) + row["n"]
        counts["generated"] += row["n"]
    return counts


# ─── Speed ────────────────────────────────────────────────────────────────────

def _median_response_seconds(client_id: str, since: datetime, sample: int = 200) -> Optional[float]:
    """Sample recent inbound→approval-latency pairs."""
    client = _client_doc(client_id)
    cname = (client or {}).get("name")
    if not cname:
        return None
    inbound_col = _db()["inbound_messages"]
    approvals = _db()["pending_approvals"]
    pairs: list[float] = []
    inbounds = inbound_col.find(
        {"received_at": {"$gte": since}},
        {"sender_phone": 1, "received_at": 1},
    ).sort("received_at", -1).limit(sample)
    for inb in inbounds:
        phone = inb.get("sender_phone")
        if not phone:
            continue
        appr = approvals.find_one(
            {"client_name": cname, "phone": phone,
             "status": {"$in": ["approved", "auto_sent"]},
             "actioned_at": {"$gte": inb["received_at"]}},
            sort=[("actioned_at", 1)],
            projection={"actioned_at": 1},
        )
        if appr and appr.get("actioned_at") and inb.get("received_at"):
            delta = (appr["actioned_at"] - inb["received_at"]).total_seconds()
            if 0 < delta < 7 * 24 * 3600:   # cap at a week to drop outliers
                pairs.append(delta)
    if not pairs:
        return None
    return float(statistics.median(pairs))


# ─── Public: compute ──────────────────────────────────────────────────────────

def compute_scorecard(
    client_id: str,
    period_days: int = 30,
) -> Scorecard:
    """Compute KPIs for the last `period_days`. Default 30 days."""
    cid = _require(client_id)
    client = _client_doc(cid)
    if not client:
        raise ValueError(f"client not found: {cid}")

    now = datetime.now(timezone.utc)
    onboarded = client.get("onboarded_at")
    if isinstance(onboarded, datetime) and onboarded.tzinfo is None:
        onboarded = onboarded.replace(tzinfo=timezone.utc)

    period_start = now - timedelta(days=period_days)
    # If the client started after period_start, anchor to onboarding so we don't
    # show "days_active = 30" for a 5-day-old client.
    if onboarded and onboarded > period_start:
        period_start = onboarded
    days_active = max(1, int((now - period_start).total_seconds() // 86400))

    # Cash side
    n_closer, ngn_closer = _closer_bookings(cid, period_start)
    n_inv, ngn_inv, ngn_inv_pending = _invoices_claimed(client.get("name"), period_start)
    n_rent, ngn_rent, ngn_rent_pending = _rent_claimed(cid, period_start)
    n_fees, ngn_fees, ngn_fees_pending = _school_fees_claimed(cid, period_start)

    bookings = n_closer + n_inv + n_rent + n_fees
    ngn_closed = ngn_closer + ngn_inv + ngn_rent + ngn_fees
    ngn_pending = ngn_inv_pending + ngn_rent_pending + ngn_fees_pending

    # Activity
    counts = _draft_counts(client.get("name"), period_start)
    drafts_generated = counts["generated"]
    drafts_approved = counts.get("approved", 0) + counts.get("auto_sent", 0)
    drafts_edited = counts.get("edited", 0)
    drafts_skipped = counts.get("skipped", 0)
    actioned = drafts_approved + drafts_edited + drafts_skipped
    approval_rate = (drafts_approved / actioned) if actioned else 0.0

    # Inbound count (any inbound where matched client = this client)
    cname = client.get("name")
    inbound_n = _db()["inbound_messages"].count_documents({"received_at": {"$gte": period_start}}) if cname else 0
    # Best-effort: there's no direct client foreign key on inbound_messages today, so this
    # over-counts marginally for multi-client setups. For single-client deployments it's accurate.

    # Speed
    median_resp = _median_response_seconds(cid, period_start)

    # Cost
    hours_saved = (drafts_approved * MINUTES_PER_MANUAL_REPLY) / 60.0
    api_cost = drafts_approved * NGN_PER_DRAFT_API_COST
    cost_per_booking = round(api_cost / bookings, 2) if bookings else None

    return Scorecard(
        client_id=cid,
        client_name=client.get("name"),
        period_start=period_start,
        period_end=now,
        onboarded_at=onboarded,
        days_active=days_active,
        ngn_closed=round(ngn_closed, 2),
        bookings_closed=bookings,
        ngn_pending=round(ngn_pending, 2),
        inbound_messages=inbound_n,
        drafts_generated=drafts_generated,
        drafts_approved=drafts_approved,
        drafts_edited=drafts_edited,
        drafts_skipped=drafts_skipped,
        approval_rate=round(approval_rate, 4),
        hours_saved=round(hours_saved, 1),
        api_cost_ngn=round(api_cost, 2),
        cost_per_booking_ngn=cost_per_booking,
        median_response_seconds=median_resp,
        breakdown={
            "closer":      {"count": n_closer,   "ngn": round(ngn_closer, 2)},
            "invoices":    {"count": n_inv,      "ngn": round(ngn_inv, 2),  "pending_ngn": round(ngn_inv_pending, 2)},
            "rent":        {"count": n_rent,     "ngn": round(ngn_rent, 2), "pending_ngn": round(ngn_rent_pending, 2)},
            "school_fees": {"count": n_fees,     "ngn": round(ngn_fees, 2), "pending_ngn": round(ngn_fees_pending, 2)},
        },
    )


# ─── Public: snapshot persistence ─────────────────────────────────────────────

def snapshot_scorecard(client_id: str, period_days: int = 30) -> dict:
    """Compute + persist. Returns the stored doc."""
    sc = compute_scorecard(client_id, period_days=period_days)
    doc = asdict(sc)
    doc["snapshot_at"] = datetime.now(timezone.utc)
    doc["period_days"] = period_days
    get_snapshots_col().insert_one(doc)
    return doc


def snapshot_all_clients(period_days: int = 30) -> int:
    """Materialise scorecards for every active client. Returns count snapshotted."""
    n = 0
    for c in _db()["clients"].find({"active": True}, {"_id": 1}):
        try:
            snapshot_scorecard(str(c["_id"]), period_days=period_days)
            n += 1
        except Exception as e:
            log.warning("scorecard_snapshot_failed", client_id=str(c["_id"]), error=str(e))
    log.info("scorecard_snapshot_all_done", count=n, period_days=period_days)
    return n


# ─── Pretty-print helpers ─────────────────────────────────────────────────────

def format_ngn(amount: float) -> str:
    if amount is None:
        return "—"
    if amount >= 1_000_000:
        return f"₦{amount/1_000_000:.1f}M"
    if amount >= 1_000:
        return f"₦{amount/1_000:.0f}K"
    return f"₦{amount:,.0f}"


def format_response_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}min"
    return f"{seconds/3600:.1f}hr"
