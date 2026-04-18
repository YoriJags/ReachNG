"""
Fuel Cost Repricing Alert — monitors fuel price changes and identifies
logistics routes that have become loss-making since contract was signed.
Generates professional repricing letters to clients.
"""
import anthropic
from datetime import datetime, timezone
from config import get_settings
import structlog

log = structlog.get_logger()

# Current pump price (₦/litre) — update when NNPC changes pricing
# This can be fetched dynamically or set via env var
DEFAULT_PUMP_PRICE = 1_050.0  # as of early 2026


def calculate_route_economics(route: dict, current_pump_price: float | None = None) -> dict:
    """
    Calculate current cost of running a route and compare to agreed rate.
    Returns margin, profitability, and repricing recommendation.
    """
    pump_price = current_pump_price or DEFAULT_PUMP_PRICE
    distance_km = route.get("distance_km", 0)
    litres_per_100km = route.get("litres_per_100km", 35)  # default for 10-tonne truck
    agreed_rate = route.get("agreed_rate_ngn", 0)
    fuel_at_signing = route.get("fuel_price_at_signing", pump_price)

    litres_needed = (distance_km / 100) * litres_per_100km
    fuel_cost_now = round(litres_needed * pump_price)
    fuel_cost_at_signing = round(litres_needed * fuel_at_signing)
    fuel_increase = fuel_cost_now - fuel_cost_at_signing

    # Estimate other variable costs (driver, tolls, maintenance) as % of agreed rate
    other_costs_pct = 0.35  # 35% of agreed rate for non-fuel costs
    total_cost_now = round(fuel_cost_now + agreed_rate * other_costs_pct)
    margin_ngn = agreed_rate - total_cost_now

    repricing_suggested = fuel_cost_now / max(fuel_cost_at_signing, 1)
    fair_rate = round(agreed_rate * (1 + (repricing_suggested - 1) * 0.65))  # pass 65% of fuel increase to client

    return {
        "pump_price_ngn": pump_price,
        "distance_km": distance_km,
        "litres_needed": round(litres_needed, 1),
        "fuel_cost_at_signing": fuel_cost_at_signing,
        "fuel_cost_now": fuel_cost_now,
        "fuel_increase_ngn": fuel_increase,
        "total_cost_now": total_cost_now,
        "agreed_rate_ngn": agreed_rate,
        "margin_ngn": margin_ngn,
        "is_loss_making": margin_ngn < 0,
        "fair_rate_ngn": fair_rate,
        "rate_increase_pct": round(((fair_rate - agreed_rate) / agreed_rate) * 100, 1),
    }


def generate_repricing_letter(route: dict, economics: dict, company_name: str) -> str:
    """Generate a professional repricing letter to the client."""
    prompt = f"""Write a professional business letter from {company_name} to their logistics client \
requesting a freight rate adjustment due to fuel price increases.

CONTEXT:
- Route: {route.get('route_name')} ({route.get('distance_km')}km)
- Client: {route.get('client_name')}
- Contract signed: {route.get('contract_date', 'Previously agreed')}
- Fuel price at contract: ₦{economics.get('fuel_cost_at_signing', 0) / max(economics.get('litres_needed', 1), 1):,.0f}/litre
- Current fuel price: ₦{economics.get('pump_price_ngn', 0):,.0f}/litre
- Current agreed rate: ₦{economics.get('agreed_rate_ngn', 0):,.0f}/trip
- Proposed rate: ₦{economics.get('fair_rate_ngn', 0):,.0f}/trip ({economics.get('rate_increase_pct', 0):.1f}% increase)
- Fuel cost per trip at old price: ₦{economics.get('fuel_cost_at_signing', 0):,.0f}
- Fuel cost per trip at current price: ₦{economics.get('fuel_cost_now', 0):,.0f}
- Additional fuel cost per trip: ₦{economics.get('fuel_increase_ngn', 0):,.0f}

Write a formal but respectful letter. 3-4 paragraphs. Include:
1. Reference to the value of the business relationship
2. Clear explanation of fuel price impact with the numbers
3. Proposed new rate and effective date (suggest 2 weeks from today)
4. Commitment to continued service quality

Tone: Professional, firm but collaborative. Not apologetic. Business reality, not complaint."""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )

    letter = response.content[0].text.strip()
    log.info("repricing_letter_generated",
             route=route.get("route_name"),
             client=route.get("client_name"),
             new_rate=economics.get("fair_rate_ngn"))
    return letter
