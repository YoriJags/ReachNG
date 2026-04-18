"""
EstateOS API — AI-powered real estate vetting for Lagos agents.

Routes:
  GET  /estate/properties           — list properties
  POST /estate/properties           — add property listing
  GET  /estate/properties/{id}      — get property detail
  POST /estate/scorecard            — neighborhood scorecard (Google Maps)
  POST /estate/concierge/ask        — property concierge Q&A
  POST /estate/pof/assess           — proof of funds screener
  POST /estate/kyc/extract          — KYC document extraction
  GET  /estate/kyc                  — list KYC records
  POST /estate/background           — tenant background check
  GET  /estate/background           — list background checks
  POST /estate/lawyer-bundle        — generate lawyer handover memo
  GET  /estate/overview             — dashboard KPIs
"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
import base64, io, zipfile
from services.estate.engine import (
    get_neighborhood_scorecard, answer_property_question,
    assess_proof_of_funds, extract_kyc_data, extract_kyc_from_image,
    assess_tenant_background, generate_lawyer_bundle_summary,
)
from bson import ObjectId
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/estate", tags=["estate_os"])


def _col(name: str):
    return get_db()[name]

def _str_id(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


# ── Pydantic Models ────────────────────────────────────────────────────────────

class PropertyCreate(BaseModel):
    agent_company: str = ""
    address: str
    property_type: str = "residential"
    bedrooms: int = 0
    asking_price_ngn: float = 0
    title_type: str = ""
    description: str = ""
    amenities: str = ""
    contact_phone: str = ""


class ScorecardRequest(BaseModel):
    address: str
    property_type: str = "residential"


class ConciergeAsk(BaseModel):
    property_id: str
    question: str
    buyer_name: str = ""


class PofAssess(BaseModel):
    property_id: str = ""
    agent_company: str = ""
    property_price_ngn: float
    pof_description: str
    buyer_name: str = ""
    notes: str = ""


class KycExtract(BaseModel):
    property_id: str = ""
    party_name: str
    document_type: str
    document_text: str


class KycImageExtract(BaseModel):
    property_id: str = ""
    agent_company: str = ""
    party_name: str
    document_type: str
    image_base64: str
    media_type: str = "image/jpeg"


class BackgroundCheck(BaseModel):
    agent_company: str = ""
    tenant_name: str
    occupation: str = ""
    employer: str = ""
    monthly_income_ngn: float = 0
    rent_amount_ngn: float
    previous_landlord_feedback: str = ""
    guarantor_info: str = ""
    additional_notes: str = ""


class LawyerBundle(BaseModel):
    agent_company: str = ""
    property_address: str
    buyer_name: str
    seller_name: str
    agreed_price_ngn: float
    documents_collected: str = ""
    chat_summary: str = ""


# ── Overview ───────────────────────────────────────────────────────────────────

@router.get("/overview")
def estate_overview(agent_company: str = Query(default="")):
    scope = {"agent_company": agent_company} if agent_company else {}
    pof_scope = dict(scope, **{"verdict": "PROCEED"})
    return {
        "total_listings":     _col("estate_properties").count_documents(scope),
        "background_checks":  _col("estate_background_checks").count_documents(scope),
        "kyc_documents":      _col("estate_kyc_records").count_documents(scope),
        "pof_approved":       _col("estate_pof_assessments").count_documents(pof_scope),
        "agent_company":      agent_company,
    }


# ── Property Listings ──────────────────────────────────────────────────────────

@router.post("/properties", status_code=201)
def estate_add_property(req: PropertyCreate):
    doc = {**req.model_dump(), "scorecard": None, "created_at": datetime.now(timezone.utc)}
    inserted = _col("estate_properties").insert_one(doc)
    return {"property_id": str(inserted.inserted_id), "address": req.address}


@router.get("/properties")
def estate_list_properties(agent_company: str = Query(default="")):
    q = {"agent_company": agent_company} if agent_company else {}
    docs = list(_col("estate_properties").find(q).sort("created_at", -1).limit(100))
    return {"properties": [_str_id(d) for d in docs]}


@router.get("/properties/{property_id}")
def estate_get_property(property_id: str):
    doc = _col("estate_properties").find_one({"_id": ObjectId(property_id)})
    if not doc:
        return {"error": "Property not found"}
    return _str_id(doc)


# ── Neighborhood Scorecard ─────────────────────────────────────────────────────

@router.post("/scorecard")
def estate_scorecard(req: ScorecardRequest):
    result = get_neighborhood_scorecard(req.address, req.property_type)
    _col("estate_scorecards").insert_one({**result, "created_at": datetime.now(timezone.utc)})
    return result


# ── Property Concierge ─────────────────────────────────────────────────────────

@router.post("/concierge/ask")
def estate_concierge_ask(req: ConciergeAsk):
    prop = _col("estate_properties").find_one({"_id": ObjectId(req.property_id)}) if req.property_id else None
    if not prop:
        return {"answer": "Property not found. Please provide a valid property ID."}
    docs_text = f"""Address: {prop.get('address')}
Type: {prop.get('property_type')} | Bedrooms: {prop.get('bedrooms')} | Price: ₦{prop.get('asking_price_ngn', 0):,.0f}
Title: {prop.get('title_type')} | Description: {prop.get('description')}
Amenities: {prop.get('amenities')}"""
    answer = answer_property_question(docs_text, req.question)
    _col("estate_concierge_log").insert_one({
        "property_id": req.property_id, "buyer_name": req.buyer_name,
        "question": req.question, "answer": answer,
        "created_at": datetime.now(timezone.utc),
    })
    return {"answer": answer, "property_address": prop.get("address")}


# ── Proof of Funds ─────────────────────────────────────────────────────────────

@router.post("/pof/assess", status_code=201)
def estate_pof_assess(req: PofAssess):
    result = assess_proof_of_funds(req.property_price_ngn, req.pof_description, req.notes)
    doc = {**req.model_dump(), **result, "created_at": datetime.now(timezone.utc)}
    inserted = _col("estate_pof_assessments").insert_one(doc)
    return {**result, "assessment_id": str(inserted.inserted_id)}


@router.get("/pof")
def estate_pof_list(agent_company: str = Query(default="")):
    q = {"agent_company": agent_company} if agent_company else {}
    docs = list(_col("estate_pof_assessments").find(q).sort("created_at", -1).limit(50))
    return {"assessments": [_str_id(d) for d in docs]}


# ── KYC Vault ─────────────────────────────────────────────────────────────────

@router.post("/kyc/extract", status_code=201)
def estate_kyc_extract(req: KycExtract):
    extracted = extract_kyc_data(req.document_type, req.document_text)
    doc = {
        "property_id": req.property_id,
        "party_name": req.party_name,
        "document_type": req.document_type,
        "extracted_data": extracted,
        "created_at": datetime.now(timezone.utc),
    }
    inserted = _col("estate_kyc_records").insert_one(doc)
    return {"kyc_id": str(inserted.inserted_id), "extracted": extracted, "party_name": req.party_name}


@router.post("/kyc/extract-image", status_code=201)
def estate_kyc_extract_image(req: KycImageExtract):
    extracted = extract_kyc_from_image(req.document_type, req.image_base64, req.media_type)
    doc = {
        "property_id": req.property_id,
        "agent_company": req.agent_company,
        "party_name": req.party_name,
        "document_type": req.document_type,
        "source": "vision",
        "extracted_data": extracted,
        "created_at": datetime.now(timezone.utc),
    }
    inserted = _col("estate_kyc_records").insert_one(doc)
    return {"kyc_id": str(inserted.inserted_id), "extracted": extracted, "party_name": req.party_name}


@router.get("/kyc")
def estate_kyc_list(property_id: str = Query(default=""), agent_company: str = Query(default="")):
    q = {}
    if property_id:
        q["property_id"] = property_id
    if agent_company:
        q["agent_company"] = agent_company
    docs = list(_col("estate_kyc_records").find(q).sort("created_at", -1).limit(100))
    return {"records": [_str_id(d) for d in docs]}


# ── Tenant Background Check ────────────────────────────────────────────────────

@router.post("/background", status_code=201)
def estate_background_check(req: BackgroundCheck):
    result = assess_tenant_background(
        req.tenant_name, req.occupation, req.employer,
        req.monthly_income_ngn, req.rent_amount_ngn,
        req.previous_landlord_feedback, req.guarantor_info, req.additional_notes,
    )
    doc = {**req.model_dump(), **result, "created_at": datetime.now(timezone.utc)}
    inserted = _col("estate_background_checks").insert_one(doc)
    return {**result, "check_id": str(inserted.inserted_id)}


@router.get("/background")
def estate_background_list(agent_company: str = Query(default="")):
    q = {"agent_company": agent_company} if agent_company else {}
    docs = list(_col("estate_background_checks").find(q).sort("created_at", -1).limit(50))
    return {"checks": [_str_id(d) for d in docs]}


# ── Lawyer Bundle ──────────────────────────────────────────────────────────────

@router.post("/lawyer-bundle", status_code=201)
def estate_lawyer_bundle(req: LawyerBundle):
    memo = generate_lawyer_bundle_summary(
        req.property_address, req.buyer_name, req.seller_name,
        req.agreed_price_ngn, req.documents_collected, req.chat_summary,
    )
    doc = {**req.model_dump(), "memo": memo, "created_at": datetime.now(timezone.utc)}
    inserted = _col("estate_lawyer_bundles").insert_one(doc)
    return {"bundle_id": str(inserted.inserted_id), "memo": memo, "property_address": req.property_address}


@router.get("/lawyer-bundle")
def estate_lawyer_bundle_list(agent_company: str = Query(default="")):
    q = {"agent_company": agent_company} if agent_company else {}
    docs = list(_col("estate_lawyer_bundles").find(q, {"attachments.data": 0}).sort("created_at", -1).limit(50))
    return {"bundles": [_str_id(d) for d in docs]}


class BundleAttachment(BaseModel):
    bundle_id: str
    filename: str
    content_base64: str
    media_type: str = "application/octet-stream"


@router.post("/lawyer-bundle/attach", status_code=201)
def estate_lawyer_bundle_attach(req: BundleAttachment):
    attachment = {
        "filename":     req.filename,
        "media_type":   req.media_type,
        "data":         req.content_base64,
        "uploaded_at":  datetime.now(timezone.utc),
    }
    result = _col("estate_lawyer_bundles").update_one(
        {"_id": ObjectId(req.bundle_id)},
        {"$push": {"attachments": attachment}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Bundle not found")
    return {"bundle_id": req.bundle_id, "filename": req.filename, "status": "attached"}


@router.get("/lawyer-bundle/{bundle_id}/zip")
def estate_lawyer_bundle_zip(bundle_id: str):
    bundle = _col("estate_lawyer_bundles").find_one({"_id": ObjectId(bundle_id)})
    if not bundle:
        raise HTTPException(404, "Bundle not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        memo_text = (
            f"LAWYER HANDOVER MEMO\n"
            f"Property: {bundle.get('property_address', '')}\n"
            f"Buyer: {bundle.get('buyer_name', '')}\n"
            f"Seller: {bundle.get('seller_name', '')}\n"
            f"Agreed Price: NGN {bundle.get('agreed_price_ngn', 0):,.0f}\n"
            f"Generated: {bundle.get('created_at', '').isoformat() if hasattr(bundle.get('created_at', ''), 'isoformat') else bundle.get('created_at', '')}\n\n"
            f"{bundle.get('memo', '')}\n"
        )
        zf.writestr("00_handover_memo.txt", memo_text)
        for i, att in enumerate(bundle.get("attachments", []), 1):
            try:
                data = base64.b64decode(att["data"])
                zf.writestr(f"{i:02d}_{att['filename']}", data)
            except Exception:
                continue

    buf.seek(0)
    address_slug = (bundle.get("property_address") or "bundle").replace(" ", "_").replace(",", "")[:40]
    filename = f"lawyer_bundle_{address_slug}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
