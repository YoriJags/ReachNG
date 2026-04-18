"""
Fake Product Authentication Scanner — detects counterfeit products
using AI analysis of packaging, markings, and known adulteration patterns.

Covers: pharmaceuticals, electronics, cosmetics, food products, lubricants.
"""
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()

# Known adulteration patterns by product category in Nigeria
NAFDAC_PREFIXES = {
    "pharmaceutical": ["A7-", "B7-", "C7-", "D7-", "E7-", "A1-", "B1-"],
    "food": ["A1-", "B1-", "C1-"],
    "cosmetic": ["A4-", "B4-", "C4-"],
    "water": ["A3-"],
}

_SYSTEM = """You are a Nigerian product authentication specialist with expertise in \
counterfeit detection across pharmaceuticals, electronics, cosmetics, and food products.

Nigerian counterfeiting context you know well:
PHARMACEUTICALS:
- Fake paracetamol, amoxicillin, and antimalarials are rampant (Alaba and Oshodi markets)
- NAFDAC numbers follow format: XX-XXXXX (2 letters, dash, 5 digits) — verify prefix matches product type
- Genuine Nigerian drugs have tamper-evident seals; fakes often have loose or re-glued seals
- Colour inconsistency in tablet coating is a strong fake signal
- Genuine Emzor/Fidson packaging has specific font weights — fakes use generic fonts

ELECTRONICS (Alaba International Market):
- Fake Samsung/Apple products: misaligned logos, slightly wrong font, lighter weight
- Power adapters: genuine have certification marks (NAFDAC/SON); fakes omit or blur them
- Screen brightness: genuine flagship phones have specific nit ratings

LUBRICANTS/FUEL ADDITIVES:
- Fake engine oil: thinner consistency, lighter colour, wrong viscosity
- Repackaged used oil is common — smell is the strongest signal

FOOD PRODUCTS:
- Repackaged expired goods with new labels
- Diluted beverages (Milo, Indomie fake packs)

COSMETICS:
- Fake Fair & Lovely, Ponds: wrong texture, stronger chemical smell, packaging discolouration

CONSTRUCTION MATERIALS (handled by Material Check — defer those)

Always consider: Is the price suspiciously low? Where was it purchased? What was the packaging condition?

Return ONLY valid JSON matching the schema in the user prompt."""


def authenticate_product(submission: dict) -> dict:
    """Run authentication check against known counterfeit patterns."""
    prompt = f"""Authenticate this product submission from a Nigerian retailer/consumer.

PRODUCT DETAILS:
- Product name: {submission.get('product_name')}
- Brand: {submission.get('brand')}
- NAFDAC number on pack: {submission.get('nafdac_number') or 'Not checked / not applicable'}
- Batch number: {submission.get('batch_number') or 'Not provided'}
- Supplier: {submission.get('supplier')}
- Packaging description: {submission.get('description')}

BUSINESS: {submission.get('business')}

Assess authenticity based on:
1. NAFDAC number format validity (if applicable)
2. Known counterfeiting patterns for this product/brand
3. Red flags in the packaging description
4. Supplier location risk (Alaba, Oshodi, Mile 12 = higher counterfeit risk)

Return JSON with this exact structure:
{{
  "verdict": "GENUINE" | "COUNTERFEIT" | "SUSPECTED_FAKE" | "INCONCLUSIVE",
  "confidence": "high" | "medium" | "low",
  "risk_score": <integer 0-100, where 100 = definitely counterfeit>,
  "analysis": "<3-4 sentences explaining your assessment>",
  "red_flags": [<list of specific counterfeit indicators found>],
  "genuine_indicators": [<list of positive authenticity signs>],
  "recommended_action": "<one clear action: reject batch, test sample, report to NAFDAC, etc.>",
  "nafdac_format_valid": <true | false | null if not applicable>
}}

Return ONLY valid JSON."""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())

    log.info("product_authenticated",
             product=submission.get("product_name"),
             verdict=result.get("verdict"),
             confidence=result.get("confidence"))
    return result
