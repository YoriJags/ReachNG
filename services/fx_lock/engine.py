"""
FX Rate Invoice Lock — monitors USD/NGN parallel market rate and alerts
import-dependent businesses when quotes need to be locked or repriced.
"""
import httpx
import anthropic
from datetime import datetime, timezone
from config import get_settings
import structlog

log = structlog.get_logger()

# Free exchange rate source — parallel market estimated via premium over official
_RATE_API = "https://api.exchangerate-api.com/v4/latest/USD"

# Nigerian parallel market premium over official CBN rate (approximate)
# Adjust when CBN/parallel gap changes significantly
PARALLEL_PREMIUM = 1.08  # ~8% premium over official rate (current reality)


async def fetch_current_rate() -> dict:
    """
    Fetch current USD/NGN rate. Uses official rate * premium as proxy for parallel market.
    Returns {usd_ngn_official, usd_ngn_parallel, source, fetched_at}
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_RATE_API)
            resp.raise_for_status()
            data = resp.json()
            official = data["rates"].get("NGN", 1600.0)
            parallel = round(official * PARALLEL_PREMIUM, 2)
            log.info("fx_rate_fetched", official=official, parallel=parallel)
            return {
                "usd_ngn_official": official,
                "usd_ngn_parallel": parallel,
                "source": "exchangerate-api + parallel premium",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        log.warning("fx_rate_fetch_failed", error=str(e))
        # Fallback to last known rate if fetch fails
        return {
            "usd_ngn_official": 1600.0,
            "usd_ngn_parallel": 1728.0,
            "source": "fallback",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


def calculate_quote_ngn(usd_value: float, rate: float) -> float:
    return round(usd_value * rate, 2)


def check_threshold_breach(
    locked_rate: float,
    current_rate: float,
    threshold_pct: float,
) -> tuple[bool, float]:
    """Returns (breached, change_pct)"""
    change_pct = ((current_rate - locked_rate) / locked_rate) * 100
    return abs(change_pct) >= threshold_pct, round(change_pct, 2)


def generate_fx_alert_message(
    business_name: str,
    quote_description: str,
    locked_rate: float,
    current_rate: float,
    change_pct: float,
    usd_value: float,
    expiry_date: str,
) -> str:
    """Generate WhatsApp alert message for rate threshold breach."""
    locked_ngn = calculate_quote_ngn(usd_value, locked_rate)
    current_ngn = calculate_quote_ngn(usd_value, current_rate)
    loss = current_ngn - locked_ngn

    direction = "risen" if change_pct > 0 else "fallen"
    impact = "cost more" if change_pct > 0 else "cost less"

    return (
        f"FX Alert — {business_name}\n\n"
        f"Rate has {direction} {abs(change_pct):.1f}% since you locked your quote.\n\n"
        f"Quote: {quote_description}\n"
        f"Locked rate: ₦{locked_rate:,.0f}/USD → ₦{locked_ngn:,.0f}\n"
        f"Current rate: ₦{current_rate:,.0f}/USD → ₦{current_ngn:,.0f}\n"
        f"Impact: ₦{abs(loss):,.0f} {'more' if loss > 0 else 'saved'}\n\n"
        f"Quote expires: {expiry_date}\n"
        f"Action: {'Update your pricing now or absorb the loss.' if change_pct > 0 else 'Good news — you can reprice lower or keep the margin.'}"
    )
