"""
Payroll API — TalentOS monthly payroll run + Nigerian-compliant payslips.

Routes:
  POST /hr/payroll/staff            — add / update staff on payroll roster
  GET  /hr/payroll/staff            — list roster
  DELETE /hr/payroll/staff/{id}     — remove staff from roster
  POST /hr/payroll/run              — run payroll for a company + period
  GET  /hr/payroll/runs             — list recent runs
  GET  /hr/payroll/runs/{id}/slips  — list payslips for a run
  GET  /hr/payroll/slip/{id}        — single payslip JSON
  GET  /hr/payroll/slip/{id}/html   — printable payslip HTML (PDF via Ctrl-P)
  POST /hr/paye/estimate            — standalone PAYE quick-calc for benchmarking
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from bson import ObjectId
from database.mongo import get_db
from services.hr_suite.payroll import (
    upsert_staff, list_staff, run_payroll, list_runs, list_slips,
    get_slip, render_payslip_html, compute_payslip, compute_paye, compute_cra,
)

router = APIRouter(prefix="/hr", tags=["hr_suite"])


class PayrollStaff(BaseModel):
    company: str
    staff_name: str
    basic: float
    housing: float = 0
    transport: float = 0
    other_allowances: float = 0
    nhf_enrolled: bool = False
    bank_name: str = ""
    account_number: str = ""
    phone: str = ""
    email: str = ""


class PayrollRunRequest(BaseModel):
    company: str
    period: str   # 'YYYY-MM'
    note: str = ""


class PayeEstimate(BaseModel):
    basic: float
    housing: float = 0
    transport: float = 0
    other_allowances: float = 0
    nhf_enrolled: bool = False


@router.post("/payroll/staff", status_code=201)
def payroll_add_staff(req: PayrollStaff):
    sid = upsert_staff(**req.model_dump())
    return {"staff_id": sid, "staff_name": req.staff_name}


@router.get("/payroll/staff")
def payroll_list_staff(company: str = ""):
    return {"staff": list_staff(company)}


@router.delete("/payroll/staff/{staff_id}")
def payroll_remove_staff(staff_id: str):
    try:
        get_db()["hr_payroll_staff"].delete_one({"_id": ObjectId(staff_id)})
    except Exception:
        raise HTTPException(400, "Invalid staff id")
    return {"removed": True}


@router.post("/payroll/run", status_code=201)
def payroll_run(req: PayrollRunRequest):
    result = run_payroll(req.company, req.period, req.note)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/payroll/runs")
def payroll_list_runs(company: str = ""):
    return {"runs": list_runs(company)}


@router.get("/payroll/runs/{run_id}/slips")
def payroll_run_slips(run_id: str):
    return {"slips": list_slips(run_id)}


@router.get("/payroll/slip/{slip_id}")
def payroll_get_slip(slip_id: str):
    slip = get_slip(slip_id)
    if not slip:
        raise HTTPException(404, "Payslip not found")
    return slip


@router.get("/payroll/slip/{slip_id}/html", response_class=HTMLResponse)
def payroll_slip_html(slip_id: str):
    slip = get_slip(slip_id)
    if not slip:
        raise HTTPException(404, "Payslip not found")
    return HTMLResponse(render_payslip_html(slip, slip.get("company", "")))


@router.post("/paye/estimate")
def paye_estimate(req: PayeEstimate):
    """Standalone PAYE calculator — useful for offer-letter modelling."""
    slip = compute_payslip(
        staff_name="<estimate>",
        basic_monthly=req.basic,
        housing_monthly=req.housing,
        transport_monthly=req.transport,
        other_allowances_monthly=req.other_allowances,
        nhf_enrolled=req.nhf_enrolled,
    )
    slip["cra_annual"] = round(compute_cra(slip["annual_gross"]), 2)
    return slip
