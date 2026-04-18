"""
FX Arbitrage Salary Parity — calculates correct naira equivalent of
dollar-benchmarked staff salaries at current parallel market rate.

For Nigerian tech companies, multinationals, and NGOs paying in USD terms.
"""
from datetime import datetime, timezone
from services.fx_lock.engine import fetch_current_rate
import structlog

log = structlog.get_logger()


async def calculate_parity(staff_records: list[dict], rate: float | None = None) -> dict:
    """
    For each staff member with a USD salary, compute this month's naira equivalent.
    Returns enriched staff list + payroll totals.
    """
    if rate is None:
        rate_data = await fetch_current_rate()
        rate = rate_data["usd_ngn_parallel"]

    enriched = []
    total_usd = 0.0
    total_ngn = 0.0

    for s in staff_records:
        usd = s.get("salary_usd", 0) or 0
        ngn = round(usd * rate)
        last_ngn = s.get("last_month_ngn") or ngn
        change_pct = ((ngn - last_ngn) / last_ngn * 100) if last_ngn else 0.0

        enriched.append({
            **s,
            "this_month_ngn": ngn,
            "last_month_ngn": last_ngn,
            "change_pct": round(change_pct, 1),
            "rate_used": rate,
        })
        total_usd += usd
        total_ngn += ngn

    return {
        "staff": enriched,
        "usd_ngn_rate": rate,
        "total_usd": round(total_usd, 2),
        "total_ngn": round(total_ngn),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_payslip_message(staff_name: str, salary_usd: float, ngn_amount: float, rate: float) -> str:
    """WhatsApp payslip notification for USD-salary staff."""
    month = datetime.now().strftime("%B %Y")
    return (
        f"Hi {staff_name},\n\n"
        f"Your {month} salary has been processed.\n\n"
        f"USD salary: ${salary_usd:,.0f}\n"
        f"Exchange rate: ₦{rate:,.0f}/USD (parallel market)\n"
        f"NGN amount: ₦{ngn_amount:,.0f}\n\n"
        f"Queries? Reply to this message."
    )
