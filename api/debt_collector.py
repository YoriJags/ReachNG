"""
Informal Debt Collector API.

Routes:
  GET  /dc/overview          — KPIs for dashboard
  GET  /dc/cases             — list active cases
  POST /dc/cases             — add new debt case
  POST /dc/cases/{id}/paid   — mark case as paid
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
from services.debt_collector import store
from services.debt_collector.engine import generate_recovery_message, get_stage_for_days_overdue
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/dc", tags=["debt_collector"])


class NewCaseRequest(BaseModel):
    client_name: str
    debtor_name: str
    debtor_business: str
    debtor_phone: str
    amount_ngn: float
    description: str
    original_due_date: str          # ISO date string
    relationship_context: str = ""


@router.get("/overview")
def dc_overview():
    active = store.list_cases(status="active")
    paid   = store.list_cases(status="paid")
    today  = datetime.now(timezone.utc)

    total_overdue = sum(c["amount_ngn"] for c in active)
    legal_stage   = sum(1 for c in active if c.get("current_stage") == "legal")

    # Recovered this month = paid cases marked paid this month
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    recovered   = sum(
        c["amount_ngn"] for c in paid
        if c.get("paid_at") and datetime.fromisoformat(str(c["paid_at"])).replace(tzinfo=timezone.utc) >= month_start
    )

    return {
        "active_cases":       len(active),
        "total_overdue_ngn":  total_overdue,
        "at_legal_stage":     legal_stage,
        "recovered_this_month": recovered,
    }


@router.get("/cases")
def dc_cases():
    cases = store.list_cases(status="active")
    today = datetime.now(timezone.utc)
    enriched = []
    for c in cases:
        due = c.get("original_due_date")
        if due:
            try:
                due_dt = datetime.fromisoformat(str(due)).replace(tzinfo=timezone.utc)
                days_overdue = max(0, (today - due_dt).days)
            except Exception:
                days_overdue = 0
        else:
            days_overdue = 0
        stage = get_stage_for_days_overdue(days_overdue)
        c["days_overdue"] = days_overdue
        c["stage_label"]  = stage["label"]
        enriched.append(c)
    return {"cases": enriched}


@router.post("/cases", status_code=201)
def dc_add_case(req: NewCaseRequest):
    try:
        due_dt = datetime.fromisoformat(req.original_due_date).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid original_due_date — use YYYY-MM-DD")

    case_id = store.create_case(
        client_name=req.client_name,
        debtor_name=req.debtor_name,
        debtor_business=req.debtor_business,
        debtor_phone=req.debtor_phone,
        amount_ngn=req.amount_ngn,
        description=req.description,
        original_due_date=due_dt,
        relationship_context=req.relationship_context,
    )
    return {"case_id": case_id, "status": "created"}


@router.post("/cases/{case_id}/paid")
def dc_mark_paid(case_id: str):
    store.mark_paid(case_id)
    return {"case_id": case_id, "status": "paid"}
