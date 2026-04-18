"""
Construction Material Adulteration Checker — detects substandard or
adulterated building materials common in Nigerian construction sites.

Covers: cement, iron rods, roofing sheets, paint, blocks, sand, granite.
"""
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()

_SYSTEM = """You are a Nigerian construction quality control engineer \
with 15 years of site experience across Lagos, Abuja, and Port Harcourt.

Nigerian construction material adulteration is widespread. Key patterns you know:

CEMENT:
- Adulterated cement: lighter bags (genuine 50kg often 47-48kg), faster setting time than normal,
  powdery rather than smooth texture, grey is too light (limestone filler added)
- Brands to watch: Dangote, WAPCO/Lafarge, BUA, Elephant — all heavily counterfeited
- Genuine Dangote 42.5N: consistent grey, smooth, 28-day compressive strength ≥42.5 MPa
- Red flag: cement bought from roadside hawkers or unofficial depots

IRON RODS / REINFORCEMENT:
- Nigerian Standard: hot-rolled deformed bars to NIS 117 or BS 4449
- Substandard rods: wrong diameter (10mm rod measuring 8.5mm), lighter than spec,
  brittle when bent, excessive rust at delivery, inconsistent rib pattern
- Local "tyre rod" (made from scrap/tyres): very cheap, catastrophic in structure

ROOFING SHEETS:
- Substandard: thinner gauge than stated, soft (easy to dent with thumb),
  uneven coating (visible bare spots), shorter sheets than stated

PAINT:
- Adulterated: excessive thinning, settles quickly, poor coverage, foul smell
- Fake Crown/Berger: thin consistency, packaging colour slightly off

BLOCKS:
- Substandard: hand-crushed easily, hollow sound when tapped,
  lightweight (genuine sandcrete blocks: min 2.5N/mm² strength)

SAND:
- Adulterated: excessive silt content (squeeze test — sand should not stain wet palm brown)
- Wrong type: sea sand (saline) used for structure — causes rebar corrosion

Return ONLY valid JSON matching the schema in the user prompt."""


def check_material(submission: dict) -> dict:
    """Assess building material for adulteration risk."""
    prompt = f"""Assess this construction material batch for adulteration.

SUBMISSION:
- Company: {submission.get('company')}
- Material: {submission.get('material')}
- Supplier: {submission.get('supplier')} ({submission.get('supplier_location', 'location not stated')})
- Quantity: {submission.get('quantity')}
- Price paid: ₦{submission.get('price_per_unit', 0):,.0f} per unit
- Stated specification: {submission.get('stated_spec') or 'Not stated'}
- Site observations: {submission.get('observations')}

Assess:
1. Does the price suggest adulteration? (suspiciously low price is a strong signal)
2. Do the physical observations match genuine material for this spec?
3. Does the supplier type/location increase risk?

Return JSON with this exact structure:
{{
  "verdict": "PASS" | "FAIL" | "SUSPECT",
  "risk_level": "low" | "medium" | "high" | "critical",
  "confidence": "high" | "medium" | "low",
  "analysis": "<3-4 sentences explaining the assessment>",
  "specific_concerns": [<list of specific adulteration indicators>],
  "price_assessment": "<is the price normal, suspiciously low, or high?>",
  "structural_risk": "<if used in construction, what could go wrong?>",
  "recommendation": "<reject batch | test sample | accept with conditions | accept>",
  "test_suggestion": "<if uncertain, what physical test to do on-site>"
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

    log.info("material_checked",
             material=submission.get("material"),
             verdict=result.get("verdict"),
             risk=result.get("risk_level"))
    return result
