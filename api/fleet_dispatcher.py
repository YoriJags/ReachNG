"""
Fleet Digital Dispatcher — the 10-second breakdown response system.

Endpoints:
  GET  /fleet/trucks                    — list registered trucks
  POST /fleet/trucks                    — register a truck
  POST /fleet/incidents                 — log + analyse a breakdown
  GET  /fleet/incidents                 — list incidents (all or by status)
  PATCH /fleet/incidents/{id}/approve   — owner approves the transfer
  PATCH /fleet/incidents/{id}/resolve   — mark incident resolved
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.fleet_dispatcher import store, engine

router = APIRouter(prefix="/fleet", tags=["fleet_dispatcher"])


class TruckCreate(BaseModel):
    plate: str
    driver_name: str
    make: str = ""
    model: str = ""
    current_km: int = 0
    client_name: str = ""


class BreakdownReport(BaseModel):
    truck_plate: str
    driver_name: str
    location: str
    message: str
    amount_requested_ngn: int


class ApproveBody(BaseModel):
    amount_ngn: int


class ResolveBody(BaseModel):
    note: str = ""


@router.get("/trucks")
def list_trucks():
    return {"trucks": store.list_trucks()}


@router.post("/trucks", status_code=201)
def register_truck(body: TruckCreate):
    truck_id = store.upsert_truck(
        plate=body.plate,
        driver_name=body.driver_name,
        make=body.make,
        model=body.model,
        current_km=body.current_km,
        client_name=body.client_name,
    )
    return {"truck_id": truck_id, "plate": body.plate.upper()}


@router.post("/incidents", status_code=201)
def log_breakdown(body: BreakdownReport):
    """
    Log a breakdown report. Claude analyses it in < 3 seconds and returns:
    - legitimacy assessment
    - recommended approval amount
    - draft WhatsApp messages (to driver + to client)
    Owner reviews and taps approve or reject.
    """
    history = store.get_truck_incident_history(body.truck_plate)

    assessment = engine.analyse_breakdown(
        raw_message=body.message,
        truck_plate=body.truck_plate,
        driver_name=body.driver_name,
        location=body.location,
        amount_requested_ngn=body.amount_requested_ngn,
        incident_history=history,
    )

    incident_id = store.create_incident(
        truck_plate=body.truck_plate,
        driver_name=body.driver_name,
        location=body.location,
        raw_message=body.message,
        amount_requested_ngn=body.amount_requested_ngn,
        claude_assessment=assessment,
    )

    return {
        "incident_id":    incident_id,
        "assessment":     assessment,
        "truck_plate":    body.truck_plate.upper(),
        "driver_name":    body.driver_name,
    }


@router.get("/incidents")
def list_incidents(status: Optional[str] = None):
    return {"incidents": store.list_incidents(status=status)}


@router.patch("/incidents/{incident_id}/approve")
def approve_incident(incident_id: str, body: ApproveBody):
    result = store.approve_incident(incident_id, body.amount_ngn)
    if not result:
        raise HTTPException(404, "Incident not found")
    return {"success": True, "incident": result}


@router.patch("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str, body: ResolveBody):
    result = store.resolve_incident(incident_id, body.note)
    if not result:
        raise HTTPException(404, "Incident not found")
    return {"success": True, "incident": result}
