"""
EstateOS Engine — AI-powered real estate vetting for Lagos agents.

Features:
  1. Neighborhood Scorecard  — Google Maps: flood risk proxy, commute to VI/Ikoyi at peak
  2. Property Concierge      — Claude reads property docs, answers buyer FAQs
  3. Proof of Funds Screener — Claude assesses bank statement / asset proof
  4. KYC Vault               — Extracts NIN / passport / utility bill data via Claude
  5. Tenant Background Check — Risk assessment from provided info
  6. Lawyer Bundle           — Packages deal documents for closing attorney
"""
import anthropic
import httpx
from config import get_settings
import structlog

log = structlog.get_logger()


def _claude(prompt: str, system: str = "", max_tokens: int = 800) -> str:
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    kwargs = dict(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    return client.messages.create(**kwargs).content[0].text.strip()


# ── Neighborhood Scorecard ─────────────────────────────────────────────────────

_HUBS = {
    "Victoria Island": "Victoria Island, Lagos, Nigeria",
    "Ikoyi": "Ikoyi, Lagos, Nigeria",
    "Ikeja": "Ikeja, Lagos, Nigeria",
}

_FLOOD_RISK_AREAS = [
    "lekki phase 1", "lekki phase 2", "ajah", "sangotedo", "chevron", "osapa",
    "banana island", "oniru", "maroko", "oworonshoki", "agege", "mushin",
    "bariga", "gbagada", "alapere", "ketu",
]


def _flood_risk_estimate(address: str) -> dict:
    addr_lower = address.lower()
    high_risk = any(area in addr_lower for area in _FLOOD_RISK_AREAS[:10])
    medium_risk = any(area in addr_lower for area in _FLOOD_RISK_AREAS[10:])
    if high_risk:
        return {"level": "HIGH", "score": 30, "note": "Area has documented flooding history. Request elevation certificate."}
    if medium_risk:
        return {"level": "MEDIUM", "score": 60, "note": "Some flood risk in wet season. Verify drainage infrastructure."}
    return {"level": "LOW", "score": 90, "note": "Lower flood risk based on topography. Standard due diligence applies."}


def get_neighborhood_scorecard(address: str, property_type: str = "residential") -> dict:
    settings = get_settings()
    api_key = settings.google_maps_api_key

    commute_results = {}
    for hub_name, hub_address in _HUBS.items():
        try:
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": address,
                "destinations": hub_address,
                "departure_time": "next_wednesday_8am",
                "traffic_model": "best_guess",
                "key": api_key,
            }
            resp = httpx.get(url, params=params, timeout=10)
            data = resp.json()
            element = data["rows"][0]["elements"][0]
            if element["status"] == "OK":
                duration_mins = element.get("duration_in_traffic", element["duration"])["value"] // 60
                distance_km = round(element["distance"]["value"] / 1000, 1)
                commute_results[hub_name] = {
                    "duration_mins": duration_mins,
                    "distance_km": distance_km,
                    "rating": "good" if duration_mins <= 25 else "moderate" if duration_mins <= 45 else "long",
                }
        except Exception as e:
            log.warning("google_maps_commute_failed", hub=hub_name, error=str(e))
            commute_results[hub_name] = {"duration_mins": None, "distance_km": None, "rating": "unavailable"}

    flood = _flood_risk_estimate(address)

    amenity_score = 70
    try:
        places_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={httpx.URL(address)}&key={api_key}"
        geo_resp = httpx.get(geo_url, timeout=8).json()
        if geo_resp.get("results"):
            loc = geo_resp["results"][0]["geometry"]["location"]
            place_resp = httpx.get(places_url, params={
                "location": f"{loc['lat']},{loc['lng']}",
                "radius": 1500,
                "type": "supermarket|hospital|school|bank",
                "key": api_key,
            }, timeout=8).json()
            amenity_count = len(place_resp.get("results", []))
            amenity_score = min(100, 50 + amenity_count * 5)
    except Exception:
        pass

    good_commutes = sum(1 for v in commute_results.values() if v.get("rating") == "good")
    overall_score = round((flood["score"] * 0.3) + (amenity_score * 0.3) + (min(100, good_commutes * 40) * 0.4))

    return {
        "address": address,
        "overall_score": overall_score,
        "flood_risk": flood,
        "commute_times": commute_results,
        "amenity_score": amenity_score,
        "verdict": "Excellent" if overall_score >= 80 else "Good" if overall_score >= 60 else "Fair" if overall_score >= 40 else "Poor",
    }


# ── Property Concierge ─────────────────────────────────────────────────────────

_CONCIERGE_SYSTEM = """You are a professional Lagos estate agent with 15 years of experience.
You answer buyer questions about a specific property using ONLY the property documentation provided.
If the answer is not in the documentation, say "This detail isn't in the current documentation — please request it from the agent."
Be direct, factual, no waffle. Nigerian buyers are savvy — treat them as equals."""


def answer_property_question(property_docs: str, question: str) -> str:
    prompt = f"""PROPERTY DOCUMENTATION:
{property_docs[:4000]}

BUYER QUESTION: {question}

Answer directly based on the documentation above."""
    return _claude(prompt, system=_CONCIERGE_SYSTEM, max_tokens=400)


# ── Proof of Funds Screener ────────────────────────────────────────────────────

_POF_SYSTEM = """You are a Lagos real estate agent assessing whether a prospective buyer
has genuine proof of funds before agreeing to a physical viewing.
Be professional but decisive — your job is to protect the listing agent's time.
Nigerian context: beware of doctored bank statements (look for inconsistent fonts, round numbers only,
no transaction history, no bank letterhead details)."""


def assess_proof_of_funds(
    property_price_ngn: float,
    pof_description: str,
    notes: str = "",
) -> dict:
    prompt = f"""PROPERTY ASKING PRICE: ₦{property_price_ngn:,.0f}

PROOF OF FUNDS SUBMITTED:
{pof_description}

AGENT NOTES: {notes or 'None'}

Assess:
1. VERDICT: PROCEED / REQUEST MORE INFO / DECLINE VIEWING
2. Funds adequacy (can they afford this property?)
3. Document authenticity signals (anything suspicious?)
4. What to request next if unclear
5. One-line rationale for the agent

Be brief. Max 5 bullet points."""
    text = _claude(prompt, system=_POF_SYSTEM, max_tokens=400)
    verdict = "PROCEED" if "PROCEED" in text.upper() else "DECLINE" if "DECLINE" in text.upper() else "REQUEST MORE INFO"
    return {"verdict": verdict, "assessment": text}


# ── KYC Vault ─────────────────────────────────────────────────────────────────

_KYC_SYSTEM = """You are a Nigerian KYC officer extracting structured data from identity documents.
Extract all available fields. For any field not clearly visible, output null.
Be precise — this data goes into a legal vault."""


def extract_kyc_data(document_type: str, document_text_or_description: str) -> dict:
    prompt = f"""DOCUMENT TYPE: {document_type}

DOCUMENT CONTENT / DESCRIPTION:
{document_text_or_description[:3000]}

Extract the following fields as JSON:
- full_name
- date_of_birth
- document_number (NIN / passport number / account number)
- issue_date (if visible)
- expiry_date (if applicable)
- address (if on document)
- issuing_authority
- verification_flags (list any suspicious elements)
- overall_authenticity: LIKELY_GENUINE / SUSPICIOUS / CANNOT_DETERMINE

Return ONLY valid JSON, no commentary."""
    raw = _claude(prompt, system=_KYC_SYSTEM, max_tokens=500)
    import json
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"raw_extraction": raw, "parse_error": True}


# ── Tenant Background Check ────────────────────────────────────────────────────

_BG_SYSTEM = """You are a Lagos landlord's trusted advisor conducting a tenant risk assessment.
Nigerian rental context: key risks are rent default (common), subletting without permission,
property damage, using property for illegal activities, difficulty with eviction.
Be direct. Landlords in Lagos have limited legal recourse — flag ALL red flags clearly."""


def assess_tenant_background(
    tenant_name: str,
    occupation: str,
    employer: str,
    monthly_income_ngn: float,
    rent_amount_ngn: float,
    previous_landlord_feedback: str,
    guarantor_info: str,
    additional_notes: str,
) -> dict:
    rent_to_income = (rent_amount_ngn / monthly_income_ngn * 100) if monthly_income_ngn > 0 else 999
    prompt = f"""TENANT BACKGROUND ASSESSMENT

Name: {tenant_name}
Occupation: {occupation} at {employer}
Monthly Income: ₦{monthly_income_ngn:,.0f}
Rent Amount: ₦{rent_amount_ngn:,.0f}/month
Rent-to-Income Ratio: {rent_to_income:.0f}%
Previous Landlord Feedback: {previous_landlord_feedback or 'None provided'}
Guarantor: {guarantor_info or 'None provided'}
Additional Notes: {additional_notes or 'None'}

Assess:
1. RISK RATING: LOW / MEDIUM / HIGH
2. Affordability verdict (standard: rent should be max 33% of income)
3. Top 3 risk flags (if any)
4. Recommended conditions before signing lease
5. Overall recommendation: APPROVE / APPROVE WITH CONDITIONS / DECLINE"""
    text = _claude(prompt, system=_BG_SYSTEM, max_tokens=500)
    risk = "HIGH" if "HIGH" in text.upper()[:100] else "MEDIUM" if "MEDIUM" in text.upper()[:100] else "LOW"
    recommendation = "DECLINE" if "DECLINE" in text.upper() else "APPROVE WITH CONDITIONS" if "CONDITIONS" in text.upper() else "APPROVE"
    return {
        "risk_rating": risk,
        "recommendation": recommendation,
        "rent_to_income_pct": round(rent_to_income, 1),
        "assessment": text,
    }


# ── Lawyer Bundle Generator ────────────────────────────────────────────────────

def generate_lawyer_bundle_summary(
    property_address: str,
    buyer_name: str,
    seller_name: str,
    agreed_price_ngn: float,
    documents_collected: str,
    chat_summary: str,
) -> str:
    prompt = f"""Generate a professional deal summary memo for a closing lawyer handling this Lagos real estate transaction.

PROPERTY: {property_address}
BUYER: {buyer_name}
SELLER: {seller_name}
AGREED PRICE: ₦{agreed_price_ngn:,.0f}
DOCUMENTS COLLECTED: {documents_collected}
NEGOTIATION SUMMARY: {chat_summary}

Format as a structured legal handover memo. Include:
1. Transaction parties and roles
2. Property details and agreed price
3. Documents in the bundle (checklist)
4. Outstanding items before contract exchange
5. Red flags or conditions to include in the deed
6. Recommended next steps for the lawyer

Use formal legal language. Nigerian property law context (Land Use Act, Governor's Consent, C of O)."""
    return _claude(prompt, max_tokens=800)
