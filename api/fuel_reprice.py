"""
Fuel Cost Repricing Alert API.

Routes:
  GET  /fuel-reprice/routes                  — list all routes with current economics
  POST /fuel-reprice/routes                  — add a new route
  POST /fuel-reprice/routes/{id}/letter      — generate repricing letter
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.fuel_reprice.engine import calculate_route_economics, generate_repricing_letter
from bson import ObjectId
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/fuel-reprice", tags=["fuel_reprice"])

COLLECTION = "fuel_routes"


def _col():
    return get_db()[COLLECTION]


class RouteRequest(BaseModel):
    company: str = ""
    route_name: str
    client_name: str
    agreed_rate_ngn: float
    distance_km: float
    litres_per_100km: float = 35.0
    contract_date: str = ""
    fuel_price_at_signing: float = 1_050.0


@router.get("/routes")
def fr_routes():
    docs = list(_col().find().sort("created_at", -1).limit(200))
    from services.fuel_reprice.engine import DEFAULT_PUMP_PRICE
    pump_price = DEFAULT_PUMP_PRICE

    loss_making = 0
    letters = 0
    enriched = []
    for d in docs:
        d["_id"] = str(d["_id"])
        econ = calculate_route_economics(d, pump_price)
        d["margin_ngn"]             = econ["margin_ngn"]
        d["cost_at_current_fuel"]   = econ["total_cost_now"]
        d["agreed_rate"]            = econ["agreed_rate_ngn"]
        d["is_loss_making"]         = econ["is_loss_making"]
        if econ["is_loss_making"]:
            loss_making += 1
        if d.get("letter_generated"):
            letters += 1
        enriched.append(d)

    return {
        "pump_price_per_litre": pump_price,
        "loss_making_count": loss_making,
        "letters_generated": letters,
        "routes": enriched,
    }


@router.post("/routes", status_code=201)
def fr_add_route(req: RouteRequest):
    from services.fuel_reprice.engine import DEFAULT_PUMP_PRICE
    doc = {**req.model_dump(), "letter_generated": False, "created_at": datetime.now(timezone.utc)}
    econ = calculate_route_economics(doc, DEFAULT_PUMP_PRICE)
    doc["economics_snapshot"] = econ
    inserted = _col().insert_one(doc)
    result = {**econ, "_id": str(inserted.inserted_id)}
    return result


@router.post("/routes/{route_id}/letter")
def fr_generate_letter(route_id: str):
    route = _col().find_one({"_id": ObjectId(route_id)})
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    from services.fuel_reprice.engine import DEFAULT_PUMP_PRICE
    econ   = calculate_route_economics(route, DEFAULT_PUMP_PRICE)
    letter = generate_repricing_letter(route, econ, company_name=route.get("company", "Our Company"))

    _col().update_one(
        {"_id": ObjectId(route_id)},
        {"$set": {"letter_generated": True, "last_letter_at": datetime.now(timezone.utc)}},
    )
    return {"letter_text": letter, "economics": econ}
