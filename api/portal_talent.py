"""
TalentOS Client Portal — token-gated API + page for HR/employer clients.
All routes validate the portal token; no Basic Auth required on the client side.
"""
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, timezone, date, timedelta
from database.mongo import get_db
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/portal/talent", tags=["portal_talent"])


def _get_client(token: str) -> dict:
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(403, "Invalid or expired portal token")
    return client


def _str(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    for k, v in doc.items():
        if hasattr(v, "isoformat"):
            doc[k] = v.isoformat()
    return doc


def _company(client: dict) -> str:
    return client.get("company", client["name"])


# ── Page ──────────────────────────────────────────────────────────────────────

@router.get("/{token}", response_class=HTMLResponse)
async def talent_portal_page(token: str, request: Request):
    client = _get_client(token)
    return request.app.state.templates.TemplateResponse(
        request, "portal_talent.html",
        {"token": token, "client_name": client["name"], "company": _company(client)},
    )


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/{token}/overview")
def talent_portal_overview(token: str):
    client = _get_client(token)
    db = get_db()
    company = _company(client)
    q = {"company": company}
    staff_count = db["hr_attendance_staff"].count_documents(q)
    pending_leave = db["hr_leave_requests"].count_documents({**q, "status": "pending"})
    open_screenings = db["hr_screenings"].count_documents(q)
    probation_due = db["hr_probation"].count_documents({**q, "status": "active"})
    return {
        "staff_registered": staff_count,
        "pending_leave": pending_leave,
        "open_screenings": open_screenings,
        "probation_active": probation_due,
        "company": company,
    }


# ── Job Screener ───────────────────────────────────────────────────────────────

class _ScreenerReq(BaseModel):
    role: str
    sector: str = ""
    requirements: str = ""
    salary_range: str = ""
    location: str = "Lagos"


@router.get("/{token}/screener")
def talent_portal_list_screenings(token: str):
    client = _get_client(token)
    company = _company(client)
    docs = list(get_db()["hr_screenings"].find({"company": company}).sort("created_at", -1).limit(50))
    return {"campaigns": [_str(d) for d in docs]}


@router.post("/{token}/screener", status_code=201)
def talent_portal_create_screening(token: str, req: _ScreenerReq):
    client = _get_client(token)
    company = _company(client)
    from services.hr_suite.engine import generate_screening_questions
    questions = generate_screening_questions(req.role, req.sector, req.requirements, req.salary_range, req.location)
    doc = {**req.model_dump(), "company": company, "questions": questions, "responses": 0, "created_at": datetime.now(timezone.utc)}
    inserted = get_db()["hr_screenings"].insert_one(doc)
    return {"screening_id": str(inserted.inserted_id), "questions": questions}


# ── Attendance ─────────────────────────────────────────────────────────────────

class _AttendanceStaffReq(BaseModel):
    name: str
    phone: str
    role: str
    work_start: str = "08:00"
    work_end: str = "17:00"


@router.get("/{token}/attendance")
def talent_portal_attendance_today(token: str):
    client = _get_client(token)
    company = _company(client)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    records = list(get_db()["hr_attendance_log"].find({"company": company, "date": {"$gte": today_start}}).sort("clock_in", 1))
    for r in records:
        r["_id"] = str(r["_id"])
    staff_count = get_db()["hr_attendance_staff"].count_documents({"company": company})
    return {"date": date.today().isoformat(), "present": len(records), "total_registered": staff_count, "records": records}


@router.post("/{token}/attendance/staff", status_code=201)
def talent_portal_add_staff(token: str, req: _AttendanceStaffReq):
    client = _get_client(token)
    company = _company(client)
    doc = {**req.model_dump(), "company": company, "created_at": datetime.now(timezone.utc)}
    get_db()["hr_attendance_staff"].update_one(
        {"name": req.name, "company": company}, {"$set": doc}, upsert=True,
    )
    return {"name": req.name, "status": "registered"}


# ── Leave Manager ──────────────────────────────────────────────────────────────

class _LeaveReq(BaseModel):
    staff_name: str
    leave_type: str
    start_date: str
    end_date: str
    reason: str = ""


@router.get("/{token}/leave")
def talent_portal_leave_pending(token: str):
    client = _get_client(token)
    company = _company(client)
    docs = list(get_db()["hr_leave_requests"].find({"company": company, "status": "pending"}).sort("created_at", -1))
    return {"pending": [_str(d) for d in docs], "count": len(docs)}


@router.post("/{token}/leave", status_code=201)
def talent_portal_log_leave(token: str, req: _LeaveReq):
    client = _get_client(token)
    company = _company(client)
    doc = {**req.model_dump(), "company": company, "status": "pending", "created_at": datetime.now(timezone.utc)}
    inserted = get_db()["hr_leave_requests"].insert_one(doc)
    return {"request_id": str(inserted.inserted_id), "status": "pending"}


@router.patch("/{token}/leave/{request_id}")
def talent_portal_approve_leave(token: str, request_id: str, action: str = Query(default="approve")):
    _get_client(token)
    from bson import ObjectId
    status = "approved" if action == "approve" else "rejected"
    get_db()["hr_leave_requests"].update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": status, "actioned_at": datetime.now(timezone.utc)}},
    )
    return {"request_id": request_id, "status": status}


# ── Salary Benchmark ──────────────────────────────────────────────────────────

class _BenchmarkReq(BaseModel):
    role: str
    sector: str = ""
    location: str = "Lagos"
    years_exp: str = "2-5"
    company_size: str = "sme"


@router.get("/{token}/benchmark")
def talent_portal_list_benchmarks(token: str):
    client = _get_client(token)
    company = _company(client)
    docs = list(get_db()["hr_benchmarks"].find({"company": company}).sort("created_at", -1).limit(30))
    return {"benchmarks": [_str(d) for d in docs]}


@router.post("/{token}/benchmark", status_code=201)
def talent_portal_benchmark(token: str, req: _BenchmarkReq):
    client = _get_client(token)
    company = _company(client)
    from services.hr_suite.engine import benchmark_salary
    result = benchmark_salary(req.role, req.sector, req.location, req.years_exp, req.company_size)
    doc = {**req.model_dump(), **result, "company": company, "created_at": datetime.now(timezone.utc)}
    get_db()["hr_benchmarks"].insert_one(doc)
    return result


# ── PENCOM ─────────────────────────────────────────────────────────────────────

class _PencomReq(BaseModel):
    staff_name: str
    pfa: str = ""
    rsa_pin: str = ""
    basic_salary_ngn: float


@router.get("/{token}/pencom")
def talent_portal_pencom_stats(token: str):
    client = _get_client(token)
    company = _company(client)
    staff = list(get_db()["hr_pencom_staff"].find({"company": company}))
    now = datetime.now(timezone.utc)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    overdue = sum(
        1 for s in staff
        if not s.get("last_remittance_date") or s.get("last_remittance_date") < this_month_start
    )
    monthly_total = sum(s.get("total_monthly", 0) for s in staff)
    schedule = [_str(s) for s in staff]
    return {"enrolled": len(staff), "overdue_remittances": overdue, "this_month_ngn": monthly_total, "schedule": schedule}


@router.post("/{token}/pencom/staff", status_code=201)
def talent_portal_add_pencom(token: str, req: _PencomReq):
    client = _get_client(token)
    company = _company(client)
    from services.hr_suite.engine import calculate_pencom
    calc = calculate_pencom(req.basic_salary_ngn)
    doc = {**req.model_dump(), **calc, "company": company, "last_remittance_date": None, "enrolled_at": datetime.now(timezone.utc)}
    get_db()["hr_pencom_staff"].update_one(
        {"staff_name": req.staff_name, "company": company}, {"$set": doc}, upsert=True,
    )
    return {**calc, "staff_name": req.staff_name}


# ── Offboarding ────────────────────────────────────────────────────────────────

class _OffboardingReq(BaseModel):
    staff_name: str
    role: str
    last_day: str
    reason: str = "resignation"
    assets: str = ""


@router.post("/{token}/offboarding", status_code=201)
def talent_portal_offboarding(token: str, req: _OffboardingReq):
    client = _get_client(token)
    company = _company(client)
    from services.hr_suite.engine import generate_offboarding_checklist
    checklist = generate_offboarding_checklist(company, req.staff_name, req.role, req.last_day, req.reason, req.assets)
    doc = {**req.model_dump(), "company": company, "checklist": checklist, "created_at": datetime.now(timezone.utc)}
    get_db()["hr_offboarding"].insert_one(doc)
    return {"checklist": checklist, "staff_name": req.staff_name}


# ── Probation ──────────────────────────────────────────────────────────────────

class _ProbationReq(BaseModel):
    staff_name: str
    role: str
    start_date: str
    probation_months: int = 3
    manager_phone: str = ""


@router.get("/{token}/probation")
def talent_portal_probation_upcoming(token: str, days: int = Query(default=30)):
    client = _get_client(token)
    company = _company(client)
    all_prob = list(get_db()["hr_probation"].find({"company": company, "status": "active"}))
    upcoming = []
    for p in all_prob:
        try:
            conf = date.fromisoformat(p["confirmation_date"])
            remaining = (conf - date.today()).days
            if 0 <= remaining <= days:
                p["_id"] = str(p["_id"])
                p["days_remaining"] = remaining
                upcoming.append(p)
        except Exception:
            pass
    upcoming.sort(key=lambda x: x["days_remaining"])
    return {"upcoming": upcoming, "count": len(upcoming)}


@router.post("/{token}/probation", status_code=201)
def talent_portal_add_probation(token: str, req: _ProbationReq):
    client = _get_client(token)
    company = _company(client)
    try:
        start = date.fromisoformat(req.start_date)
    except ValueError:
        start = date.today()
    m = start.month + req.probation_months
    y = start.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    try:
        confirm_date = start.replace(year=y, month=m)
    except ValueError:
        confirm_date = start.replace(year=y, month=m, day=28)
    doc = {
        **req.model_dump(), "company": company,
        "confirmation_date": confirm_date.isoformat(),
        "days_remaining": (confirm_date - date.today()).days,
        "status": "active", "created_at": datetime.now(timezone.utc),
    }
    get_db()["hr_probation"].update_one(
        {"staff_name": req.staff_name, "company": company}, {"$set": doc}, upsert=True,
    )
    return {"staff_name": req.staff_name, "confirmation_date": confirm_date.isoformat(), "days_remaining": doc["days_remaining"]}


# ── Policy Oracle ──────────────────────────────────────────────────────────────

class _PolicyUploadReq(BaseModel):
    policy_text: str


class _PolicyAskReq(BaseModel):
    question: str


@router.post("/{token}/policy/upload", status_code=201)
def talent_portal_policy_upload(token: str, req: _PolicyUploadReq):
    client = _get_client(token)
    company = _company(client)
    get_db()["hr_policies"].update_one(
        {"company": company},
        {"$set": {"company": company, "policy_text": req.policy_text, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"company": company, "status": "uploaded", "word_count": len(req.policy_text.split())}


@router.post("/{token}/policy/ask")
def talent_portal_policy_ask(token: str, req: _PolicyAskReq):
    client = _get_client(token)
    company = _company(client)
    policy_doc = get_db()["hr_policies"].find_one({"company": company})
    if not policy_doc:
        return {"answer": "No policy document uploaded yet. Please upload your staff handbook first."}
    from services.hr_suite.engine import answer_policy_question
    answer = answer_policy_question(policy_doc["policy_text"], req.question)
    return {"answer": answer, "company": company}
