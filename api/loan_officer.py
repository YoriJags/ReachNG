"""
AI Loan Officer — REST API + applicant portal.

Routes:
  POST /loan/apply              — submit application, get instant AI decision
  GET  /loan/applications       — list all (officer dashboard, Basic Auth)
  GET  /loan/applications/{id}  — single application with full memo
  POST /loan/applications/{id}/override — officer override with reason
  GET  /loan/portal             — public applicant intake form
  GET  /loan/status/{id}        — applicant status check (no auth required)
  GET  /loan/stats              — queue stats for dashboard
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional
from auth import require_auth
from services.loan_officer.scorer import score_application
from services.loan_officer.memo   import generate_memo, generate_memo_text
from services.loan_officer        import store
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/loan", tags=["loan_officer"])


# ── Pydantic models ────────────────────────────────────────────────────────────

class LoanApplication(BaseModel):
    mfb_client_name: str = Field(default="Charis MFB")

    # Applicant
    applicant_name:      str
    phone:               str
    occupation:          str
    employer_or_business: str
    employment_type:     str    # "salaried" | "self_employed" | "civil_servant" | "trader"
    monthly_income_ngn:  float
    address:             str
    bvn_verified:        str = "Not checked"   # "Yes" | "No" | "Not checked"
    loan_history:        Optional[str] = None

    # Loan
    loan_amount_ngn:     float
    loan_purpose:        str
    loan_tenure_months:  int = 12
    collateral_description: Optional[str] = ""
    guarantor_name:      Optional[str] = ""

    # Obligations
    existing_loan_count:             int   = 0
    existing_monthly_obligations_ngn: float = 0

    # Officer notes
    officer_notes: Optional[str] = ""


class OverrideRequest(BaseModel):
    decision:     str   # "Approve" | "Decline" | "Refer"
    reason:       str
    officer_name: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/apply")
def apply_for_loan(body: LoanApplication, _=Depends(require_auth)):
    """Score and persist a loan application. Returns decision + memo."""
    app = body.model_dump(exclude={"mfb_client_name"})
    try:
        score    = score_application(app)
        memo_html = generate_memo(app, score, mfb_name=body.mfb_client_name)
        app_id   = store.save_application(app, score, memo_html, body.mfb_client_name)
    except Exception as e:
        log.error("loan_scoring_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")

    return {
        "id":              app_id,
        "risk_band":       score["risk_band"],
        "decision":        score["decision"],
        "confidence":      score["confidence"],
        "recommended_amount_ngn":    score.get("recommended_amount_ngn"),
        "recommended_tenure_months": score.get("recommended_tenure_months"),
        "recommended_rate_pct":      score.get("recommended_rate_pct"),
        "conditions":      score.get("conditions", []),
        "red_flags":       score.get("red_flags", []),
        "strengths":       score.get("strengths", []),
        "rationale":       score.get("rationale"),
        "officer_action":  score.get("officer_action"),
        "hard_decline_triggered": score.get("hard_decline_triggered", False),
        "factors":         score.get("factors", {}),
    }


@router.get("/applications", dependencies=[Depends(require_auth)])
def list_applications(
    mfb: Optional[str] = Query(None),
    status: Optional[str]   = Query(None),
    decision: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    skip: int  = Query(0),
):
    apps = store.list_applications(
        mfb_client_name=mfb, status=status, decision=decision,
        limit=limit, skip=skip,
    )
    total = store.count_applications(mfb_client_name=mfb, status=status)
    return {"total": total, "applications": apps}


@router.get("/applications/{application_id}", dependencies=[Depends(require_auth)])
def get_application(application_id: str):
    doc = store.get_application(application_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    return doc


@router.get("/applications/{application_id}/memo", dependencies=[Depends(require_auth)])
def get_memo(application_id: str):
    doc = store.get_application(application_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    return HTMLResponse(content=doc.get("memo_html", "<p>No memo available.</p>"))


@router.post("/applications/{application_id}/override", dependencies=[Depends(require_auth)])
def override_decision(application_id: str, body: OverrideRequest):
    ok = store.officer_override(
        application_id,
        override_decision=body.decision,
        reason=body.reason,
        officer_name=body.officer_name,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"status": "overridden", "new_decision": body.decision}


@router.get("/stats", dependencies=[Depends(require_auth)])
def get_stats(mfb: Optional[str] = Query(None)):
    return store.queue_stats(mfb_client_name=mfb)


@router.get("/status/{application_id}")
def applicant_status(application_id: str):
    """Public endpoint — applicant checks their own application status."""
    doc = store.get_application(application_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    # Return minimal info — never expose score internals to applicant
    decision = doc.get("officer_override") or doc.get("decision")
    return {
        "applicant_name": doc.get("application", {}).get("applicant_name"),
        "status":         doc.get("status"),
        "decision":       decision,
        "submitted_at":   doc.get("created_at"),
    }


# ── Applicant intake portal ────────────────────────────────────────────────────

@router.get("/portal", response_class=HTMLResponse)
def applicant_portal():
    return HTMLResponse(content=_PORTAL_HTML)


_PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Loan Application Portal</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --green: #00c47a;
      --green-dark: #009e62;
      --green-glow: rgba(0,196,122,.15);
      --bg: #06090f;
      --surface: #0d1117;
      --surface2: #161b22;
      --border: #21262d;
      --border2: #30363d;
      --text: #e6edf3;
      --muted: #8b949e;
      --danger: #f85149;
      --warn: #e3b341;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      min-height: 100vh;
      color: var(--text);
      padding: 0 0 60px;
    }

    /* ── Top bar ── */
    .topbar {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .topbar-brand { display: flex; align-items: center; gap: 10px; }
    .topbar-logo {
      width: 30px; height: 30px;
      background: var(--green);
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-size: 14px; font-weight: 800; color: #000;
    }
    .topbar-name { font-size: 15px; font-weight: 700; color: var(--text); }
    .topbar-badge {
      font-size: 11px; color: var(--muted);
      background: var(--surface2);
      border: 1px solid var(--border);
      padding: 3px 10px; border-radius: 20px;
    }

    /* ── Page layout ── */
    .page { max-width: 720px; margin: 0 auto; padding: 32px 20px 0; }

    /* ── Hero ── */
    .hero { margin-bottom: 28px; }
    .hero-eyebrow {
      font-size: 11px; font-weight: 600; letter-spacing: .1em;
      text-transform: uppercase; color: var(--green); margin-bottom: 8px;
    }
    .hero h1 { font-size: 26px; font-weight: 800; color: var(--text); line-height: 1.25; }
    .hero p { font-size: 14px; color: var(--muted); margin-top: 8px; line-height: 1.6; }

    /* ── Trust bar ── */
    .trust-bar {
      display: flex; gap: 16px; flex-wrap: wrap;
      margin-bottom: 28px;
    }
    .trust-pill {
      display: flex; align-items: center; gap: 6px;
      background: var(--surface2); border: 1px solid var(--border);
      border-radius: 20px; padding: 5px 12px;
      font-size: 12px; color: var(--muted);
    }
    .trust-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); flex-shrink: 0; }

    /* ── Progress steps ── */
    .steps {
      display: flex; gap: 0; margin-bottom: 32px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; overflow: hidden;
    }
    .step {
      flex: 1; padding: 12px 8px; text-align: center;
      font-size: 11px; font-weight: 600; color: var(--muted);
      text-transform: uppercase; letter-spacing: .06em;
      border-right: 1px solid var(--border);
      position: relative; cursor: default;
    }
    .step:last-child { border-right: none; }
    .step.active { color: var(--green); background: var(--green-glow); }
    .step.done { color: var(--green); }
    .step-num {
      display: block; font-size: 16px; font-weight: 800;
      margin-bottom: 2px; color: inherit;
    }

    /* ── Form card ── */
    .form-section {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 16px;
    }
    .form-section-header {
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
      display: flex; align-items: center; gap: 10px;
    }
    .form-section-icon {
      width: 28px; height: 28px; border-radius: 7px;
      background: var(--green-glow); border: 1px solid var(--green);
      display: flex; align-items: center; justify-content: center;
      font-size: 13px; flex-shrink: 0;
    }
    .form-section-title { font-size: 13px; font-weight: 600; color: var(--text); }
    .form-section-body { padding: 20px; }

    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    @media(max-width:520px) { .grid-2 { grid-template-columns: 1fr; } }

    .field { margin-bottom: 14px; }
    .field:last-child { margin-bottom: 0; }
    label {
      display: block; font-size: 12px; font-weight: 500;
      color: var(--muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: .05em;
    }
    label .req { color: var(--danger); }

    input, select, textarea {
      width: 100%;
      background: var(--surface2);
      border: 1px solid var(--border2);
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 14px;
      color: var(--text);
      font-family: inherit;
      outline: none;
      transition: border-color .15s, box-shadow .15s;
      appearance: none;
    }
    input::placeholder, textarea::placeholder { color: #484f58; }
    input:focus, select:focus, textarea:focus {
      border-color: var(--green);
      box-shadow: 0 0 0 3px var(--green-glow);
    }
    select { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%238b949e' d='M6 8L0 0h12z'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 14px center; padding-right: 36px; cursor: pointer; }
    select option { background: #1c2128; }
    textarea { resize: vertical; min-height: 80px; line-height: 1.5; }

    /* ── Submit button ── */
    .submit-wrap { margin-top: 24px; }
    .btn-submit {
      width: 100%; padding: 15px;
      background: var(--green);
      color: #000;
      border: none; border-radius: 10px;
      font-size: 15px; font-weight: 700;
      cursor: pointer; font-family: inherit;
      transition: background .15s, transform .1s, box-shadow .15s;
      letter-spacing: .02em;
    }
    .btn-submit:hover:not(:disabled) {
      background: var(--green-dark);
      box-shadow: 0 4px 20px var(--green-glow);
    }
    .btn-submit:active:not(:disabled) { transform: scale(.98); }
    .btn-submit:disabled { background: #21262d; color: #484f58; cursor: not-allowed; }

    .btn-processing {
      display: flex; align-items: center; justify-content: center; gap: 10px;
    }
    .spinner {
      width: 16px; height: 16px;
      border: 2px solid rgba(0,0,0,.3);
      border-top-color: #000;
      border-radius: 50%;
      animation: spin .7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Disclaimer ── */
    .disclaimer {
      margin-top: 16px;
      font-size: 11px; color: var(--muted); text-align: center; line-height: 1.6;
    }

    /* ── Result screen ── */
    #resultScreen {
      display: none;
      text-align: center;
      padding: 48px 24px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
    }
    .result-icon { font-size: 56px; margin-bottom: 16px; }
    .result-band-wrap {
      display: inline-flex; align-items: center; justify-content: center;
      width: 80px; height: 80px; border-radius: 50%;
      font-size: 40px; font-weight: 900;
      margin-bottom: 16px;
    }
    .band-A { background: #0f3d24; color: #00c47a; border: 2px solid #00c47a; }
    .band-B { background: #0d1e3d; color: #3b82f6; border: 2px solid #3b82f6; }
    .band-C { background: #3d2c0d; color: #e3b341; border: 2px solid #e3b341; }
    .band-D { background: #3d0d0d; color: #f85149; border: 2px solid #f85149; }
    .result-decision-label {
      font-size: 22px; font-weight: 800; margin-bottom: 8px;
    }
    .result-decision-approve { color: #00c47a; }
    .result-decision-refer   { color: #e3b341; }
    .result-decision-decline { color: #f85149; }
    .result-rationale {
      font-size: 14px; color: var(--muted); line-height: 1.65;
      max-width: 520px; margin: 0 auto 20px;
    }
    .result-ref {
      font-size: 12px; color: #484f58;
      background: var(--surface2); border: 1px solid var(--border);
      border-radius: 6px; padding: 6px 14px; display: inline-block; margin-top: 8px;
      font-family: 'Courier New', monospace;
    }
    .result-conditions {
      margin-top: 20px; text-align: left;
      background: var(--surface2); border: 1px solid var(--border);
      border-radius: 8px; padding: 16px 18px;
      max-width: 480px; margin-left: auto; margin-right: auto;
    }
    .result-conditions-title {
      font-size: 11px; font-weight: 700; text-transform: uppercase;
      letter-spacing: .07em; color: var(--muted); margin-bottom: 10px;
    }
    .result-conditions li {
      font-size: 13px; color: var(--text); margin-bottom: 6px;
      padding-left: 4px; list-style: none;
      display: flex; gap: 8px; align-items: flex-start;
    }
    .result-conditions li::before { content: "→"; color: var(--green); flex-shrink: 0; }

    /* ── Processing overlay ── */
    #processingOverlay {
      display: none; position: fixed; inset: 0;
      background: rgba(6,9,15,.92);
      z-index: 100; align-items: center; justify-content: center;
      flex-direction: column; gap: 20px;
    }
    .processing-ring {
      width: 64px; height: 64px;
      border: 3px solid #21262d;
      border-top-color: var(--green);
      border-radius: 50%;
      animation: spin .8s linear infinite;
    }
    .processing-text { font-size: 15px; color: var(--muted); font-weight: 500; }
    .processing-sub  { font-size: 12px; color: #484f58; }
  </style>
</head>
<body>

<!-- Processing overlay -->
<div id="processingOverlay">
  <div class="processing-ring"></div>
  <div class="processing-text">Analysing your application…</div>
  <div class="processing-sub">AI credit scoring in progress</div>
</div>

<!-- Top bar -->
<div class="topbar">
  <div class="topbar-brand">
    <div class="topbar-logo">L</div>
    <span class="topbar-name">Loan Portal</span>
  </div>
  <div class="topbar-badge">Powered by AI Credit Scoring</div>
</div>

<div class="page">

  <!-- Hero -->
  <div class="hero">
    <div class="hero-eyebrow">Instant Credit Decision</div>
    <h1>Apply for a Business or Personal Loan</h1>
    <p>Complete this form accurately. Your application will be scored immediately using AI and CBN-compliant credit rules. You will see your decision before you leave this page.</p>
  </div>

  <!-- Trust signals -->
  <div class="trust-bar">
    <div class="trust-pill"><span class="trust-dot"></span> CBN-Compliant Scoring</div>
    <div class="trust-pill"><span class="trust-dot"></span> Instant AI Decision</div>
    <div class="trust-pill"><span class="trust-dot"></span> 256-bit Encrypted</div>
    <div class="trust-pill"><span class="trust-dot"></span> NDPR Compliant</div>
  </div>

  <!-- Step indicators -->
  <div class="steps">
    <div class="step active" id="step-1"><span class="step-num">1</span>Personal</div>
    <div class="step" id="step-2"><span class="step-num">2</span>Loan</div>
    <div class="step" id="step-3"><span class="step-num">3</span>Obligations</div>
    <div class="step" id="step-4"><span class="step-num">4</span>Decision</div>
  </div>

  <!-- Form -->
  <form id="loanForm">

    <!-- Personal info -->
    <div class="form-section">
      <div class="form-section-header">
        <div class="form-section-icon">👤</div>
        <span class="form-section-title">Personal Information</span>
      </div>
      <div class="form-section-body">
        <div class="grid-2">
          <div class="field">
            <label>Full Name <span class="req">*</span></label>
            <input name="applicant_name" required placeholder="e.g. Adaeze Okonkwo">
          </div>
          <div class="field">
            <label>Phone Number <span class="req">*</span></label>
            <input name="phone" required placeholder="08012345678" inputmode="tel">
          </div>
          <div class="field">
            <label>Occupation <span class="req">*</span></label>
            <input name="occupation" required placeholder="e.g. Market Trader, Civil Servant">
          </div>
          <div class="field">
            <label>Employment Type <span class="req">*</span></label>
            <select name="employment_type" required>
              <option value="">— Select type —</option>
              <option value="salaried">Salaried (Private Sector)</option>
              <option value="civil_servant">Civil Servant / Government</option>
              <option value="self_employed">Self-Employed / Business Owner</option>
              <option value="trader">Market Trader</option>
              <option value="transport">Transport / Logistics</option>
            </select>
          </div>
          <div class="field">
            <label>Employer / Business Name <span class="req">*</span></label>
            <input name="employer_or_business" required placeholder="e.g. GTBank, MTN, Mama Nkechi Stores">
          </div>
          <div class="field">
            <label>Stated Monthly Income (₦) <span class="req">*</span></label>
            <input name="monthly_income_ngn" type="number" required min="0" placeholder="150000" inputmode="numeric">
          </div>
        </div>
        <div class="field" style="margin-top:14px;">
          <label>Residential Address <span class="req">*</span></label>
          <input name="address" required placeholder="e.g. 14 Bode Thomas Street, Surulere, Lagos">
        </div>
      </div>
    </div>

    <!-- Loan details -->
    <div class="form-section">
      <div class="form-section-header">
        <div class="form-section-icon">💰</div>
        <span class="form-section-title">Loan Request</span>
      </div>
      <div class="form-section-body">
        <div class="grid-2">
          <div class="field">
            <label>Loan Amount Requested (₦) <span class="req">*</span></label>
            <input name="loan_amount_ngn" type="number" required min="0" placeholder="500000" inputmode="numeric">
          </div>
          <div class="field">
            <label>Repayment Period <span class="req">*</span></label>
            <select name="loan_tenure_months" required>
              <option value="1">1 month</option>
              <option value="3">3 months</option>
              <option value="6">6 months</option>
              <option value="12" selected>12 months</option>
              <option value="18">18 months</option>
              <option value="24">24 months</option>
              <option value="36">36 months</option>
            </select>
          </div>
        </div>
        <div class="field" style="margin-top:14px;">
          <label>Loan Purpose <span class="req">*</span> — Be specific</label>
          <textarea name="loan_purpose" required placeholder="e.g. Purchase additional stock (tomatoes, onions, peppers) for my provision store at Mile 12 Market before the December season"></textarea>
        </div>
        <div class="grid-2" style="margin-top:14px;">
          <div class="field">
            <label>Collateral Offered (if any)</label>
            <input name="collateral_description" placeholder="e.g. Toyota Camry 2015 (₦3.5m)">
          </div>
          <div class="field">
            <label>Guarantor Name (if any)</label>
            <input name="guarantor_name" placeholder="Full name of guarantor">
          </div>
        </div>
      </div>
    </div>

    <!-- Financial obligations -->
    <div class="form-section">
      <div class="form-section-header">
        <div class="form-section-icon">📋</div>
        <span class="form-section-title">Existing Financial Obligations</span>
      </div>
      <div class="form-section-body">
        <div class="grid-2">
          <div class="field">
            <label>Number of Active Loans</label>
            <input name="existing_loan_count" type="number" min="0" value="0" inputmode="numeric">
          </div>
          <div class="field">
            <label>Total Monthly Repayments (₦)</label>
            <input name="existing_monthly_obligations_ngn" type="number" min="0" value="0" placeholder="0" inputmode="numeric">
          </div>
        </div>
        <div class="field" style="margin-top:14px;">
          <label>Previous Loan History</label>
          <textarea name="loan_history" placeholder="e.g. Repaid ₦200,000 with Lapo MFB in 2023 with no defaults. No previous loan defaults. First-time borrower."></textarea>
        </div>
      </div>
    </div>

    <!-- Submit -->
    <div class="submit-wrap">
      <button type="submit" class="btn-submit" id="submitBtn">
        Submit Application — Get Instant Decision
      </button>
      <p class="disclaimer">
        By submitting, you confirm all information is accurate and true.<br>
        False declarations may result in blacklisting from participating lenders.<br>
        Your data is encrypted and handled under NDPR regulations.
      </p>
    </div>

  </form>

  <!-- Result screen (hidden until submission) -->
  <div id="resultScreen">
    <div id="rBandWrap" class="result-band-wrap band-A" style="display:none;"></div>
    <div id="rIcon" class="result-icon"></div>
    <div id="rDecision" class="result-decision-label"></div>
    <p id="rRationale" class="result-rationale"></p>
    <div id="rTerms" style="display:none;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:14px 18px;max-width:420px;margin:0 auto 16px;text-align:left;">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:10px;">Recommended Terms</div>
      <div id="rTermsBody" style="font-size:13px;color:var(--text);line-height:1.8;"></div>
    </div>
    <div id="rConditions" class="result-conditions" style="display:none;">
      <div class="result-conditions-title">Conditions Before Disbursement</div>
      <ul id="rConditionsList"></ul>
    </div>
    <div id="rRef" class="result-ref"></div>
  </div>

</div><!-- .page -->

<script>
// Step progress tracker
const NUMERIC = ['monthly_income_ngn','loan_amount_ngn','loan_tenure_months','existing_loan_count','existing_monthly_obligations_ngn'];

function activateStep(n) {
  for (let i = 1; i <= 4; i++) {
    const s = document.getElementById('step-'+i);
    s.classList.remove('active','done');
    if (i < n) s.classList.add('done');
    else if (i === n) s.classList.add('active');
  }
}

// Live step detection based on filled fields
document.querySelectorAll('input,select,textarea').forEach(el => {
  el.addEventListener('input', () => {
    const form = document.getElementById('loanForm');
    const p = form.querySelector('[name=applicant_name]').value;
    const l = form.querySelector('[name=loan_amount_ngn]').value;
    const o = form.querySelector('[name=loan_purpose]').value;
    if (o) activateStep(3);
    else if (l) activateStep(2);
    else if (p) activateStep(2);
  });
});

document.getElementById('loanForm').addEventListener('submit', async function(e) {
  e.preventDefault();

  activateStep(4);
  document.getElementById('processingOverlay').style.display = 'flex';

  const fd = new FormData(this);
  const payload = {};
  for (const [k,v] of fd.entries()) {
    payload[k] = NUMERIC.includes(k) ? parseFloat(v) || 0 : v;
  }

  try {
    const resp = await fetch('/loan/apply', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Submission failed');

    document.getElementById('processingOverlay').style.display = 'none';
    this.style.display = 'none';
    document.querySelector('.hero').style.display = 'none';
    document.querySelector('.trust-bar').style.display = 'none';
    document.querySelector('.steps').style.display = 'none';

    const rs = document.getElementById('resultScreen');
    rs.style.display = 'block';

    // Band badge
    const band = data.risk_band;
    const bw = document.getElementById('rBandWrap');
    bw.textContent = band;
    bw.className = 'result-band-wrap band-' + band;
    bw.style.display = 'flex';

    // Decision
    const decEl = document.getElementById('rDecision');
    const decColors = {Approve:'result-decision-approve',Refer:'result-decision-refer',Decline:'result-decision-decline'};
    const decLabels = {Approve:'Approved','Refer':'Referred for Review',Decline:'Not Approved at This Time'};
    decEl.textContent = decLabels[data.decision] || data.decision;
    decEl.className = 'result-decision-label ' + (decColors[data.decision]||'');

    // Icon
    document.getElementById('rIcon').textContent = {Approve:'✅',Refer:'⏳',Decline:'❌'}[data.decision]||'📋';

    // Rationale
    document.getElementById('rRationale').textContent = data.rationale || '';

    // Terms
    if (data.decision === 'Approve' && data.recommended_amount_ngn) {
      const fmt = n => '₦' + Number(n).toLocaleString('en-NG');
      document.getElementById('rTermsBody').innerHTML =
        '<div><strong>Amount:</strong> ' + fmt(data.recommended_amount_ngn) + '</div>' +
        '<div><strong>Tenure:</strong> ' + data.recommended_tenure_months + ' months</div>' +
        '<div><strong>Rate:</strong> ' + data.recommended_rate_pct + '% p.a.</div>';
      document.getElementById('rTerms').style.display = 'block';
    }

    // Conditions
    if (data.conditions && data.conditions.length) {
      const ul = document.getElementById('rConditionsList');
      ul.innerHTML = data.conditions.map(c => '<li>' + c + '</li>').join('');
      document.getElementById('rConditions').style.display = 'block';
    }

    // Ref
    document.getElementById('rRef').textContent = 'REF: ' + data.id;

  } catch(err) {
    document.getElementById('processingOverlay').style.display = 'none';
    alert('Submission error: ' + err.message);
    document.getElementById('submitBtn').disabled = false;
    document.getElementById('submitBtn').textContent = 'Submit Application — Get Instant Decision';
    activateStep(1);
  }
});
</script>
</body>
</html>"""
