"""
Digital Associates — AI contract review for Lagos law firms.
Upload a contract PDF → get a structured review memo in under 60 seconds.
Third product line inside ReachNG.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from services.legal_review.extractor import _extract_pdf_text, extract_clauses
from services.legal_review.memo import generate_memo
from services.legal_review.store import save_review, get_review, list_reviews

router = APIRouter(prefix="/legal", tags=["Digital Associates"])


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post("/review")
async def review_contract(
    file: UploadFile = File(...),
    firm_name: str = Form(default=""),
):
    """
    Upload a contract PDF → returns extracted clauses + full review memo.
    Typical turnaround: 30-60 seconds depending on document length.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(400, "File too large. Maximum 20MB.")

    # Step 1: Extract text
    contract_text = _extract_pdf_text(content)
    if not contract_text.strip():
        raise HTTPException(422, "Could not extract text from PDF. Ensure the PDF is not scanned/image-only.")

    # Step 2: Extract clauses
    clauses = extract_clauses(contract_text, file.filename)

    # Step 3: Generate memo
    memo = generate_memo(
        filename=file.filename,
        clauses=clauses,
        firm_name=firm_name,
    )

    # Step 4: Persist
    overall_risk = clauses.get("overall_risk", "unknown")
    review_id = save_review(
        firm_name=firm_name or "anonymous",
        filename=file.filename,
        clauses=clauses,
        memo=memo,
        overall_risk=overall_risk,
    )

    return {
        "review_id":          review_id,
        "filename":           file.filename,
        "firm_name":          firm_name,
        "overall_risk":       overall_risk,
        "overall_summary":    clauses.get("overall_summary", ""),
        "contract_type":      clauses.get("contract_type", "general"),
        "contract_type_label": clauses.get("contract_type_label", "Commercial Agreement"),
        "red_flags":          clauses.get("red_flags", []),
        "nigerian_law_issues": clauses.get("nigerian_law_issues", []),
        "stamp_duty_required": clauses.get("stamp_duty_required", False),
        "memo":               memo,
        "clauses":            clauses,
    }


@router.get("/reviews")
async def get_reviews(firm_name: str | None = None, limit: int = 20):
    """List review history, optionally filtered by firm name."""
    return list_reviews(firm_name=firm_name, limit=limit)


@router.get("/reviews/{review_id}")
async def get_single_review(review_id: str):
    """Retrieve a specific review by ID — includes full memo and clause data."""
    doc = get_review(review_id)
    if not doc:
        raise HTTPException(404, "Review not found.")
    return doc


# ── Upload portal — clean standalone page for law firm associates ─────────────

_PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Digital Associates — AI Contract Review</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f7f6f3;
    color: #1a1a1a;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 48px 24px;
  }

  .header { text-align: center; margin-bottom: 48px; }
  .logo { font-size: 13px; font-weight: 600; letter-spacing: 2px; color: #888; text-transform: uppercase; margin-bottom: 12px; }
  .title { font-size: 32px; font-weight: 700; color: #1a1a1a; margin-bottom: 8px; letter-spacing: -0.5px; }
  .subtitle { font-size: 16px; color: #666; max-width: 480px; line-height: 1.6; }

  .card {
    background: #fff;
    border: 1px solid #e5e5e5;
    border-radius: 16px;
    padding: 40px;
    width: 100%;
    max-width: 600px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  }

  .field { margin-bottom: 20px; }
  .field label { display: block; font-size: 13px; font-weight: 600; color: #444; margin-bottom: 6px; letter-spacing: 0.3px; }
  .field input {
    width: 100%; padding: 12px 14px;
    border: 1px solid #ddd; border-radius: 8px;
    font-size: 15px; color: #1a1a1a;
    font-family: inherit; outline: none;
    transition: border-color 0.15s;
  }
  .field input:focus { border-color: #1a1a1a; }

  .upload-area {
    border: 2px dashed #ddd; border-radius: 12px;
    padding: 40px 24px; text-align: center;
    cursor: pointer; transition: all 0.2s;
    background: #fafafa;
  }
  .upload-area:hover, .upload-area.drag { border-color: #1a1a1a; background: #f0f0f0; }
  .upload-area.has-file { border-color: #00a651; background: #f0fff6; border-style: solid; }

  .upload-icon { font-size: 36px; margin-bottom: 12px; }
  .upload-text { font-size: 15px; color: #666; }
  .upload-text strong { color: #1a1a1a; }
  .file-name { font-size: 14px; color: #00a651; font-weight: 600; margin-top: 8px; }

  #file-input { display: none; }

  .btn {
    width: 100%; padding: 14px;
    background: #1a1a1a; color: #fff;
    border: none; border-radius: 10px;
    font-size: 16px; font-weight: 600;
    cursor: pointer; margin-top: 24px;
    transition: opacity 0.15s; font-family: inherit;
  }
  .btn:hover { opacity: 0.85; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .progress { display: none; text-align: center; padding: 24px 0; }
  .spinner {
    width: 40px; height: 40px;
    border: 3px solid #eee; border-top-color: #1a1a1a;
    border-radius: 50%; animation: spin 0.8s linear infinite;
    margin: 0 auto 16px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .progress-text { font-size: 14px; color: #666; }

  /* ── Result ── */
  .result { display: none; margin-top: 0; }

  .risk-banner {
    border-radius: 10px; padding: 16px 20px;
    margin-bottom: 24px; display: flex;
    align-items: center; gap: 12px;
  }
  .risk-low      { background: #f0fff6; border: 1px solid #00a651; }
  .risk-medium   { background: #fffbf0; border: 1px solid #f5a623; }
  .risk-high     { background: #fff5f5; border: 1px solid #e53e3e; }
  .risk-critical { background: #fff0f0; border: 1px solid #c53030; }
  .risk-emoji    { font-size: 24px; }
  .risk-label    { font-size: 15px; font-weight: 600; }
  .risk-summary  { font-size: 13px; color: #555; margin-top: 2px; }

  .memo-box {
    background: #fafafa; border: 1px solid #e5e5e5;
    border-radius: 10px; padding: 24px;
    font-size: 14px; line-height: 1.8; color: #2a2a2a;
    white-space: pre-wrap; max-height: 500px;
    overflow-y: auto; font-family: 'Georgia', serif;
  }

  .action-row { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
  .btn-outline {
    flex: 1; padding: 11px; border: 1px solid #ddd;
    border-radius: 8px; font-size: 13px; font-weight: 600;
    cursor: pointer; background: #fff; color: #1a1a1a;
    font-family: inherit; transition: all 0.15s; text-align: center;
  }
  .btn-outline:hover { border-color: #1a1a1a; }

  .error-box {
    background: #fff5f5; border: 1px solid #e53e3e;
    border-radius: 10px; padding: 16px 20px;
    color: #c53030; font-size: 14px; display: none;
    margin-top: 16px;
  }

  .reset-btn {
    background: none; border: none; color: #888;
    font-size: 13px; cursor: pointer; margin-top: 20px;
    text-decoration: underline; font-family: inherit;
    display: block; margin-left: auto; margin-right: auto;
  }

  .stats { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  .stat { flex: 1; background: #f7f6f3; border-radius: 8px; padding: 12px 16px; min-width: 120px; }
  .stat .s-val { font-size: 20px; font-weight: 700; }
  .stat .s-lbl { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }

  footer { margin-top: 48px; font-size: 12px; color: #aaa; text-align: center; }
</style>
</head>
<body>

<div class="header">
  <div class="logo">Digital Associates</div>
  <div class="title">AI Contract Review</div>
  <div class="subtitle">Upload a contract. Get a structured review memo in under 60 seconds — same rigour, a fraction of the time.</div>
</div>

<div class="card" id="upload-card">
  <div class="field">
    <label>Firm Name</label>
    <input type="text" id="firm-name" placeholder="e.g. Banwo & Ighodalo" />
  </div>

  <div class="field">
    <label>Contract PDF</label>
    <div class="upload-area" id="upload-area" onclick="document.getElementById('file-input').click()"
         ondragover="event.preventDefault();this.classList.add('drag')"
         ondragleave="this.classList.remove('drag')"
         ondrop="handleDrop(event)">
      <div class="upload-icon">📄</div>
      <div class="upload-text"><strong>Click to upload</strong> or drag and drop</div>
      <div class="upload-text" style="font-size:12px;margin-top:4px;">PDF only · Max 20MB</div>
      <div class="file-name" id="file-name" style="display:none;"></div>
    </div>
    <input type="file" id="file-input" accept=".pdf" onchange="handleFileSelect(this)" />
  </div>

  <div style="margin-bottom:20px;padding:14px 16px;background:#f7f6f3;border:1px solid #e0e0e0;border-radius:8px;display:flex;align-items:flex-start;gap:10px;">
    <input type="checkbox" id="disclaimer-check" onchange="document.getElementById('submit-btn').disabled=!this.checked||!selectedFile" style="margin-top:3px;width:auto;cursor:pointer;flex-shrink:0;" />
    <label for="disclaimer-check" style="font-size:12px;color:#555;line-height:1.5;cursor:pointer;">
      I understand this review is generated by AI and has not been verified by a qualified legal practitioner.
      It should not be relied upon as legal advice. Significant decisions based on this analysis should be reviewed
      by a Nigerian-qualified solicitor. Digital Associates AI accepts no liability for errors or omissions.
    </label>
  </div>

  <button class="btn" id="submit-btn" onclick="submitReview()" disabled>
    Review Contract →
  </button>

  <div class="progress" id="progress">
    <div class="spinner"></div>
    <div class="progress-text" id="progress-text">Extracting clauses…</div>
  </div>

  <div class="error-box" id="error-box"></div>
</div>

<!-- Result card -->
<div class="card result" id="result-card" style="margin-top:24px;">
  <div class="risk-banner" id="risk-banner">
    <span class="risk-emoji" id="risk-emoji"></span>
    <div>
      <div class="risk-label" id="risk-label"></div>
      <div class="risk-summary" id="risk-summary"></div>
    </div>
  </div>

  <div class="stats" id="stats-row"></div>

  <div style="font-size:13px;font-weight:600;color:#444;margin-bottom:10px;letter-spacing:0.3px;">REVIEW MEMO</div>
  <div class="memo-box" id="memo-box"></div>

  <div class="action-row">
    <button class="btn-outline" onclick="copyMemo()">📋 Copy Memo</button>
    <button class="btn-outline" onclick="downloadMemo()">⬇️ Download .txt</button>
  </div>

  <button class="reset-btn" onclick="resetForm()">← Review another contract</button>
</div>

<footer>Digital Associates AI · Powered by ReachNG · For review purposes only — not legal advice</footer>

<script>
let selectedFile = null;
let lastMemo = "";
let lastFilename = "";

function handleFileSelect(input) {
  if (input.files && input.files[0]) setFile(input.files[0]);
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById("upload-area").classList.remove("drag");
  const f = e.dataTransfer.files[0];
  if (f && f.name.toLowerCase().endsWith(".pdf")) setFile(f);
}

function setFile(f) {
  selectedFile = f;
  const area = document.getElementById("upload-area");
  area.classList.add("has-file");
  const fn = document.getElementById("file-name");
  fn.style.display = "block";
  fn.textContent = "✓ " + f.name + " (" + (f.size / 1024).toFixed(0) + " KB)";
  const checked = document.getElementById("disclaimer-check").checked;
  document.getElementById("submit-btn").disabled = !checked;
}

const RISK_CONFIG = {
  low:      { emoji: "🟢", label: "Low Risk", cls: "risk-low" },
  medium:   { emoji: "🟡", label: "Medium Risk", cls: "risk-medium" },
  high:     { emoji: "🔴", label: "High Risk", cls: "risk-high" },
  critical: { emoji: "🚨", label: "Critical Risk", cls: "risk-critical" },
};

async function submitReview() {
  if (!selectedFile) return;

  const btn      = document.getElementById("submit-btn");
  const progress = document.getElementById("progress");
  const errBox   = document.getElementById("error-box");

  btn.disabled = true;
  btn.style.display = "none";
  progress.style.display = "block";
  errBox.style.display = "none";

  const steps = ["Extracting text from PDF…", "Identifying clauses…", "Analysing risk language…", "Generating review memo…"];
  let step = 0;
  const ticker = setInterval(() => {
    step = (step + 1) % steps.length;
    document.getElementById("progress-text").textContent = steps[step];
  }, 4000);

  try {
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("firm_name", document.getElementById("firm-name").value.trim());

    const r = await fetch("/legal/review", { method: "POST", body: form });
    clearInterval(ticker);

    if (!r.ok) {
      const err = await r.json();
      throw new Error(err.detail || "Review failed");
    }

    const data = await r.json();
    showResult(data);

  } catch (err) {
    clearInterval(ticker);
    progress.style.display = "none";
    btn.style.display = "block";
    btn.disabled = false;
    errBox.style.display = "block";
    errBox.textContent = "Error: " + err.message;
  }
}

function showResult(data) {
  document.getElementById("progress").style.display = "none";

  const risk   = (data.overall_risk || "low").toLowerCase();
  const cfg    = RISK_CONFIG[risk] || RISK_CONFIG.low;
  const banner = document.getElementById("risk-banner");
  banner.className = "risk-banner " + cfg.cls;
  document.getElementById("risk-emoji").textContent  = cfg.emoji;
  document.getElementById("risk-label").textContent  = cfg.label + " — " + (data.filename || "");
  document.getElementById("risk-summary").textContent = data.overall_summary || "";

  // Stats
  const skipKeys = new Set(["overall_risk","overall_summary","red_flags","nigerian_law_issues","stamp_duty_required","contract_type","contract_type_label","parse_error","raw"]);
  const clauseKeys = Object.keys(data.clauses || {}).filter(k => !skipKeys.has(k));
  const found      = clauseKeys.filter(k => data.clauses[k] && data.clauses[k].found).length;
  const redFlags   = (data.red_flags || []).length;
  const ngIssues   = (data.clauses?.nigerian_law_issues || []).length;
  const stampDuty  = data.clauses?.stamp_duty_required;

  document.getElementById("stats-row").innerHTML = `
    <div class="stat"><div class="s-val">${found}</div><div class="s-lbl">Clauses Found</div></div>
    <div class="stat"><div class="s-val">${redFlags}</div><div class="s-lbl">Red Flags</div></div>
    <div class="stat"><div class="s-val">${ngIssues}</div><div class="s-lbl">Law Issues</div></div>
    ${stampDuty ? '<div class="stat" style="border:1px solid #f5a623;"><div class="s-val" style="font-size:14px;color:#f5a623;">⚠️ YES</div><div class="s-lbl">Stamp Duty</div></div>' : ''}
    <div class="stat"><div class="s-val" style="font-size:14px;">${data.contract_type_label || "—"}</div><div class="s-lbl">Contract Type</div></div>
  `;

  lastMemo     = data.memo || "";
  lastFilename = data.filename || "review";
  document.getElementById("memo-box").textContent = lastMemo;

  document.getElementById("result-card").style.display = "block";
  document.getElementById("result-card").scrollIntoView({ behavior: "smooth" });
}

function copyMemo() {
  navigator.clipboard.writeText(lastMemo);
  event.target.textContent = "✓ Copied!";
  setTimeout(() => event.target.textContent = "📋 Copy Memo", 1500);
}

function downloadMemo() {
  const blob = new Blob([lastMemo], { type: "text/plain" });
  const a    = document.createElement("a");
  a.href     = URL.createObjectURL(blob);
  a.download = lastFilename.replace(".pdf", "") + "_review_memo.txt";
  a.click();
}

function resetForm() {
  selectedFile = null;
  document.getElementById("file-input").value = "";
  document.getElementById("upload-area").classList.remove("has-file");
  document.getElementById("file-name").style.display = "none";
  document.getElementById("submit-btn").disabled = true;
  document.getElementById("submit-btn").style.display = "block";
  document.getElementById("result-card").style.display = "none";
  document.getElementById("firm-name").value = "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}
</script>
</body>
</html>"""


@router.get("/portal", response_class=HTMLResponse)
async def legal_portal():
    """Clean upload portal for law firm associates — no login required for demo."""
    return HTMLResponse(content=_PORTAL_HTML)
