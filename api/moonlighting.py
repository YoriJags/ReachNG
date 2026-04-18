"""
Staff Moonlighting Detector API.

Routes:
  GET  /moonlighting/overview    — KPI summary
  POST /moonlighting/analyse     — analyse attendance log for moonlighting signals
  GET  /moonlighting/flagged     — list flagged staff records
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.moonlighting.engine import analyse_attendance
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/moonlighting", tags=["moonlighting"])

COLLECTION = "moonlighting_analyses"


def _col():
    return get_db()[COLLECTION]


class AnalyseRequest(BaseModel):
    company: str = ""
    staff_name: str
    role: str
    attendance_log: str


@router.get("/overview")
def ml_overview():
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    all_docs = list(_col().find())
    this_month = [d for d in all_docs if d.get("created_at", now) >= month_start]
    flagged_this_month = sum(1 for d in this_month if d.get("flag_for_review"))
    confirmed = sum(1 for d in all_docs if d.get("confirmed_moonlighting"))
    return {
        "total_staff":          len(all_docs),
        "flagged_this_month":   flagged_this_month,
        "confirmed_cases":      confirmed,
    }


@router.post("/analyse", status_code=201)
def ml_analyse(req: AnalyseRequest):
    result = analyse_attendance(
        company=req.company,
        staff_name=req.staff_name,
        role=req.role,
        attendance_log=req.attendance_log,
    )
    doc = {
        **req.model_dump(),
        **result,
        "confirmed_moonlighting": False,
        "created_at": datetime.now(timezone.utc),
    }
    _col().update_one(
        {"staff_name": req.staff_name, "company": req.company},
        {"$set": doc},
        upsert=True,
    )
    return result


@router.get("/flagged")
def ml_flagged():
    docs = list(_col().find({"flag_for_review": True}).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"flagged": docs}
