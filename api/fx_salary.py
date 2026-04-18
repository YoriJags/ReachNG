"""
FX Arbitrage Salary Parity API.

Routes:
  GET  /fx-salary/dashboard   — KPIs + staff list with this month's naira equivalent
  POST /fx-salary/staff       — add a USD-salary staff member
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.fx_salary.engine import calculate_parity
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/fx-salary", tags=["fx_salary"])

COLLECTION = "fx_salary_staff"


def _col():
    return get_db()[COLLECTION]


class StaffRecord(BaseModel):
    company: str = ""
    name: str
    role: str
    salary_usd: float
    phone: str = ""


@router.get("/dashboard")
async def fxs_dashboard():
    docs = list(_col().find().sort("name", 1))
    for d in docs:
        d["_id"] = str(d["_id"])
        d["last_month_ngn"] = d.get("last_month_ngn")

    result = await calculate_parity(docs)
    # Persist updated last_month_ngn for next month diff
    rate = result["usd_ngn_rate"]
    for s in result["staff"]:
        _col().update_one(
            {"name": s["name"], "company": s.get("company", "")},
            {"$set": {"last_month_ngn": s["this_month_ngn"]}},
        )
    return result


@router.post("/staff", status_code=201)
async def fxs_add_staff(req: StaffRecord):
    doc = {**req.model_dump(), "created_at": datetime.now(timezone.utc)}
    _col().update_one(
        {"name": req.name, "company": req.company},
        {"$set": doc},
        upsert=True,
    )
    return {"name": req.name, "status": "added"}
