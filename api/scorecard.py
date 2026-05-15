"""
Outcomes Scorecard API — admin + portal endpoints.

Admin (Basic Auth):
  GET  /api/v1/scorecard/{client_id}
  GET  /api/v1/scorecard/{client_id}/snapshots
  POST /api/v1/scorecard/{client_id}/refresh
  GET  /api/v1/quality/{client_id}
  GET  /api/v1/quality/alerts

Portal (token):
  GET  /portal/{token}/scorecard
  GET  /portal/{token}/scorecard.html      → branded PDF-ready page
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import require_auth as _admin_auth
from database import get_db
from services.scorecard import (
    compute_scorecard, snapshot_scorecard, get_snapshots_col,
    format_ngn, format_response_time, ScorecardScopeError,
)
from services.quality_metrics import (
    compute_quality, get_alerts_col, QualityScopeError,
)

router = APIRouter(tags=["Scorecard"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_from_token(token: str) -> dict:
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "portal not found")
    return client


# ─── Admin: scorecard ─────────────────────────────────────────────────────────

@router.get("/api/v1/scorecard/{client_id}")
async def admin_scorecard(client_id: str, period_days: int = 30,
                            _: str = Depends(_admin_auth)):
    try:
        sc = compute_scorecard(client_id, period_days=period_days)
    except ScorecardScopeError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return asdict(sc)


@router.get("/api/v1/scorecard/{client_id}/snapshots")
async def admin_snapshots(client_id: str, limit: int = 30,
                           _: str = Depends(_admin_auth)):
    rows = list(
        get_snapshots_col()
        .find({"client_id": client_id})
        .sort("snapshot_at", -1)
        .limit(min(200, limit))
    )
    for r in rows:
        r["_id"] = str(r["_id"])
    return {"snapshots": rows}


@router.post("/api/v1/scorecard/{client_id}/refresh")
async def admin_refresh(client_id: str, period_days: int = 30,
                         _: str = Depends(_admin_auth)):
    try:
        doc = snapshot_scorecard(client_id, period_days=period_days)
    except ScorecardScopeError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    doc.pop("_id", None)
    return doc


# ─── Admin: quality ───────────────────────────────────────────────────────────

@router.get("/api/v1/quality/{client_id}")
async def admin_quality(client_id: str, window_days: int = 14,
                         _: str = Depends(_admin_auth)):
    try:
        q = compute_quality(client_id, window_days=window_days)
    except QualityScopeError as e:
        raise HTTPException(400, str(e))
    return asdict(q)


@router.get("/api/v1/quality/alerts")
async def admin_quality_alerts(limit: int = 50, _: str = Depends(_admin_auth)):
    rows = list(get_alerts_col().find().sort("ts", -1).limit(min(200, limit)))
    for r in rows:
        r["_id"] = str(r["_id"])
    return {"alerts": rows}


# ─── Portal: scorecard ────────────────────────────────────────────────────────

@router.get("/portal/{token}/scorecard")
async def portal_scorecard(token: str, period_days: int = 30):
    client = _client_from_token(token)
    sc = compute_scorecard(str(client["_id"]), period_days=period_days)
    return asdict(sc)


@router.get("/portal/{token}/scorecard.html", response_class=HTMLResponse)
async def portal_scorecard_html(token: str, period_days: int = 30):
    """Branded, print-friendly scorecard. Customers can save as PDF via browser."""
    client = _client_from_token(token)
    sc = compute_scorecard(str(client["_id"]), period_days=period_days)
    return HTMLResponse(_render_scorecard_html(client, sc))


# ─── Branded HTML render ──────────────────────────────────────────────────────

def _render_scorecard_html(client: dict, sc) -> str:
    period_start = sc.period_start.strftime("%d %b %Y") if sc.period_start else ""
    period_end   = sc.period_end.strftime("%d %b %Y") if sc.period_end else ""
    approval_pct = f"{sc.approval_rate * 100:.0f}%" if sc.approval_rate else "—"
    cost_per_booking = format_ngn(sc.cost_per_booking_ngn) if sc.cost_per_booking_ngn else "—"
    response_txt = format_response_time(sc.median_response_seconds)
    breakdown_rows = ""
    for kind, b in sc.breakdown.items():
        if not b.get("count") and not b.get("ngn"):
            continue
        label = kind.replace("_", " ").title()
        breakdown_rows += (
            f"<tr><td>{label}</td><td>{b['count']}</td><td>{format_ngn(b['ngn'])}</td>"
            f"<td>{format_ngn(b.get('pending_ngn', 0))}</td></tr>"
        )
    if not breakdown_rows:
        breakdown_rows = "<tr><td colspan='4' style='color:#777;text-align:center;'>No bookings or recoveries yet — keep approving drafts to start counting wins.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>{client.get('name')} — ReachNG Scorecard</title>
<style>
  body {{ background:#0a0a0a;color:#e8e8e8;font-family:-apple-system,system-ui,sans-serif;margin:0;padding:40px;line-height:1.5; }}
  .wrap {{ max-width:880px;margin:0 auto; }}
  h1 {{ color:#fff;font-size:32px;margin:0 0 4px;letter-spacing:-0.5px; }}
  .sub {{ color:#9aa0a8;font-size:14px;margin:0 0 32px; }}
  .grid {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:28px; }}
  .kpi {{ background:#141414;border:1px solid #1f2530;border-radius:10px;padding:18px; }}
  .kpi .label {{ font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#6a7280;font-weight:700;margin-bottom:8px; }}
  .kpi .value {{ font-size:26px;color:#fff;font-weight:700;letter-spacing:-0.5px; }}
  .kpi .sub   {{ font-size:11px;color:#6a7280;margin-top:6px; }}
  .accent .value {{ color:#ff5500; }}
  .good .value   {{ color:#5dd28a; }}
  table {{ width:100%;border-collapse:collapse;background:#141414;border:1px solid #1f2530;border-radius:10px;overflow:hidden; }}
  th, td {{ text-align:left;padding:12px 16px;font-size:13px;border-bottom:1px solid #1f2530; }}
  th {{ background:#181818;color:#6a7280;text-transform:uppercase;font-size:11px;letter-spacing:0.08em;font-weight:700; }}
  td {{ color:#e8e8e8; }}
  tr:last-child td {{ border-bottom:none; }}
  .footer {{ margin-top:32px;text-align:center;color:#6a7280;font-size:12px; }}
  @media print {{
    body {{ background:#fff;color:#111; }}
    .kpi, table {{ background:#fff;border-color:#ddd;color:#111; }}
    th {{ background:#f5f5f5;color:#444; }}
    .kpi .label {{ color:#666; }}
    .kpi .value {{ color:#111; }}
    .accent .value {{ color:#ff5500; }}
  }}
</style></head><body><div class="wrap">

  <h1>{client.get('name')} — Outcomes Scorecard</h1>
  <p class="sub">ReachNG · {period_start} → {period_end} · {sc.days_active} days active</p>

  <div class="grid">
    <div class="kpi accent">
      <div class="label">₦ Closed</div>
      <div class="value">{format_ngn(sc.ngn_closed)}</div>
      <div class="sub">{sc.bookings_closed} booking{('s' if sc.bookings_closed != 1 else '')}</div>
    </div>
    <div class="kpi">
      <div class="label">Pending (claimed)</div>
      <div class="value" style="color:#ffb84d;">{format_ngn(sc.ngn_pending)}</div>
      <div class="sub">awaiting verification</div>
    </div>
    <div class="kpi good">
      <div class="label">Hours Saved</div>
      <div class="value">{sc.hours_saved:.1f}h</div>
      <div class="sub">{sc.drafts_approved} drafts approved × 2 min</div>
    </div>
    <div class="kpi">
      <div class="label">Median Response</div>
      <div class="value">{response_txt}</div>
      <div class="sub">inbound → reply</div>
    </div>
    <div class="kpi">
      <div class="label">Approval Rate</div>
      <div class="value">{approval_pct}</div>
      <div class="sub">{sc.drafts_approved} approved · {sc.drafts_edited} edited · {sc.drafts_skipped} skipped</div>
    </div>
    <div class="kpi">
      <div class="label">API Cost / Booking</div>
      <div class="value">{cost_per_booking}</div>
      <div class="sub">avg ₦ per closed deal</div>
    </div>
  </div>

  <h3 style="color:#fff;font-size:16px;margin:24px 0 12px;">Where the wins came from</h3>
  <table>
    <thead><tr><th>Source</th><th>Count</th><th>₦ Closed</th><th>₦ Pending</th></tr></thead>
    <tbody>{breakdown_rows}</tbody>
  </table>

  <p class="footer">
    Generated {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')} · ReachNG ·
    <a href="https://www.reachng.ng" style="color:#ff5500;text-decoration:none;">www.reachng.ng</a>
  </p>

</div></body></html>"""


# ─── Portal: quality (operator/owner view) ────────────────────────────────────

@router.get("/portal/{token}/quality")
async def portal_quality(token: str, window_days: int = 14):
    client = _client_from_token(token)
    q = compute_quality(str(client["_id"]), window_days=window_days)
    return asdict(q)


# ─── Public: cohort stats (for landing page) ──────────────────────────────────

@router.get("/api/v1/cohort-stats")
async def public_cohort_stats():
    """Anonymised platform-wide aggregates. PUBLIC — no auth. Read from cache."""
    from services.cohort_stats import latest_cohort_stats, format_summary_for_landing
    raw = latest_cohort_stats() or {}
    summary = format_summary_for_landing()
    # Strip internal datetime objects for safe JSON
    def _safe(v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v
    raw_safe = {k: _safe(v) for k, v in raw.items()}
    return {"summary": summary, "raw": raw_safe}


# ─── Milestone events ─────────────────────────────────────────────────────────

@router.get("/portal/{token}/milestones")
async def portal_milestones(token: str, limit: int = 20):
    client = _client_from_token(token)
    from services.milestone_engine import get_events_col
    rows = list(
        get_events_col()
        .find({"client_id": str(client["_id"])})
        .sort("fired_at", -1)
        .limit(min(50, limit))
    )
    for r in rows:
        r["_id"] = str(r["_id"])
        # Strip the heavy card_html — fetch it separately via card endpoint
        r.pop("card_html", None)
    return {"milestones": rows}


@router.get("/portal/{token}/milestones/{event_id}/card", response_class=HTMLResponse)
async def portal_milestone_card(token: str, event_id: str):
    client = _client_from_token(token)
    from services.milestone_engine import get_events_col
    from bson import ObjectId
    try:
        row = get_events_col().find_one({"_id": ObjectId(event_id),
                                          "client_id": str(client["_id"])})
    except Exception:
        row = None
    if not row:
        raise HTTPException(404, "milestone not found")
    return HTMLResponse(row.get("card_html") or "<p>Card missing</p>")
