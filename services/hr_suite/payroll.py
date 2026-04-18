"""
Nigerian Payroll Engine — PAYE + PENCOM + NHF + Net Pay.

PAYE bands (Personal Income Tax Act as amended):
  First  ₦300,000  → 7%
  Next   ₦300,000  → 11%
  Next   ₦500,000  → 15%
  Next   ₦500,000  → 19%
  Next   ₦1,600,000 → 21%
  Above  ₦3,200,000 → 24%

Consolidated Relief Allowance (CRA):
  Higher of (₦200,000, 1% of gross) + 20% of gross

PENCOM: 8% employee (tax-deductible before PAYE)
NHF: 2.5% of basic (optional for SMEs; skipped if not opted in)
"""
from datetime import datetime, timezone
from database.mongo import get_db
from bson import ObjectId
import structlog

log = structlog.get_logger()

PAYE_BANDS = [
    (300_000,  0.07),
    (300_000,  0.11),
    (500_000,  0.15),
    (500_000,  0.19),
    (1_600_000, 0.21),
    (float("inf"), 0.24),
]

PENCOM_EMPLOYEE_PCT = 0.08
NHF_PCT = 0.025


def _col(name: str):
    return get_db()[name]


def ensure_payroll_indexes():
    _col("hr_payroll_staff").create_index("company")
    _col("hr_payroll_staff").create_index([("company", 1), ("staff_name", 1)], unique=True)
    _col("hr_payroll_runs").create_index([("company", 1), ("period", 1)])
    _col("hr_payslips").create_index([("run_id", 1)])
    _col("hr_payslips").create_index([("staff_name", 1), ("period", 1)])


def compute_paye(annual_taxable: float) -> float:
    """Apply Nigerian PAYE bands to an annual taxable income."""
    if annual_taxable <= 0:
        return 0.0
    remaining = annual_taxable
    tax = 0.0
    for band_size, rate in PAYE_BANDS:
        chunk = min(remaining, band_size)
        tax += chunk * rate
        remaining -= chunk
        if remaining <= 0:
            break
    return tax


def compute_cra(annual_gross: float) -> float:
    """Consolidated Relief Allowance."""
    higher_floor = max(200_000, annual_gross * 0.01)
    return higher_floor + (annual_gross * 0.20)


def compute_payslip(
    staff_name: str,
    basic_monthly: float,
    housing_monthly: float = 0,
    transport_monthly: float = 0,
    other_allowances_monthly: float = 0,
    other_deductions_monthly: float = 0,
    nhf_enrolled: bool = False,
) -> dict:
    """Compute a single month payslip with Nigerian statutory deductions."""
    gross_monthly = basic_monthly + housing_monthly + transport_monthly + other_allowances_monthly
    annual_gross  = gross_monthly * 12

    pencom_emp_monthly = basic_monthly * PENCOM_EMPLOYEE_PCT
    nhf_monthly        = (basic_monthly * NHF_PCT) if nhf_enrolled else 0.0

    cra_annual    = compute_cra(annual_gross)
    pension_annual = pencom_emp_monthly * 12
    nhf_annual    = nhf_monthly * 12

    annual_taxable = max(0, annual_gross - cra_annual - pension_annual - nhf_annual)
    paye_annual    = compute_paye(annual_taxable)
    paye_monthly   = paye_annual / 12

    total_deductions = pencom_emp_monthly + nhf_monthly + paye_monthly + other_deductions_monthly
    net_monthly      = gross_monthly - total_deductions

    return {
        "staff_name":        staff_name,
        "basic":             round(basic_monthly, 2),
        "housing":           round(housing_monthly, 2),
        "transport":         round(transport_monthly, 2),
        "other_allowances":  round(other_allowances_monthly, 2),
        "gross":             round(gross_monthly, 2),
        "pencom_employee":   round(pencom_emp_monthly, 2),
        "nhf":               round(nhf_monthly, 2),
        "paye":              round(paye_monthly, 2),
        "other_deductions":  round(other_deductions_monthly, 2),
        "total_deductions":  round(total_deductions, 2),
        "net_pay":           round(net_monthly, 2),
        "annual_gross":      round(annual_gross, 2),
        "annual_paye":       round(paye_annual, 2),
    }


def upsert_staff(company: str, staff_name: str, basic: float,
                 housing: float = 0, transport: float = 0,
                 other_allowances: float = 0,
                 nhf_enrolled: bool = False,
                 bank_name: str = "", account_number: str = "",
                 phone: str = "", email: str = "") -> str:
    doc = {
        "company":          company,
        "staff_name":       staff_name,
        "basic":            basic,
        "housing":          housing,
        "transport":        transport,
        "other_allowances": other_allowances,
        "nhf_enrolled":     nhf_enrolled,
        "bank_name":        bank_name,
        "account_number":   account_number,
        "phone":            phone,
        "email":            email,
        "updated_at":       datetime.now(timezone.utc),
    }
    _col("hr_payroll_staff").update_one(
        {"company": company, "staff_name": staff_name},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    row = _col("hr_payroll_staff").find_one({"company": company, "staff_name": staff_name})
    return str(row["_id"])


def list_staff(company: str = "") -> list[dict]:
    q = {"company": company} if company else {}
    rows = list(_col("hr_payroll_staff").find(q).sort("staff_name", 1))
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows


def run_payroll(company: str, period: str, note: str = "") -> dict:
    """
    Run payroll for a given period ('YYYY-MM'). Computes payslip per staff.
    Returns run summary; each slip is stored with run_id linkage.
    """
    staff = list_staff(company)
    if not staff:
        return {"error": "No staff in payroll roster for this company."}

    run_doc = {
        "company":     company,
        "period":      period,
        "note":        note,
        "staff_count": len(staff),
        "total_gross": 0.0,
        "total_net":   0.0,
        "total_paye":  0.0,
        "total_pencom": 0.0,
        "created_at":  datetime.now(timezone.utc),
    }
    run_inserted = _col("hr_payroll_runs").insert_one(run_doc)
    run_id = str(run_inserted.inserted_id)

    slips = []
    for s in staff:
        slip = compute_payslip(
            staff_name             = s["staff_name"],
            basic_monthly          = s.get("basic", 0),
            housing_monthly        = s.get("housing", 0),
            transport_monthly      = s.get("transport", 0),
            other_allowances_monthly = s.get("other_allowances", 0),
            nhf_enrolled           = s.get("nhf_enrolled", False),
        )
        slip["company"]     = company
        slip["period"]      = period
        slip["run_id"]      = run_id
        slip["bank_name"]   = s.get("bank_name", "")
        slip["account_number"] = s.get("account_number", "")
        slip["created_at"]  = datetime.now(timezone.utc)
        _col("hr_payslips").insert_one(slip)
        slips.append(slip)

        run_doc["total_gross"]  += slip["gross"]
        run_doc["total_net"]    += slip["net_pay"]
        run_doc["total_paye"]   += slip["paye"]
        run_doc["total_pencom"] += slip["pencom_employee"]

    _col("hr_payroll_runs").update_one(
        {"_id": run_inserted.inserted_id},
        {"$set": {
            "total_gross":  round(run_doc["total_gross"], 2),
            "total_net":    round(run_doc["total_net"], 2),
            "total_paye":   round(run_doc["total_paye"], 2),
            "total_pencom": round(run_doc["total_pencom"], 2),
        }},
    )

    log.info("payroll_run_complete",
             company=company, period=period, staff=len(slips),
             net=round(run_doc["total_net"], 2))

    return {
        "run_id":       run_id,
        "company":      company,
        "period":       period,
        "staff_count":  len(slips),
        "total_gross":  round(run_doc["total_gross"], 2),
        "total_net":    round(run_doc["total_net"], 2),
        "total_paye":   round(run_doc["total_paye"], 2),
        "total_pencom": round(run_doc["total_pencom"], 2),
    }


def list_runs(company: str = "") -> list[dict]:
    q = {"company": company} if company else {}
    rows = list(_col("hr_payroll_runs").find(q).sort("created_at", -1).limit(24))
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows


def list_slips(run_id: str) -> list[dict]:
    rows = list(_col("hr_payslips").find({"run_id": run_id}).sort("staff_name", 1))
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows


def get_slip(slip_id: str) -> dict | None:
    try:
        doc = _col("hr_payslips").find_one({"_id": ObjectId(slip_id)})
    except Exception:
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def render_payslip_html(slip: dict, company: str) -> str:
    """Return a standalone HTML payslip — client prints to PDF."""
    period = slip.get("period", "")
    s = slip
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Payslip — {s['staff_name']} — {period}</title>
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;color:#111;max-width:640px;margin:32px auto;padding:0 24px;}}
 h1{{margin:0;font-size:20px;}}
 .meta{{color:#666;font-size:13px;margin-top:4px;}}
 table{{width:100%;border-collapse:collapse;margin-top:24px;}}
 th,td{{padding:8px 12px;border-bottom:1px solid #eee;text-align:left;font-size:13px;}}
 th{{background:#fafafa;font-weight:600;text-transform:uppercase;letter-spacing:.04em;font-size:11px;color:#555;}}
 td.amount{{text-align:right;font-variant-numeric:tabular-nums;}}
 .row-total{{background:#f7f7f7;font-weight:700;}}
 .net{{background:#0a5a3a;color:#fff;}}
 .net td{{border-bottom:none;}}
 @media print {{ body{{margin:0;}} }}
</style></head>
<body>
 <h1>{company}</h1>
 <div class="meta">Payslip — <b>{s['staff_name']}</b> — Period: <b>{period}</b></div>
 <table>
  <tr><th>Earnings</th><th class="amount">₦</th></tr>
  <tr><td>Basic</td><td class="amount">{s['basic']:,.2f}</td></tr>
  <tr><td>Housing</td><td class="amount">{s['housing']:,.2f}</td></tr>
  <tr><td>Transport</td><td class="amount">{s['transport']:,.2f}</td></tr>
  <tr><td>Other Allowances</td><td class="amount">{s['other_allowances']:,.2f}</td></tr>
  <tr class="row-total"><td>Gross Pay</td><td class="amount">{s['gross']:,.2f}</td></tr>
 </table>
 <table>
  <tr><th>Deductions</th><th class="amount">₦</th></tr>
  <tr><td>PAYE Tax</td><td class="amount">{s['paye']:,.2f}</td></tr>
  <tr><td>Pension (8%)</td><td class="amount">{s['pencom_employee']:,.2f}</td></tr>
  <tr><td>NHF (2.5%)</td><td class="amount">{s['nhf']:,.2f}</td></tr>
  <tr><td>Other</td><td class="amount">{s['other_deductions']:,.2f}</td></tr>
  <tr class="row-total"><td>Total Deductions</td><td class="amount">{s['total_deductions']:,.2f}</td></tr>
 </table>
 <table>
  <tr class="net"><td>NET PAY</td><td class="amount">₦{s['net_pay']:,.2f}</td></tr>
 </table>
 <div class="meta" style="margin-top:32px;">Pay to: {s.get('bank_name','')} — {s.get('account_number','')}</div>
 <div class="meta" style="margin-top:4px;font-size:11px;">Generated by ReachNG TalentOS · {datetime.now().strftime('%Y-%m-%d')}</div>
</body></html>"""
