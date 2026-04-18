"""
Market Woman Credit Profiler — informal trader credit scoring for Nigerian MFBs.

Builds a credit profile from non-traditional signals:
- Years trading at same market (stability indicator)
- Market association membership (social accountability)
- Type of goods (perishable = lower risk — daily cash flow)
- Peer references (two-trader verification)
- Daily sales estimate vs loan amount ratio
"""
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()

# Goods with reliable daily cash flow — lower credit risk for MFBs
HIGH_CASHFLOW_GOODS = [
    "food", "vegetables", "tomato", "pepper", "yam", "fish", "meat", "chicken",
    "bread", "akara", "beans", "rice", "garri", "palm oil", "groceries",
    "drinks", "water", "juice", "provisions",
]

# Market associations add social accountability — defaulting risks market exclusion
KNOWN_ASSOCIATIONS = [
    "traders union", "market association", "onitsha main market",
    "balogun", "alaba", "mile 12", "oshodi", "ketu", "oyingbo",
    "tejuosho", "idumota", "lagos island",
]

_SYSTEM = """You are a Nigerian microfinance credit officer specialising in market trader loans.

You score traders who have NO formal credit history — no bank statements, no payslips. \
Instead, you assess informal signals that experienced Lagos MFB officers know to be reliable:

Key risk signals for market traders:
1. STABILITY: Traders at same location 3+ years rarely default — they protect their market space
2. DAILY CASHFLOW: Food/perishable traders have daily income — they can service daily/weekly collections
3. ASSOCIATION MEMBERSHIP: Market association members face social consequences for default — lower risk
4. PEER REFERENCES: Two credible references from other traders is the informal equivalent of a guarantor
5. LOAN-TO-DAILY-SALES RATIO: Loan repayment should not exceed 30% of estimated daily sales
6. GOODS TYPE: Electronics/fashion = irregular sales; food/provisions = reliable daily turnover
7. TIME IN BUSINESS: <1 year = high risk; 1-3 years = medium; 3+ years = low
8. LOAN PURPOSE: Stock finance (working capital) = lowest risk — loan is self-liquidating

Return ONLY valid JSON with the schema specified in the user prompt."""


def run_informal_rules(app: dict) -> dict:
    """Rules engine for informal trader scoring."""
    daily_sales = app.get("daily_sales_ngn", 0) or 0
    loan_amount = app.get("loan_amount_ngn", 0) or 0
    years = app.get("years_trading", 0) or 0
    goods = (app.get("goods_type", "") or "").lower()
    assoc = (app.get("association_membership", "") or "").lower()
    refs = (app.get("peer_references", "") or "").strip()

    flags = {}

    # Stability
    if years >= 5:
        flags["stability"] = {"value": years, "flag": "green", "note": f"{years} years — very stable location"}
    elif years >= 3:
        flags["stability"] = {"value": years, "flag": "amber", "note": f"{years} years — established trader"}
    elif years >= 1:
        flags["stability"] = {"value": years, "flag": "amber", "note": f"{years} years — moderate tenure"}
    else:
        flags["stability"] = {"value": years, "flag": "red", "note": "Less than 1 year — new trader, unproven"}

    # Cashflow type
    is_high_cf = any(k in goods for k in HIGH_CASHFLOW_GOODS)
    flags["cashflow_type"] = {
        "value": goods,
        "flag": "green" if is_high_cf else "amber",
        "note": "Daily cash flow — food/perishables" if is_high_cf else "Irregular sales — assess carefully",
    }

    # Association
    has_assoc = "yes" in assoc or any(k in assoc for k in KNOWN_ASSOCIATIONS)
    flags["association"] = {
        "value": assoc,
        "flag": "green" if has_assoc else "amber",
        "note": "Association member — social accountability" if has_assoc else "No association — higher flight risk",
    }

    # References
    ref_count = len([r for r in refs.split("\n") if r.strip()]) if refs else 0
    flags["peer_references"] = {
        "value": ref_count,
        "flag": "green" if ref_count >= 2 else ("amber" if ref_count == 1 else "red"),
        "note": f"{ref_count} references provided",
    }

    # Loan-to-daily-sales ratio
    if daily_sales > 0:
        monthly_sales = daily_sales * 26  # ~26 trading days/month
        lts = loan_amount / monthly_sales
        flags["loan_to_sales"] = {
            "value": round(lts, 2),
            "flag": "green" if lts <= 1.0 else ("amber" if lts <= 2.0 else "red"),
            "note": f"Loan = {lts:.1f}× monthly sales — {'manageable' if lts <= 1.0 else 'elevated' if lts <= 2.0 else 'too high'}",
        }
    else:
        flags["loan_to_sales"] = {"value": "unknown", "flag": "amber", "note": "Daily sales not verified"}

    hard_decline = (
        years < 1 and ref_count == 0
    ) or (
        daily_sales > 0 and loan_amount / (daily_sales * 26) > 3.0
    )

    return {"factors": flags, "hard_decline": hard_decline}


def score_trader(app: dict) -> dict:
    """Full informal trader scoring: rules → Claude reasoning → decision."""
    rules = run_informal_rules(app)
    factors = rules["factors"]
    hard_decline = rules["hard_decline"]

    factor_lines = [
        f"- {k.replace('_',' ').title()}: {v['value']} [{v['flag'].upper()}] — {v['note']}"
        for k, v in factors.items()
    ]

    prompt = f"""Score this informal market trader loan application for a Nigerian MFB.

TRADER DETAILS:
- Name: {app.get('trader_name')}
- Market: {app.get('market')}
- Goods sold: {app.get('goods_type')}
- Years at this market: {app.get('years_trading')}
- Daily sales estimate: ₦{app.get('daily_sales_ngn', 0):,.0f}
- Association: {app.get('association_membership')}
- References: {app.get('peer_references', 'None')}
- Phone: {app.get('phone')}

LOAN REQUEST:
- Amount: ₦{app.get('loan_amount_ngn', 0):,.0f}
- Purpose: {app.get('loan_purpose', 'Working capital / stock finance')}

RULES ENGINE FLAGS:
{chr(10).join(factor_lines)}
{"⚠️ HARD DECLINE TRIGGERED" if hard_decline else ""}

Return JSON with this exact structure:
{{
  "score": <integer 0-100>,
  "decision": "Approve" | "Refer" | "Decline",
  "risk_level": "low" | "medium" | "high",
  "recommended_amount_ngn": <integer>,
  "recommended_collection": "daily" | "weekly" | "monthly",
  "conditions": [<list of verification steps before disbursement>],
  "red_flags": [<list of concerns>],
  "rationale": "<2-3 sentence explanation using Nigerian MFB context>",
  "officer_action": "<one clear next step for the loan officer>"
}}

Return ONLY valid JSON."""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
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
    result["factors"] = factors
    result["hard_decline_triggered"] = hard_decline

    log.info("market_trader_scored",
             trader=app.get("trader_name"), score=result.get("score"),
             decision=result.get("decision"))
    return result
