"""
Rent Roll API — EstateOS landlord unit inventory + automated rent chase.

Routes:
  POST /estate/rent/units            — add rentable unit
  GET  /estate/rent/units            — list units (per landlord_company)
  POST /estate/rent/tenants          — assign tenant to a unit
  GET  /estate/rent/tenants          — list active tenants
  POST /estate/rent/period/open      — open rent charges for a period (idempotent)
  GET  /estate/rent/overdue          — list all overdue charges with stage
  POST /estate/rent/charge/{id}/paid — mark a charge as paid
  POST /estate/rent/chase/run        — run the chase loop: generate drafts → HITL queue
  GET  /estate/rent/overview         — KPI summary (occupied, collected, outstanding)
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from bson import ObjectId
from database.mongo import get_db
from services.estate.rent_roll import (
    add_unit, list_units, assign_tenant, list_tenants,
    open_charges_for_period, get_overdue_charges, mark_paid, record_chase,
    stage_for_days_overdue,
)
import anthropic
from config import get_settings
from tools.hitl import queue_draft

router = APIRouter(prefix="/estate/rent", tags=["estate_os"])


class UnitCreate(BaseModel):
    landlord_company: str
    address: str
    unit_label: str = ""
    monthly_rent_ngn: float
    rent_cycle: str = "monthly"
    property_type: str = "residential"
    landlord_bank_name: str = ""
    landlord_account_number: str = ""
    landlord_account_name: str = ""
    landlord_phone: str = ""


class TenantAssign(BaseModel):
    unit_id: str
    tenant_name: str
    tenant_phone: str
    tenant_email: str = ""
    lease_start: str = ""
    lease_months: int = 12
    rent_due_day: int = 1


class PeriodOpen(BaseModel):
    period: str   # YYYY-MM


class MarkPaid(BaseModel):
    amount_paid: float | None = None


_CHASE_SYSTEM = """You are a professional Nigerian property manager writing WhatsApp rent reminders \
to tenants on behalf of the landlord. Tone escalates with days overdue:
- friendly  (1-6 days): warm, assumes oversight
- firm      (7-13 days): direct, references amount and date
- serious   (14-29 days): clear consequences, mention quit notice possibility
- warning   (30-59 days): formal tone, explicit quit notice threat, mention Lagos Tenancy Law
- final     (60+ days): formal quit notice draft with 7-day ultimatum

Rules:
1. Address tenant by first name
2. State exact amount owed and the period (e.g. "April 2026 rent")
3. Reference the unit address
4. Never rude or threatening violence — firm and professional only
5. WhatsApp messages max 5 sentences (friendly/firm/serious/warning); final is a formal letter
"""


def _claude(prompt: str, max_tokens: int = 500) -> str:
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=_CHASE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# ── Units ─────────────────────────────────────────────────────────────────────

@router.post("/units", status_code=201)
def rr_add_unit(req: UnitCreate):
    uid = add_unit(
        landlord_company=req.landlord_company,
        address=req.address,
        unit_label=req.unit_label,
        monthly_rent_ngn=req.monthly_rent_ngn,
        rent_cycle=req.rent_cycle,
        property_type=req.property_type,
        landlord_bank_name=req.landlord_bank_name,
        landlord_account_number=req.landlord_account_number,
        landlord_account_name=req.landlord_account_name,
        landlord_phone=req.landlord_phone,
    )
    return {"unit_id": uid, "address": req.address}


@router.get("/units")
def rr_list_units(landlord_company: str = ""):
    return {"units": list_units(landlord_company)}


# ── Tenants ───────────────────────────────────────────────────────────────────

@router.post("/tenants", status_code=201)
def rr_assign_tenant(req: TenantAssign):
    tid = assign_tenant(
        unit_id=req.unit_id,
        tenant_name=req.tenant_name,
        tenant_phone=req.tenant_phone,
        tenant_email=req.tenant_email,
        lease_start=req.lease_start,
        lease_months=req.lease_months,
        rent_due_day=req.rent_due_day,
    )
    return {"tenant_id": tid, "tenant_name": req.tenant_name}


@router.get("/tenants")
def rr_list_tenants(unit_id: str = ""):
    return {"tenants": list_tenants(unit_id)}


# ── Period open ───────────────────────────────────────────────────────────────

@router.post("/period/open", status_code=201)
def rr_open_period(req: PeriodOpen):
    opened = open_charges_for_period(req.period)
    return {"period": req.period, "charges_opened": opened}


# ── Overdue + payment ─────────────────────────────────────────────────────────

@router.get("/overdue")
def rr_overdue(landlord_company: str = ""):
    return {"overdue": get_overdue_charges(landlord_company)}


@router.post("/charge/{charge_id}/paid")
def rr_mark_paid(charge_id: str, body: MarkPaid):
    try:
        mark_paid(charge_id, body.amount_paid)
    except Exception:
        raise HTTPException(400, "Invalid charge id")
    return {"charge_id": charge_id, "status": "paid"}


# ── Chase loop ────────────────────────────────────────────────────────────────

@router.post("/chase/run")
def rr_run_chase(landlord_company: str = ""):
    """Generate chase drafts for every overdue charge and queue into HITL Message Queue."""
    overdue = get_overdue_charges(landlord_company)
    queued = 0
    errors = 0
    for c in overdue:
        try:
            stage = c["stage"]
            unit = c['unit']
            bank_line = ""
            if unit.get('landlord_bank_name') and unit.get('landlord_account_number'):
                bank_line = (f"\nPAYMENT DETAILS (MUST be included verbatim in the message so the tenant can transfer directly): "
                             f"{unit['landlord_bank_name']} — {unit['landlord_account_number']}"
                             f"{' (' + unit['landlord_account_name'] + ')' if unit.get('landlord_account_name') else ''}")

            prompt = f"""Write a WhatsApp rent reminder at stage: {stage['label']} ({stage['tone']} tone).

LANDLORD / PROPERTY MANAGER: {unit['landlord_company']}
TENANT: {c['tenant']['name']}
UNIT: {unit['address']}{' — ' + unit['unit_label'] if unit['unit_label'] else ''}
PERIOD OWED: {c['period']}
AMOUNT OWED: ₦{c['amount_ngn']:,.0f}
DAYS OVERDUE: {c['days_overdue']}
PRIOR CHASES SENT: {c.get('chase_count', 0)}{bank_line}

Write the WhatsApp message only. No explanation. If payment details are provided above, include them in the message exactly as shown."""
            message = _claude(prompt)

            queue_draft(
                contact_id=str(ObjectId()),
                contact_name=c['tenant']['name'],
                vertical="estate_rent",
                channel="whatsapp",
                message=message,
                phone=c['tenant']['phone'],
                source="rent",
            )
            record_chase(c["_id"])
            queued += 1
        except Exception:
            errors += 1
    return {"overdue_found": len(overdue), "queued": queued, "errors": errors}


# ── Overview KPIs ─────────────────────────────────────────────────────────────

@router.get("/overview")
def rr_overview(landlord_company: str = ""):
    units_col  = get_db()["estate_units"]
    tenant_col = get_db()["estate_tenants"]
    ledger_col = get_db()["estate_rent_ledger"]

    uq = {"landlord_company": landlord_company} if landlord_company else {}
    units = list(units_col.find(uq))
    unit_ids = [str(u["_id"]) for u in units]

    occupied = tenant_col.count_documents({"unit_id": {"$in": unit_ids}, "status": "active"})
    total_units = len(units)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    collected_this_month = sum(
        c.get("paid_amount", 0) or c.get("amount_ngn", 0)
        for c in ledger_col.find({"unit_id": {"$in": unit_ids},
                                  "status": "paid", "paid_at": {"$gte": month_start}})
    )

    outstanding_open = list(ledger_col.find({"unit_id": {"$in": unit_ids}, "status": "open",
                                             "due_date": {"$lt": now}}))
    total_outstanding = sum(c["amount_ngn"] for c in outstanding_open)

    return {
        "total_units":         total_units,
        "occupied":            occupied,
        "vacancy_rate":        round((total_units - occupied) / total_units * 100, 1) if total_units else 0,
        "collected_this_month": round(collected_this_month, 2),
        "outstanding_overdue": round(total_outstanding, 2),
        "overdue_charge_count": len(outstanding_open),
    }
