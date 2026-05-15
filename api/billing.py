"""
Admin Billing API — per-client revenue / cost / margin visibility.

The operator's single-pane view to prevent any runaway client surprising
us at month-end. Surfaces:
  • Per-client rows: revenue, API cost MTD, margin %, top spend feature
  • Per-client drill-in: usage by feature with last 30 days of calls
  • Cohort totals: platform-wide cost, revenue, margin
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import require_auth as _admin_auth
from services.usage_meter import billing_table, usage_for_client

router = APIRouter(prefix="/api/v1/admin/billing", tags=["Billing"])


@router.get("")
async def admin_billing_table(days: int = 30, _: str = Depends(_admin_auth)):
    rows = billing_table(days=days)
    total_revenue = sum(r["revenue_ngn"] for r in rows)
    total_cost = sum(r["cost_ngn"] for r in rows)
    total_margin = total_revenue - total_cost
    avg_margin_pct = round(
        sum(r["margin_pct"] for r in rows if r.get("margin_pct") is not None) /
        max(1, sum(1 for r in rows if r.get("margin_pct") is not None)),
        1,
    ) if rows else None
    return {
        "rows": rows,
        "totals": {
            "revenue_ngn":   round(total_revenue, 2),
            "cost_ngn":      round(total_cost, 2),
            "margin_ngn":    round(total_margin, 2),
            "avg_margin_pct": avg_margin_pct,
            "client_count":  len(rows),
            "at_risk_count": sum(1 for r in rows if r.get("at_risk")),
        },
        "since_days": days,
    }


@router.get("/{client_id}")
async def admin_billing_client(client_id: str, days: int = 30,
                                _: str = Depends(_admin_auth)):
    return usage_for_client(client_id, days=days)
