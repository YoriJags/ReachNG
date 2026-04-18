"""
HR Suite API — 8 HR features for Nigerian SMEs.

Routes:
  POST /hr/screener              — create screening campaign (AI questions)
  GET  /hr/screener              — list campaigns
  POST /hr/attendance/staff      — register staff for attendance
  GET  /hr/attendance            — today's attendance summary
  POST /hr/leave                 — log leave request
  GET  /hr/leave/pending         — pending leave requests
  POST /hr/benchmark             — salary benchmarking (AI)
  GET  /hr/benchmark             — recent benchmarks
  POST /hr/pencom/staff          — enroll staff for PENCOM
  GET  /hr/pencom/stats          — PENCOM KPIs
  GET  /hr/pencom/schedule       — remittance schedule
  POST /hr/offboarding           — generate offboarding checklist (AI)
  POST /hr/probation             — add probation track
  GET  /hr/probation/upcoming    — confirmations due in 30 days
  POST /hr/policy/upload         — store company policy doc
  POST /hr/policy/ask            — ask policy question (AI)
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime, timezone, date, timedelta
from database.mongo import get_db
from services.hr_suite.engine import (
    generate_screening_questions, benchmark_salary,
    generate_offboarding_checklist, answer_policy_question, calculate_pencom,
)
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/hr", tags=["hr_suite"])


def _col(name: str):
    return get_db()[name]


# ── Pydantic Models ────────────────────────────────────────────────────────────

class ScreenerCreate(BaseModel):
    company: str = ""
    role: str
    sector: str = ""
    requirements: str = ""
    salary_range: str = ""
    location: str = "Lagos"


class AttendanceStaff(BaseModel):
    company: str = ""
    name: str
    phone: str
    role: str
    work_start: str = "08:00"
    work_end: str   = "17:00"


class LeaveRequest(BaseModel):
    company: str = ""
    staff_name: str
    leave_type: str
    start_date: str
    end_date: str
    reason: str = ""


class BenchmarkRequest(BaseModel):
    role: str
    sector: str = ""
    location: str = "Lagos"
    years_exp: str = "2-5"
    company_size: str = "sme"


class PencomStaff(BaseModel):
    company: str = ""
    staff_name: str
    pfa: str = ""
    rsa_pin: str = ""
    basic_salary_ngn: float


class OffboardingRequest(BaseModel):
    company: str = ""
    staff_name: str
    role: str
    last_day: str
    reason: str = "resignation"
    assets: str = ""


class ProbationRecord(BaseModel):
    company: str = ""
    staff_name: str
    role: str
    start_date: str
    probation_months: int = 3
    manager_phone: str = ""


class PolicyUpload(BaseModel):
    company: str
    policy_text: str


class PolicyQuestion(BaseModel):
    company: str
    question: str


# ── Job Screener ───────────────────────────────────────────────────────────────

@router.post("/screener", status_code=201)
def hr_create_screener(req: ScreenerCreate):
    questions = generate_screening_questions(
        req.role, req.sector, req.requirements, req.salary_range, req.location
    )
    doc = {**req.model_dump(), "questions": questions, "responses": 0,
           "created_at": datetime.now(timezone.utc)}
    inserted = _col("hr_screenings").insert_one(doc)
    return {"screening_id": str(inserted.inserted_id), "questions": questions}


@router.get("/screener")
def hr_list_screenings():
    docs = list(_col("hr_screenings").find().sort("created_at", -1).limit(50))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"campaigns": docs}


# ── Attendance ─────────────────────────────────────────────────────────────────

@router.post("/attendance/staff", status_code=201)
def hr_add_attendance_staff(req: AttendanceStaff):
    doc = {**req.model_dump(), "created_at": datetime.now(timezone.utc)}
    _col("hr_attendance_staff").update_one(
        {"name": req.name, "company": req.company},
        {"$set": doc}, upsert=True,
    )
    return {"name": req.name, "status": "registered"}


@router.get("/attendance")
def hr_attendance_today():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    records = list(_col("hr_attendance_log").find({"date": {"$gte": today_start}}).sort("clock_in", 1))
    for r in records:
        r["_id"] = str(r["_id"])
    staff_count = _col("hr_attendance_staff").count_documents({})
    return {"date": date.today().isoformat(), "present": len(records),
            "total_registered": staff_count, "records": records}


# ── Leave Manager ──────────────────────────────────────────────────────────────

@router.post("/leave", status_code=201)
def hr_log_leave(req: LeaveRequest):
    doc = {**req.model_dump(), "status": "pending", "created_at": datetime.now(timezone.utc)}
    inserted = _col("hr_leave_requests").insert_one(doc)
    return {"request_id": str(inserted.inserted_id), "status": "pending"}


@router.get("/leave/pending")
def hr_leave_pending(company: str = Query(default="")):
    q = {"status": "pending"}
    if company:
        q["company"] = company
    docs = list(_col("hr_leave_requests").find(q).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"pending": docs, "count": len(docs)}


# ── Salary Benchmarking ────────────────────────────────────────────────────────

@router.post("/benchmark", status_code=201)
def hr_benchmark(req: BenchmarkRequest):
    result = benchmark_salary(req.role, req.sector, req.location, req.years_exp, req.company_size)
    doc = {**req.model_dump(), **result, "created_at": datetime.now(timezone.utc)}
    _col("hr_benchmarks").insert_one(doc)
    return result


@router.get("/benchmark")
def hr_list_benchmarks():
    docs = list(_col("hr_benchmarks").find().sort("created_at", -1).limit(30))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"benchmarks": docs}


# ── PENCOM ─────────────────────────────────────────────────────────────────────

@router.post("/pencom/staff", status_code=201)
def hr_add_pencom(req: PencomStaff):
    calc = calculate_pencom(req.basic_salary_ngn)
    doc = {**req.model_dump(), **calc,
           "last_remittance_date": None, "enrolled_at": datetime.now(timezone.utc)}
    _col("hr_pencom_staff").update_one(
        {"staff_name": req.staff_name, "company": req.company},
        {"$set": doc}, upsert=True,
    )
    return {**calc, "staff_name": req.staff_name}


@router.get("/pencom/stats")
def hr_pencom_stats(company: str = Query(default="")):
    q = {"company": company} if company else {}
    staff = list(_col("hr_pencom_staff").find(q))
    now = datetime.now(timezone.utc)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    overdue = sum(
        1 for s in staff
        if not s.get("last_remittance_date") or
        (s.get("last_remittance_date") and s["last_remittance_date"] < this_month_start)
    )
    monthly_total = sum(s.get("total_monthly", 0) for s in staff)
    return {
        "enrolled": len(staff),
        "overdue_remittances": overdue,
        "this_month_ngn": monthly_total,
    }


@router.get("/pencom/schedule")
def hr_pencom_schedule(company: str = Query(default="")):
    q = {"company": company} if company else {}
    staff = list(_col("hr_pencom_staff").find(q).sort("staff_name", 1))
    for s in staff:
        s["_id"] = str(s["_id"])
    return {"schedule": staff}


# ── Offboarding ────────────────────────────────────────────────────────────────

@router.post("/offboarding", status_code=201)
def hr_offboarding(req: OffboardingRequest):
    checklist = generate_offboarding_checklist(
        req.company, req.staff_name, req.role, req.last_day, req.reason, req.assets
    )
    doc = {**req.model_dump(), "checklist": checklist, "created_at": datetime.now(timezone.utc)}
    _col("hr_offboarding").insert_one(doc)
    return {"checklist": checklist, "staff_name": req.staff_name}


# ── Probation Tracker ──────────────────────────────────────────────────────────

@router.post("/probation", status_code=201)
def hr_add_probation(req: ProbationRecord):
    try:
        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
    except ValueError:
        start = date.today()
    confirm_date = (start.replace(day=1) if req.probation_months else start)
    # Add months properly
    m = start.month + req.probation_months
    y = start.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    try:
        confirm_date = start.replace(year=y, month=m)
    except ValueError:
        confirm_date = start.replace(year=y, month=m, day=28)

    doc = {
        **req.model_dump(),
        "confirmation_date": confirm_date.isoformat(),
        "days_remaining": (confirm_date - date.today()).days,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    _col("hr_probation").update_one(
        {"staff_name": req.staff_name, "company": req.company},
        {"$set": doc}, upsert=True,
    )
    return {"staff_name": req.staff_name, "confirmation_date": confirm_date.isoformat(),
            "days_remaining": doc["days_remaining"]}


@router.get("/probation/upcoming")
def hr_probation_upcoming(company: str = Query(default=""), days: int = 30):
    q = {"status": "active"}
    if company:
        q["company"] = company
    all_prob = list(_col("hr_probation").find(q))
    cutoff = date.today() + timedelta(days=days)
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


# ── Policy Bot ─────────────────────────────────────────────────────────────────

@router.post("/policy/upload", status_code=201)
def hr_policy_upload(req: PolicyUpload):
    _col("hr_policies").update_one(
        {"company": req.company},
        {"$set": {"company": req.company, "policy_text": req.policy_text,
                  "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    word_count = len(req.policy_text.split())
    return {"company": req.company, "status": "uploaded", "word_count": word_count}


@router.post("/policy/ask")
def hr_policy_ask(req: PolicyQuestion):
    policy_doc = _col("hr_policies").find_one({"company": req.company})
    if not policy_doc:
        return {"answer": "No policy document found for this company. Please upload your handbook first."}
    answer = answer_policy_question(policy_doc["policy_text"], req.question)
    return {"answer": answer, "company": req.company}
