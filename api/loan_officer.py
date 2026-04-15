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
  <title>Loan Application</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f1f5f9; min-height: 100vh; padding: 32px 16px; color: #1e293b; }
    .card { max-width: 680px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.10); overflow: hidden; }
    .header { background: #1e293b; padding: 24px 32px; }
    .header h1 { color: white; font-size: 22px; font-weight: 700; }
    .header p { color: #94a3b8; font-size: 14px; margin-top: 4px; }
    .body { padding: 28px 32px; }
    .section-title { font-size: 13px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .06em; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #e2e8f0; }
    .section-title:first-child { margin-top: 0; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media(max-width:520px){ .grid-2{ grid-template-columns:1fr; } }
    label { display: block; font-size: 13px; font-weight: 500; color: #374151; margin-bottom: 4px; }
    label span { color: #dc2626; }
    input, select, textarea { width: 100%; padding: 9px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; color: #1e293b; outline: none; transition: border .15s; }
    input:focus, select:focus, textarea:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px #dbeafe; }
    textarea { resize: vertical; min-height: 72px; }
    .btn { width: 100%; margin-top: 28px; padding: 14px; background: #1e293b; color: white; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background .15s; }
    .btn:hover { background: #0f172a; }
    .btn:disabled { background: #94a3b8; cursor: not-allowed; }
    #result { display:none; margin-top:24px; padding:20px; border-radius:8px; }
    .result-approve { background:#dcfce7; border:1px solid #16a34a33; }
    .result-refer   { background:#fef3c7; border:1px solid #d9770633; }
    .result-decline { background:#fee2e2; border:1px solid #dc262633; }
    .result-band { font-size:40px; font-weight:800; line-height:1; }
    .result-decision { font-size:22px; font-weight:700; }
    .result-note { font-size:13px; margin-top:8px; color:#475569; }
    .result-id  { font-size:12px; margin-top:12px; color:#94a3b8; }
  </style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>Loan Application Form</h1>
    <p>Fill in all required fields accurately. Your application will be assessed immediately.</p>
  </div>
  <div class="body">
    <form id="loanForm">

      <div class="section-title">Personal Information</div>
      <div class="grid-2">
        <div>
          <label>Full Name <span>*</span></label>
          <input name="applicant_name" required placeholder="e.g. Adaeze Okonkwo">
        </div>
        <div>
          <label>Phone Number <span>*</span></label>
          <input name="phone" required placeholder="08012345678">
        </div>
        <div>
          <label>Occupation <span>*</span></label>
          <input name="occupation" required placeholder="e.g. Market Trader">
        </div>
        <div>
          <label>Employment Type <span>*</span></label>
          <select name="employment_type" required>
            <option value="">— Select —</option>
            <option value="salaried">Salaried (Private Sector)</option>
            <option value="civil_servant">Civil Servant</option>
            <option value="self_employed">Self-Employed / Business Owner</option>
            <option value="trader">Market Trader</option>
            <option value="transport">Transport / Logistics</option>
          </select>
        </div>
        <div>
          <label>Employer / Business Name <span>*</span></label>
          <input name="employer_or_business" required placeholder="e.g. GTBank or Mama Nkechi Stores">
        </div>
        <div>
          <label>Monthly Income (₦) <span>*</span></label>
          <input name="monthly_income_ngn" type="number" required min="0" placeholder="e.g. 150000">
        </div>
      </div>
      <div style="margin-top:16px;">
        <label>Residential Address <span>*</span></label>
        <input name="address" required placeholder="e.g. 14 Bode Thomas Street, Surulere, Lagos">
      </div>

      <div class="section-title">Loan Details</div>
      <div class="grid-2">
        <div>
          <label>Loan Amount (₦) <span>*</span></label>
          <input name="loan_amount_ngn" type="number" required min="0" placeholder="e.g. 500000">
        </div>
        <div>
          <label>Repayment Period (months) <span>*</span></label>
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
      <div style="margin-top:16px;">
        <label>Loan Purpose <span>*</span></label>
        <textarea name="loan_purpose" required placeholder="e.g. Purchase stock for my provision store before the festive season"></textarea>
      </div>
      <div style="margin-top:16px;">
        <label>Collateral Offered (if any)</label>
        <input name="collateral_description" placeholder="e.g. Toyota Camry 2015 (valued ₦3.5m) or leave blank">
      </div>
      <div style="margin-top:16px;">
        <label>Guarantor Name (if any)</label>
        <input name="guarantor_name" placeholder="Full name of guarantor">
      </div>

      <div class="section-title">Existing Financial Obligations</div>
      <div class="grid-2">
        <div>
          <label>Number of Existing Loans</label>
          <input name="existing_loan_count" type="number" min="0" value="0">
        </div>
        <div>
          <label>Total Monthly Loan Repayments (₦)</label>
          <input name="existing_monthly_obligations_ngn" type="number" min="0" value="0" placeholder="0">
        </div>
      </div>

      <div class="section-title">Previous Loan History</div>
      <textarea name="loan_history" placeholder="e.g. Repaid ₦200,000 loan with Lapo MFB in 2023 with no defaults. Or: First-time borrower."></textarea>

      <button type="submit" class="btn" id="submitBtn">Submit Application</button>
    </form>

    <div id="result">
      <div class="result-band" id="rBand"></div>
      <div class="result-decision" id="rDecision"></div>
      <div class="result-note" id="rNote"></div>
      <div class="result-id" id="rId"></div>
    </div>
  </div>
</div>

<script>
document.getElementById('loanForm').addEventListener('submit', async function(e) {
  e.preventDefault();
  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  btn.textContent = 'Processing…';

  const fd = new FormData(this);
  const payload = {};
  for (const [k,v] of fd.entries()) {
    payload[k] = ['monthly_income_ngn','loan_amount_ngn','loan_tenure_months',
                  'existing_loan_count','existing_monthly_obligations_ngn'].includes(k)
                 ? parseFloat(v) || 0 : v;
  }

  try {
    const resp = await fetch('/loan/apply', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await resp.json();

    if (!resp.ok) throw new Error(data.detail || 'Submission failed');

    const res = document.getElementById('result');
    const cls = {Approve:'result-approve', Refer:'result-refer', Decline:'result-decline'}[data.decision] || 'result-refer';
    res.className = cls;

    const bandLabels = {A:'Excellent',B:'Good',C:'Elevated',D:'High Risk'};
    document.getElementById('rBand').textContent = data.risk_band;
    document.getElementById('rDecision').textContent = data.decision;
    document.getElementById('rNote').textContent = data.rationale || '';
    document.getElementById('rId').textContent = 'Reference: ' + data.id;
    res.style.display = 'block';

    btn.textContent = 'Submitted';
    btn.disabled = true;
    this.style.display = 'none';
  } catch(err) {
    alert('Error: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Submit Application';
  }
});
</script>
</body>
</html>"""
