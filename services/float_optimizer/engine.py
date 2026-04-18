"""
OPay/PalmPay/Moniepoint Float Optimizer — tracks mobile money agent float
utilization and recommends optimal levels to prevent liquidity shortfalls.
"""
from datetime import datetime, timezone
import structlog

log = structlog.get_logger()

# Risk thresholds
SHORTFALL_RISK_RATIO = 0.85   # utilization > 85% = shortfall risk
LOW_UTILIZATION_RATIO = 0.30  # utilization < 30% = float is too high (dead capital)

# Peak day multipliers by day of week (0=Mon, 4=Fri)
PEAK_DAY_MULTIPLIERS = {
    0: 1.2,   # Monday (post-weekend activity)
    1: 1.0,
    2: 1.0,
    3: 1.0,
    4: 1.4,   # Friday (salary day preparation, market day)
    5: 1.6,   # Saturday (market day)
    6: 0.6,   # Sunday
}


def calculate_recommendation(agent: dict) -> dict:
    """
    Analyse an agent's float and generate optimization recommendation.
    Returns risk level, optimal float range, and action.
    """
    current_float = agent.get("current_float_ngn", 0) or 0
    daily_volume = agent.get("avg_daily_volume_ngn", 0) or 0
    peak_days_raw = (agent.get("peak_days", "") or "").lower()

    # Estimate peak day multiplier
    peak_mult = 1.0
    if "friday" in peak_days_raw or "salary" in peak_days_raw:
        peak_mult = max(peak_mult, 1.5)
    if "saturday" in peak_days_raw or "market" in peak_days_raw:
        peak_mult = max(peak_mult, 1.6)
    if "monday" in peak_days_raw:
        peak_mult = max(peak_mult, 1.3)

    peak_volume = daily_volume * peak_mult
    utilization_pct = (daily_volume / current_float * 100) if current_float > 0 else 0
    peak_utilization_pct = (peak_volume / current_float * 100) if current_float > 0 else 0

    # Optimal float: enough to cover 2x peak day volume (buffer for same-day liquidity)
    optimal_float = round(peak_volume * 2)
    min_float = round(peak_volume * 1.2)
    max_float = round(peak_volume * 3)  # above this is dead capital

    # Risk assessment
    if peak_utilization_pct > 85:
        risk = "high"
        action = f"Top up float immediately. At peak, you'll run out mid-day. Add at least ₦{max(0, optimal_float - current_float):,.0f}."
    elif peak_utilization_pct > 65:
        risk = "medium"
        action = f"Float is adequate for normal days but tight on peak days. Recommend increasing to ₦{optimal_float:,.0f}."
    elif utilization_pct < 30:
        risk = "low"
        action = f"Float is too high — ₦{current_float - max_float:,.0f} is idle capital. Reduce to ₦{optimal_float:,.0f} and redeploy the rest."
    else:
        risk = "low"
        action = "Float level is well-calibrated. No action needed."

    return {
        "current_float_ngn": current_float,
        "avg_daily_volume_ngn": daily_volume,
        "peak_volume_ngn": round(peak_volume),
        "recommended_float_ngn": optimal_float,
        "min_float_ngn": min_float,
        "max_float_ngn": max_float,
        "utilization_pct": round(utilization_pct, 1),
        "peak_utilization_pct": round(peak_utilization_pct, 1),
        "risk": risk,
        "action": action,
    }


def generate_shortfall_alert(agent_name: str, platform: str, shortfall_ngn: float) -> str:
    """WhatsApp alert for imminent float shortfall."""
    return (
        f"Float Alert — {agent_name} ({platform})\n\n"
        f"Your float is running low. Estimated shortfall: ₦{shortfall_ngn:,.0f}\n\n"
        f"You may not be able to complete customer transactions later today.\n\n"
        f"Top up now to avoid downtime."
    )
