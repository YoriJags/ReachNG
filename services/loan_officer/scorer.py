"""
AI Loan Officer — credit scoring engine.

Takes a structured loan application and produces:
  - Risk band: A (excellent) → D (decline)
  - Decision: Approve / Refer / Decline
  - Scored factors with individual flags
  - Red flags list

Rules engine runs first (hard limits).
Claude Sonnet then reasons over the full picture and produces the final band + rationale.
"""
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()

# ── Nigerian MFB scoring context ───────────────────────────────────────────────

_SCORING_SYSTEM = """You are a senior Nigerian credit risk officer with 15 years of experience \
at microfinance banks and commercial lenders in Lagos.

You apply Nigerian MFB lending standards and CBN prudential guidelines exclusively.

YOUR KNOWLEDGE BASE:
• CBN Prudential Guidelines for MFBs — maximum single obligor limit (1% of shareholders' funds \
  for unit MFBs), capital adequacy requirements, NPL thresholds
• Nigerian borrower risk patterns:
  - Market traders: income irregular but verifiable through market association records; \
    tend to self-cure on default to protect market space
  - Salary earners (private sector): most reliable income — verify with payslip + bank statement
  - Civil servants: stable but pension deductions reduce disposable income significantly
  - SME owners: high income potential but illiquid; business cash flow ≠ personal income
  - Transport/logistics operators: seasonal, fuel price sensitive
  - Loan stacking: borrowers with multiple concurrent MFB loans — highest default predictor in Nigeria
  - Over-leveraged households: Lagos cost of living means DTI above 40% is high risk even for salaried
• Productive vs consumptive loans:
  - Productive (working capital, equipment, trade finance): lower risk — loan generates repayment
  - Consumptive (school fees, rent, medical): higher risk — no income-generating mechanism
  - Mixed: assess primary purpose
• Address risk in Lagos:
  - Floating population (Oshodi, Mile 12, Alaba): harder to trace on default
  - Established addresses with tenancy proof: lower flight risk
• Employer verification:
  - Unverifiable employer name (generic "Company Ltd", PO box address): high risk
  - Known large employer (GTBank, MTN, NNPC, federal/state government): low risk

SCORING FACTORS — weight each in your analysis:
1. Debt-to-Income Ratio (DTI): Below 30% = excellent, 30-40% = acceptable, above 40% = risky, above 50% = decline
2. Loan-to-Income Ratio: Requested amount vs monthly income. Above 6× monthly income = high risk for unsecured
3. Loan Purpose: Productive = lower risk premium; consumptive = higher risk premium
4. Employment/Income Stability: Verified salaried > verifiable business > self-declared income
5. Existing Obligations: Number of current loans, total monthly repayment obligations
6. Loan Tenure vs Purpose: Working capital loan > 12 months is suspicious; personal loan > 24 months increases default risk
7. Collateral: Presence, type, and realisability under Nigerian law
8. Loan History: Reported previous defaults or successful repayment history
9. Address Stability: Lagos address with verifiable tenancy/ownership vs transient
10. Employer Verifiability: Can the employer be confirmed via a phone call or public record?

RISK BANDS:
A — Excellent: Approve at standard rate. DTI < 30%, verified income, productive purpose, no red flags.
B — Good: Approve with standard conditions. Minor risk factors present but manageable.
C — Elevated: Refer to senior officer OR approve with enhanced conditions (guarantor, reduced amount, shorter tenure).
D — High Risk: Decline or require significant restructuring. Multiple red flags, DTI > 50%, unverifiable income.

OUTPUT FORMAT — always return valid JSON matching the schema described in the user prompt."""


# ── Loan purpose classification ───────────────────────────────────────────────

PRODUCTIVE_KEYWORDS = [
    "working capital", "stock", "inventory", "equipment", "machinery", "trade",
    "business expansion", "shop", "market", "raw material", "production",
    "farm", "agriculture", "transport", "logistics", "contract finance",
    "invoice discounting", "supply", "export", "import",
]

CONSUMPTIVE_KEYWORDS = [
    "school fees", "hospital", "medical", "rent", "salary", "personal",
    "house repair", "furniture", "electronics", "travel", "wedding",
    "burial", "celebration", "car repair", "utility",
]


def classify_loan_purpose(purpose: str) -> tuple[str, str]:
    """Returns (classification, note) — 'productive' | 'consumptive' | 'mixed'"""
    lower = purpose.lower()
    prod  = any(k in lower for k in PRODUCTIVE_KEYWORDS)
    cons  = any(k in lower for k in CONSUMPTIVE_KEYWORDS)
    if prod and cons:
        return "mixed", "Contains both productive and consumptive elements — assess primary use"
    if prod:
        return "productive", "Loan generates economic activity — lower risk premium"
    if cons:
        return "consumptive", "No income-generating mechanism from this loan — higher risk premium"
    return "unclassified", "Purpose unclear — officer should confirm with applicant"


def run_rules_engine(app: dict) -> dict:
    """
    Hard rule checks before Claude reasoning.
    Returns dict of {factor: {value, flag, note}} + hard_decline bool.
    """
    monthly_income   = app.get("monthly_income_ngn", 0) or 0
    loan_amount      = app.get("loan_amount_ngn", 0) or 0
    loan_tenure_months = app.get("loan_tenure_months", 12) or 12
    existing_monthly = app.get("existing_monthly_obligations_ngn", 0) or 0
    monthly_repayment = loan_amount / loan_tenure_months if loan_tenure_months > 0 else loan_amount

    total_obligations = existing_monthly + monthly_repayment
    dti = (total_obligations / monthly_income * 100) if monthly_income > 0 else 999
    lti = (loan_amount / monthly_income) if monthly_income > 0 else 999

    purpose_raw = app.get("loan_purpose", "")
    purpose_class, purpose_note = classify_loan_purpose(purpose_raw)

    existing_loans = app.get("existing_loan_count", 0) or 0
    has_collateral = bool(app.get("collateral_description", "").strip())

    flags = {}
    hard_decline = False

    # DTI check
    if dti < 30:
        flags["dti"] = {"value": round(dti, 1), "flag": "green", "note": "DTI excellent — well within safe range"}
    elif dti < 40:
        flags["dti"] = {"value": round(dti, 1), "flag": "amber", "note": "DTI acceptable but monitor repayment capacity"}
    elif dti < 50:
        flags["dti"] = {"value": round(dti, 1), "flag": "red", "note": "DTI high — assess if income is conservative estimate"}
    else:
        flags["dti"] = {"value": round(dti, 1), "flag": "critical", "note": "DTI exceeds 50% — borrower cannot service this loan from stated income"}
        hard_decline = True

    # LTI check
    if lti <= 3:
        flags["lti"] = {"value": round(lti, 1), "flag": "green", "note": "Loan amount proportionate to income"}
    elif lti <= 6:
        flags["lti"] = {"value": round(lti, 1), "flag": "amber", "note": "Loan-to-income elevated — verify income carefully"}
    else:
        flags["lti"] = {"value": round(lti, 1), "flag": "red", "note": "Loan amount significantly exceeds income capacity"}

    # Loan stacking
    if existing_loans == 0:
        flags["loan_stacking"] = {"value": 0, "flag": "green", "note": "No existing loans reported"}
    elif existing_loans == 1:
        flags["loan_stacking"] = {"value": 1, "flag": "amber", "note": "One existing loan — verify total obligations are as stated"}
    else:
        flags["loan_stacking"] = {"value": existing_loans, "flag": "red", "note": f"{existing_loans} concurrent loans — highest default predictor. Verify all obligations."}
        if existing_loans >= 3:
            hard_decline = True

    # Loan purpose
    purpose_flag = {"productive": "green", "consumptive": "amber", "mixed": "amber", "unclassified": "red"}
    flags["loan_purpose"] = {
        "value": purpose_class,
        "flag": purpose_flag.get(purpose_class, "amber"),
        "note": purpose_note,
    }

    # Collateral
    flags["collateral"] = {
        "value": "present" if has_collateral else "none",
        "flag": "green" if has_collateral else "amber",
        "note": app.get("collateral_description", "No collateral offered") if has_collateral else "Unsecured — price risk premium into rate",
    }

    # Computed values for Claude
    flags["_computed"] = {
        "dti_pct":             round(dti, 1),
        "lti_multiple":        round(lti, 1),
        "monthly_repayment":   round(monthly_repayment),
        "total_obligations":   round(total_obligations),
        "purpose_class":       purpose_class,
    }

    return {"factors": flags, "hard_decline": hard_decline}


def score_application(app: dict) -> dict:
    """
    Full scoring: rules engine → Claude reasoning → structured decision.
    Returns complete scoring result ready for memo generation.
    """
    rules = run_rules_engine(app)
    factors = rules["factors"]
    computed = factors.pop("_computed", {})
    hard_decline = rules["hard_decline"]

    # Build factor summary for Claude
    factor_lines = []
    for k, v in factors.items():
        factor_lines.append(
            f"- {k.replace('_',' ').title()}: {v['value']} [{v['flag'].upper()}] — {v['note']}"
        )

    prompt = f"""Score this loan application for a Nigerian microfinance bank.

APPLICANT DETAILS:
- Name: {app.get('applicant_name', 'N/A')}
- Occupation: {app.get('occupation', 'N/A')}
- Employer / Business: {app.get('employer_or_business', 'N/A')}
- Employment Type: {app.get('employment_type', 'N/A')}
- Monthly Income (stated): ₦{app.get('monthly_income_ngn', 0):,.0f}
- Address: {app.get('address', 'N/A')}
- Phone: {app.get('phone', 'N/A')}
- BVN Verified: {app.get('bvn_verified', 'Not checked')}
- Previous Loan History: {app.get('loan_history', 'Not provided')}

LOAN REQUEST:
- Amount: ₦{app.get('loan_amount_ngn', 0):,.0f}
- Purpose: {app.get('loan_purpose', 'N/A')}
- Tenure: {app.get('loan_tenure_months', 12)} months
- Collateral: {app.get('collateral_description', 'None offered')}
- Guarantor: {app.get('guarantor_name', 'None')}

RULES ENGINE OUTPUT:
- Debt-to-Income Ratio: {computed.get('dti_pct', 'N/A')}%
- Loan-to-Income Multiple: {computed.get('lti_multiple', 'N/A')}×
- Estimated Monthly Repayment: ₦{computed.get('monthly_repayment', 0):,.0f}
- Total Monthly Obligations After Loan: ₦{computed.get('total_obligations', 0):,.0f}
- Existing Loan Count: {app.get('existing_loan_count', 0)}
- Existing Monthly Obligations: ₦{app.get('existing_monthly_obligations_ngn', 0):,.0f}
- Purpose Classification: {computed.get('purpose_class', 'N/A')}
{"- ⚠️ HARD DECLINE TRIGGERED by rules engine (DTI > 50% or 3+ concurrent loans)" if hard_decline else ""}

FACTOR FLAGS:
{chr(10).join(factor_lines)}

ADDITIONAL OFFICER NOTES:
{app.get('officer_notes', 'None')}

Return a JSON object with EXACTLY this structure:
{{
  "risk_band": "A" | "B" | "C" | "D",
  "decision": "Approve" | "Refer" | "Decline",
  "confidence": "high" | "medium" | "low",
  "recommended_amount_ngn": <integer — same as requested if no concern, reduced if risk warrants>,
  "recommended_tenure_months": <integer>,
  "recommended_rate_pct": <float — annual interest rate>,
  "conditions": [<list of conditions officer must satisfy before disbursement>],
  "red_flags": [<list of specific concerns — max 6, most serious first>],
  "strengths": [<list of positive factors — max 4>],
  "rationale": "<3-4 sentence explanation of the decision in plain English — cite specific Nigerian MFB risk factors>",
  "officer_action": "<one clear instruction to the loan officer — what to do next>"
}}

Return ONLY the JSON. No markdown, no explanation outside the JSON."""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=_SCORING_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())

    # Attach factor flags to result
    result["factors"] = factors
    result["computed"] = computed
    result["hard_decline_triggered"] = hard_decline

    log.info("loan_scored",
             applicant=app.get("applicant_name"),
             band=result.get("risk_band"),
             decision=result.get("decision"),
             dti=computed.get("dti_pct"))
    return result
