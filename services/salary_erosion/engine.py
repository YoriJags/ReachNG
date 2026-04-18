"""
Naira Salary Erosion Tracker — calculates real purchasing power of staff
salaries over time, adjusted for Nigeria CPI inflation.

NBS Nigeria CPI data (year-over-year % change, annual average):
Updated quarterly. Source: National Bureau of Statistics Nigeria.
"""
import anthropic
from datetime import datetime, timezone, date
from config import get_settings
import structlog

log = structlog.get_logger()

# Nigeria annual CPI inflation rate by year (NBS data)
# Format: {year: annual_inflation_pct}
NIGERIA_ANNUAL_CPI: dict[int, float] = {
    2019: 11.4,
    2020: 13.2,
    2021: 16.5,
    2022: 18.8,
    2023: 24.5,
    2024: 32.7,
    2025: 28.9,  # NBS estimate
    2026: 24.0,  # projection
}

CHURN_RISK_THRESHOLDS = {
    "high":   30.0,  # >30% real value lost → likely looking for new job
    "medium": 15.0,  # 15-30% → disengaged, open to offers
    "low":    0.0,   # <15% → stable
}


def calculate_erosion(
    salary_ngn: float,
    hired_date: str,
) -> dict:
    """
    Calculate real purchasing power of salary from hire date to today.
    Returns {real_value_today, erosion_pct, churn_risk, years_tracked}
    """
    try:
        hire_dt = datetime.strptime(hired_date, "%Y-%m-%d").date()
    except ValueError:
        hire_dt = date.today().replace(day=1)

    today = date.today()
    hire_year = hire_dt.year
    current_year = today.year

    # Compound the erosion year by year
    real_value = salary_ngn
    for year in range(hire_year, current_year + 1):
        inflation_rate = NIGERIA_ANNUAL_CPI.get(year, 20.0) / 100
        # Partial year adjustment for hire year and current year
        if year == hire_year and year == current_year:
            months = (today.month - hire_dt.month) / 12
        elif year == hire_year:
            months = (12 - hire_dt.month) / 12
        elif year == current_year:
            months = today.month / 12
        else:
            months = 1.0
        real_value = real_value / (1 + inflation_rate * months)

    erosion_pct = ((salary_ngn - real_value) / salary_ngn) * 100
    erosion_pct = max(0.0, round(erosion_pct, 1))
    real_value = round(real_value, 0)

    churn_risk = "low"
    if erosion_pct >= CHURN_RISK_THRESHOLDS["high"]:
        churn_risk = "high"
    elif erosion_pct >= CHURN_RISK_THRESHOLDS["medium"]:
        churn_risk = "medium"

    return {
        "real_value_today": real_value,
        "erosion_pct": erosion_pct,
        "churn_risk": churn_risk,
        "years_tracked": round((today - hire_dt).days / 365.25, 1),
    }


def generate_erosion_report(company: str, staff_records: list[dict]) -> str:
    """Use Claude to generate a human-readable retention risk report."""
    if not staff_records:
        return "No staff records found for this company."

    high_risk = [s for s in staff_records if s.get("churn_risk") == "high"]
    medium_risk = [s for s in staff_records if s.get("churn_risk") == "medium"]
    avg_erosion = sum(s.get("erosion_pct", 0) for s in staff_records) / len(staff_records)

    staff_summary = "\n".join([
        f"- {s['name']} ({s['role']}): hired {s['hired_date']}, salary ₦{s['salary_ngn']:,.0f}, "
        f"real value today ₦{s.get('real_value_today', 0):,.0f} ({s.get('erosion_pct', 0):.1f}% erosion) — {s.get('churn_risk', 'low')} risk"
        for s in staff_records
    ])

    prompt = f"""Generate a concise salary erosion report for {company}.

STAFF DATA:
{staff_summary}

SUMMARY:
- Total staff: {len(staff_records)}
- High churn risk: {len(high_risk)} ({', '.join(s['name'] for s in high_risk) or 'none'})
- Medium churn risk: {len(medium_risk)}
- Average real value erosion: {avg_erosion:.1f}%
- Nigeria CPI context: ~24-33% annual inflation 2023-2025

Write a 3-paragraph report:
1. Overall picture and urgency level
2. Who is at highest risk and why
3. Recommended actions (salary adjustment, non-cash benefits, retention bonuses)

Be direct. Use naira figures. This is for the business owner, not HR consultants."""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
