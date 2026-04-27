"""
EstateOS Client Portal — token-gated API + page for estate agent clients.
All routes validate the portal token; no Basic Auth required on the client side.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from bson import ObjectId
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/portal/estate", tags=["portal_estate"])


def _get_client(token: str) -> dict:
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(403, "Invalid or expired portal token")
    return client


def _str(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    for k, v in doc.items():
        if hasattr(v, "isoformat"):
            doc[k] = v.isoformat()
    return doc


# ── Page ──────────────────────────────────────────────────────────────────────

@router.get("/{token}", response_class=HTMLResponse)
async def estate_portal_page(token: str, request: Request):
    client = _get_client(token)
    return request.app.state.templates.TemplateResponse(
        request, "portal_estate.html",
        {
            "token": token,
            "client_name": client["name"],
            "company": client.get("company", client["name"]),
            "vertical": client.get("vertical", "real_estate"),
        },
    )


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/{token}/overview")
def estate_portal_overview(token: str):
    client = _get_client(token)
    db = get_db()
    company = client.get("company", client["name"])
    return {
        "total_listings": db["estate_properties"].count_documents({"agent_company": company}),
        "background_checks": db["estate_background_checks"].count_documents({"agent_company": company}),
        "kyc_documents": db["estate_kyc_records"].count_documents({}),
        "pof_approved": db["estate_pof_assessments"].count_documents({"verdict": "PROCEED"}),
        "company": company,
    }


# ── Properties ────────────────────────────────────────────────────────────────

class _PropertyReq(BaseModel):
    address: str
    property_type: str = "residential"
    bedrooms: int = 0
    asking_price_ngn: float = 0
    title_type: str = ""
    description: str = ""
    amenities: str = ""
    contact_phone: str = ""


@router.get("/{token}/properties")
def estate_portal_list_properties(token: str):
    client = _get_client(token)
    company = client.get("company", client["name"])
    docs = list(get_db()["estate_properties"].find({"agent_company": company}).sort("created_at", -1).limit(100))
    return {"properties": [_str(d) for d in docs]}


@router.post("/{token}/properties", status_code=201)
def estate_portal_add_property(token: str, req: _PropertyReq):
    client = _get_client(token)
    company = client.get("company", client["name"])
    doc = {**req.model_dump(), "agent_company": company, "scorecard": None, "created_at": datetime.now(timezone.utc)}
    inserted = get_db()["estate_properties"].insert_one(doc)
    return {"property_id": str(inserted.inserted_id), "address": req.address}


# ── Scorecard ─────────────────────────────────────────────────────────────────

class _ScorecardReq(BaseModel):
    address: str
    property_type: str = "residential"


@router.post("/{token}/scorecard")
def estate_portal_scorecard(token: str, req: _ScorecardReq):
    _get_client(token)
    from services.estate.engine import get_neighborhood_scorecard
    result = get_neighborhood_scorecard(req.address, req.property_type)
    get_db()["estate_scorecards"].insert_one({**result, "created_at": datetime.now(timezone.utc)})
    return result


# ── Concierge ─────────────────────────────────────────────────────────────────

class _ConciergeReq(BaseModel):
    property_id: str
    question: str
    buyer_name: str = ""


@router.post("/{token}/concierge")
def estate_portal_concierge(token: str, req: _ConciergeReq):
    _get_client(token)
    db = get_db()
    prop = db["estate_properties"].find_one({"_id": ObjectId(req.property_id)})
    if not prop:
        return {"answer": "Property not found. Please check the listing ID."}
    docs_text = (
        f"Address: {prop.get('address')}\n"
        f"Type: {prop.get('property_type')} | Bedrooms: {prop.get('bedrooms')} | "
        f"Price: \u20a6{prop.get('asking_price_ngn', 0):,.0f}\n"
        f"Title: {prop.get('title_type')} | Description: {prop.get('description')}\n"
        f"Amenities: {prop.get('amenities')}"
    )
    from services.estate.engine import answer_property_question
    answer = answer_property_question(docs_text, req.question)
    db["estate_concierge_log"].insert_one({
        "property_id": req.property_id, "buyer_name": req.buyer_name,
        "question": req.question, "answer": answer,
        "created_at": datetime.now(timezone.utc),
    })
    return {"answer": answer, "property_address": prop.get("address")}


# ── Proof of Funds ─────────────────────────────────────────────────────────────

class _PofReq(BaseModel):
    property_price_ngn: float
    pof_description: str
    buyer_name: str = ""
    notes: str = ""


@router.get("/{token}/pof")
def estate_portal_pof_list(token: str):
    _get_client(token)
    docs = list(get_db()["estate_pof_assessments"].find().sort("created_at", -1).limit(50))
    return {"assessments": [_str(d) for d in docs]}


@router.post("/{token}/pof", status_code=201)
def estate_portal_pof(token: str, req: _PofReq):
    _get_client(token)
    from services.estate.engine import assess_proof_of_funds
    result = assess_proof_of_funds(req.property_price_ngn, req.pof_description, req.notes)
    doc = {**req.model_dump(), **result, "created_at": datetime.now(timezone.utc)}
    inserted = get_db()["estate_pof_assessments"].insert_one(doc)
    return {**result, "assessment_id": str(inserted.inserted_id)}


# ── KYC Vault ─────────────────────────────────────────────────────────────────

class _KycReq(BaseModel):
    party_name: str
    document_type: str
    document_text: str
    property_id: str = ""


@router.get("/{token}/kyc")
def estate_portal_kyc_list(token: str):
    _get_client(token)
    docs = list(get_db()["estate_kyc_records"].find().sort("created_at", -1).limit(100))
    return {"records": [_str(d) for d in docs]}


@router.post("/{token}/kyc", status_code=201)
def estate_portal_kyc(token: str, req: _KycReq):
    _get_client(token)
    from services.estate.engine import extract_kyc_data
    extracted = extract_kyc_data(req.document_type, req.document_text)
    doc = {
        "property_id": req.property_id, "party_name": req.party_name,
        "document_type": req.document_type, "extracted_data": extracted,
        "created_at": datetime.now(timezone.utc),
    }
    inserted = get_db()["estate_kyc_records"].insert_one(doc)
    return {"kyc_id": str(inserted.inserted_id), "extracted": extracted, "party_name": req.party_name}


# ── Background Check ──────────────────────────────────────────────────────────

class _BgReq(BaseModel):
    tenant_name: str
    occupation: str = ""
    employer: str = ""
    monthly_income_ngn: float = 0
    rent_amount_ngn: float
    previous_landlord_feedback: str = ""
    guarantor_info: str = ""
    additional_notes: str = ""


@router.get("/{token}/background")
def estate_portal_bg_list(token: str):
    client = _get_client(token)
    company = client.get("company", client["name"])
    docs = list(get_db()["estate_background_checks"].find({"agent_company": company}).sort("created_at", -1).limit(50))
    return {"checks": [_str(d) for d in docs]}


@router.post("/{token}/background", status_code=201)
def estate_portal_bg(token: str, req: _BgReq):
    client = _get_client(token)
    company = client.get("company", client["name"])
    from services.estate.engine import assess_tenant_background
    result = assess_tenant_background(
        req.tenant_name, req.occupation, req.employer,
        req.monthly_income_ngn, req.rent_amount_ngn,
        req.previous_landlord_feedback, req.guarantor_info, req.additional_notes,
    )
    doc = {**req.model_dump(), **result, "agent_company": company, "created_at": datetime.now(timezone.utc)}
    inserted = get_db()["estate_background_checks"].insert_one(doc)
    return {**result, "check_id": str(inserted.inserted_id)}


# ── Lawyer Bundle ─────────────────────────────────────────────────────────────

class _LawyerReq(BaseModel):
    property_address: str
    buyer_name: str
    seller_name: str
    agreed_price_ngn: float
    documents_collected: str = ""
    chat_summary: str = ""


@router.get("/{token}/lawyer-bundle")
def estate_portal_lawyer_list(token: str):
    _get_client(token)
    docs = list(get_db()["estate_lawyer_bundles"].find().sort("created_at", -1).limit(50))
    return {"bundles": [_str(d) for d in docs]}


@router.post("/{token}/lawyer-bundle", status_code=201)
def estate_portal_lawyer(token: str, req: _LawyerReq):
    _get_client(token)
    from services.estate.engine import generate_lawyer_bundle_summary
    memo = generate_lawyer_bundle_summary(
        req.property_address, req.buyer_name, req.seller_name,
        req.agreed_price_ngn, req.documents_collected, req.chat_summary,
    )
    doc = {**req.model_dump(), "memo": memo, "created_at": datetime.now(timezone.utc)}
    inserted = get_db()["estate_lawyer_bundles"].insert_one(doc)
    return {"bundle_id": str(inserted.inserted_id), "memo": memo, "property_address": req.property_address}


# ── Rent Roll (read-only for landlord) ────────────────────────────────────────

@router.get("/{token}/rent")
def estate_portal_rent(token: str):
    """Landlord-scoped rent roll: units, occupancy, collected, overdue ledger.

    Scope: unit.landlord_company == client.name (or client.company).
    Read-only — write ops stay in admin dashboard.
    """
    client = _get_client(token)
    landlord_company = client.get("company") or client["name"]

    from services.estate.rent_roll import (
        list_units, list_tenants, get_overdue_charges,
    )

    db = get_db()
    units = list_units(landlord_company)
    unit_ids = [u["_id"] for u in units]

    occupied = db["estate_tenants"].count_documents(
        {"unit_id": {"$in": unit_ids}, "status": "active"}
    )

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    collected = sum(
        c.get("paid_amount", 0) or c.get("amount_ngn", 0)
        for c in db["estate_rent_ledger"].find({
            "unit_id": {"$in": unit_ids},
            "status":  "paid",
            "paid_at": {"$gte": month_start},
        })
    )

    overdue = get_overdue_charges(landlord_company)
    outstanding = sum(c["amount_ngn"] for c in overdue)

    for c in overdue:
        for k in ("due_date", "last_chased_at", "created_at"):
            v = c.get(k)
            if hasattr(v, "isoformat"):
                c[k] = v.isoformat()

    return {
        "landlord":             landlord_company,
        "total_units":          len(units),
        "occupied":             occupied,
        "vacancy_rate":         round((len(units) - occupied) / len(units) * 100, 1) if units else 0,
        "collected_this_month": round(collected, 2),
        "outstanding_overdue":  round(outstanding, 2),
        "overdue_count":        len(overdue),
        "units":                units,
        "overdue":              overdue,
    }
