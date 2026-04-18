"""
Naira Salary Erosion Tracker API.

Routes:
  GET  /salary-erosion/dashboard              — KPIs + staff list with erosion data
  POST /salary-erosion/staff                  — add a staff member to track
  GET  /salary-erosion/report?company=...     — AI-generated retention report
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.salary_erosion.engine import calculate_erosion, generate_erosion_report
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/salary-erosion", tags=["salary_erosion"])

COLLECTION = "salary_erosion_staff"


def _col():
    return get_db()[COLLECTION]


class StaffRecord(BaseModel):
    company: str = ""
    name: str
    role: str
    salary_ngn: float
    hired_date: str     # YYYY-MM-DD


@router.get("/dashboard")
def se_dashboard():
    docs = list(_col().find().sort("name", 1))
    enriched = []
    total_erosion = 0.0
    at_risk = 0

    for d in docs:
        d["_id"] = str(d["_id"])
        erosion = calculate_erosion(d["salary_ngn"], d["hired_date"])
        d.update(erosion)
        total_erosion += erosion["erosion_pct"]
        if erosion["churn_risk"] in ("high", "medium"):
            at_risk += 1
        enriched.append(d)

    count = len(enriched)
    return {
        "total_staff":       count,
        "avg_erosion_pct":   round(total_erosion / count, 1) if count else 0.0,
        "at_churn_risk":     at_risk,
        "staff":             enriched,
    }


@router.post("/staff", status_code=201)
def se_add_staff(req: StaffRecord):
    doc = {**req.model_dump(), "created_at": datetime.now(timezone.utc)}
    _col().update_one(
        {"name": req.name, "company": req.company},
        {"$set": doc},
        upsert=True,
    )
    erosion = calculate_erosion(req.salary_ngn, req.hired_date)
    return {"name": req.name, **erosion}


@router.get("/report")
def se_report(company: str = Query(default="")):
    docs = list(_col().find({"company": company} if company else {}))
    enriched = []
    for d in docs:
        erosion = calculate_erosion(d["salary_ngn"], d["hired_date"])
        enriched.append({**d, **erosion})

    report_text = generate_erosion_report(company or "Company", enriched)
    return {"report_text": report_text, "staff_count": len(enriched)}
