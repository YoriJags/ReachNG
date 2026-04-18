"""
Market Woman Credit Profiler API.

Routes:
  GET  /market-credit/applications  — list scored applications
  POST /market-credit/apply         — score a new trader application
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.market_credit.engine import score_trader
from bson import ObjectId
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/market-credit", tags=["market_credit"])

COLLECTION = "market_credit_applications"


def _col():
    return get_db()[COLLECTION]


class TraderApplication(BaseModel):
    mfb: str = "MFB"
    trader_name: str
    market: str
    goods_type: str
    years_trading: int = 0
    daily_sales_ngn: float = 0
    association_membership: str = ""
    peer_references: str = ""
    phone: str = ""
    loan_amount_ngn: float = 0
    loan_purpose: str = "Working capital / stock finance"


@router.get("/applications")
def mc_applications():
    docs = list(_col().find().sort("created_at", -1).limit(100))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"applications": docs}


@router.post("/apply", status_code=201)
def mc_apply(req: TraderApplication):
    result = score_trader(req.model_dump())
    doc = {
        **req.model_dump(),
        **result,
        "created_at": datetime.now(timezone.utc),
    }
    inserted = _col().insert_one(doc)
    result["_id"] = str(inserted.inserted_id)
    return result
