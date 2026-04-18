"""
FX Rate Invoice Lock API.

Routes:
  GET  /fx-lock/rate          — current USD/NGN rate + 24h change + quote count
  POST /fx-lock/quotes        — lock a quote at current rate
  GET  /fx-lock/quotes        — list locked quotes
  POST /fx-lock/settings      — save alert settings for a client
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.fx_lock.engine import fetch_current_rate, calculate_quote_ngn
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/fx-lock", tags=["fx_lock"])

QUOTES_COL   = "fx_lock_quotes"
SETTINGS_COL = "fx_lock_settings"
HISTORY_COL  = "fx_lock_rate_history"


def _quotes():   return get_db()[QUOTES_COL]
def _settings(): return get_db()[SETTINGS_COL]
def _history():  return get_db()[HISTORY_COL]


class QuoteRequest(BaseModel):
    client_name: str
    description: str
    usd_value: float
    alert_threshold_pct: float = 3.0
    expiry_date: str = ""


class SettingsRequest(BaseModel):
    client_name: str
    phone: str = ""
    threshold_pct: float = 3.0


@router.get("/rate")
async def fxl_rate():
    rate_data = await fetch_current_rate()

    # Store in history
    today = datetime.now(timezone.utc).date().isoformat()
    _history().update_one(
        {"date": today},
        {"$set": {"rate": rate_data["usd_ngn_parallel"], "date": today}},
        upsert=True,
    )

    # Build history for last 7 days
    history_docs = list(_history().find().sort("date", -1).limit(8))
    history = []
    for i, h in enumerate(history_docs):
        prev_rate = history_docs[i + 1]["rate"] if i + 1 < len(history_docs) else h["rate"]
        change = ((h["rate"] - prev_rate) / prev_rate * 100) if prev_rate else 0
        history.append({"date": h["date"], "rate": h["rate"], "change": round(change, 2)})

    # 24h change
    change_24h = history[0]["change"] if history else 0

    # Quotes locked today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    quotes_today = _quotes().count_documents({"locked_at": {"$gte": today_start}})

    return {
        **rate_data,
        "change_24h_pct":   change_24h,
        "quotes_locked_today": quotes_today,
        "history":          history,
    }


@router.post("/quotes", status_code=201)
async def fxl_lock_quote(req: QuoteRequest):
    rate_data = await fetch_current_rate()
    locked_rate = rate_data["usd_ngn_parallel"]
    ngn_value   = calculate_quote_ngn(req.usd_value, locked_rate)

    doc = {
        **req.model_dump(),
        "locked_rate":  locked_rate,
        "ngn_value":    ngn_value,
        "locked_at":    datetime.now(timezone.utc),
        "status":       "active",
    }
    _quotes().insert_one(doc)
    return {"locked_rate": locked_rate, "ngn_value": ngn_value, "status": "locked"}


@router.get("/quotes")
def fxl_quotes():
    docs = list(_quotes().find().sort("locked_at", -1).limit(100))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"quotes": docs}


@router.post("/settings")
def fxl_settings(req: SettingsRequest):
    _settings().update_one(
        {"client_name": req.client_name},
        {"$set": {**req.model_dump(), "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"status": "saved", "client_name": req.client_name}
