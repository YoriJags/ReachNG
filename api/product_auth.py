"""
Fake Product Authentication Scanner API.

Routes:
  GET  /product-auth/history          — list past scans
  POST /product-auth/scan             — run authentication check
  GET  /product-auth/flagged          — scans with COUNTERFEIT/SUSPECTED_FAKE verdict
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.product_auth.engine import authenticate_product
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/product-auth", tags=["product_auth"])

COLLECTION = "product_auth_scans"


def _col():
    return get_db()[COLLECTION]


class ScanRequest(BaseModel):
    business: str = ""
    product_name: str
    brand: str
    nafdac_number: str = ""
    batch_number: str = ""
    supplier: str
    description: str


@router.get("/history")
def pa_history():
    docs = list(_col().find().sort("created_at", -1).limit(200))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"scans": docs}


@router.get("/flagged")
def pa_flagged():
    docs = list(_col().find({"verdict": {"$in": ["COUNTERFEIT", "SUSPECTED_FAKE"]}}).sort("created_at", -1).limit(100))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"flagged": docs}


@router.post("/scan", status_code=201)
def pa_scan(req: ScanRequest):
    result = authenticate_product(req.model_dump())
    doc = {
        **req.model_dump(),
        **result,
        "created_at": datetime.now(timezone.utc),
    }
    _col().insert_one(doc)
    return result
