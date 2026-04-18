"""
Construction Material Adulteration Checker API.

Routes:
  GET  /material-check/results                  — list past checks
  POST /material-check/check                    — run new check
  POST /material-check/{check_id}/blacklist     — flag supplier as blacklisted
  GET  /material-check/blacklist                — list blacklisted suppliers
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.material_check.engine import check_material
from bson import ObjectId
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/material-check", tags=["material_check"])

CHECKS_COL   = "material_checks"
BLACKLIST_COL = "material_supplier_blacklist"


def _checks():
    return get_db()[CHECKS_COL]


def _blacklist():
    return get_db()[BLACKLIST_COL]


class CheckRequest(BaseModel):
    company: str = ""
    material: str
    supplier: str
    supplier_location: str = ""
    quantity: str = ""
    price_per_unit: float = 0
    stated_spec: str = ""
    observations: str


@router.get("/results")
def mch_results():
    docs = list(_checks().find().sort("created_at", -1).limit(200))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"checks": docs}


@router.post("/check", status_code=201)
def mch_check(req: CheckRequest):
    result = check_material(req.model_dump())
    doc = {
        **req.model_dump(),
        **result,
        "created_at": datetime.now(timezone.utc),
    }
    inserted = _checks().insert_one(doc)
    result["_id"] = str(inserted.inserted_id)
    return result


@router.post("/{check_id}/blacklist")
def mch_blacklist(check_id: str):
    check = _checks().find_one({"_id": ObjectId(check_id)})
    if not check:
        return {"error": "Check not found"}
    supplier = check.get("supplier", "Unknown")
    _blacklist().update_one(
        {"supplier": supplier},
        {"$set": {"supplier": supplier, "blacklisted_at": datetime.now(timezone.utc),
                  "material": check.get("material"), "reason": check.get("verdict")}},
        upsert=True,
    )
    return {"supplier": supplier, "status": "blacklisted"}


@router.get("/blacklist")
def mch_get_blacklist():
    docs = list(_blacklist().find().sort("blacklisted_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"blacklisted": docs}
