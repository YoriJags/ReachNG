"""
MarketOS API — commodity price intelligence for Lagos traders.

Endpoints:
  GET  /market/prices              — latest prices per commodity+market
  POST /market/prices              — record a new price entry
  GET  /market/prices/{commodity}  — history for one commodity
  GET  /market/briefing            — generate daily WhatsApp briefing
  GET  /market/alerts/check        — check all alert thresholds
  POST /market/alerts              — create a price alert for a trader
  GET  /market/commodities         — list supported commodities + markets
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.market_os.engine import (
    record_price, get_latest_prices, get_price_history,
    generate_daily_briefing, check_buy_alerts, upsert_alert,
    COMMODITIES, MARKETS,
)

router = APIRouter(prefix="/market", tags=["market_os"])


class PriceEntry(BaseModel):
    commodity: str
    market: str
    price_ngn: float
    unit: str = "kg"
    source: str = "manual"


class AlertCreate(BaseModel):
    trader_name: str
    phone: str
    commodity: str
    threshold_ngn: float
    direction: str = "below"   # "below" = buy alert, "above" = avoid/sell alert
    market: str = "any"
    unit: str = "kg"


class BriefingRequest(BaseModel):
    trader_name: str
    commodities: list[str]


@router.get("/commodities")
def list_commodities():
    return {"commodities": COMMODITIES, "markets": MARKETS}


@router.get("/prices")
def latest_prices(commodity: Optional[str] = None):
    return {"prices": get_latest_prices(commodity=commodity)}


@router.post("/prices", status_code=201)
def add_price(body: PriceEntry):
    price_id = record_price(
        commodity=body.commodity,
        market=body.market,
        price_ngn=body.price_ngn,
        unit=body.unit,
        source=body.source,
    )
    return {"price_id": price_id, "recorded": True}


@router.get("/prices/{commodity}")
def commodity_history(commodity: str, market: str = "mile_12", days: int = 7):
    return {"history": get_price_history(commodity=commodity, market=market, days=days)}


@router.post("/briefing")
def daily_briefing(body: BriefingRequest):
    text = generate_daily_briefing(
        trader_name=body.trader_name,
        commodities_watched=body.commodities,
    )
    return {"briefing": text}


@router.get("/alerts/check")
def check_alerts():
    triggered = check_buy_alerts()
    return {"triggered": triggered, "count": len(triggered)}


@router.post("/alerts", status_code=201)
def create_alert(body: AlertCreate):
    alert_id = upsert_alert(
        trader_name=body.trader_name,
        phone=body.phone,
        commodity=body.commodity,
        threshold_ngn=body.threshold_ngn,
        direction=body.direction,
        market=body.market,
        unit=body.unit,
    )
    return {"alert_id": alert_id, "created": True}
