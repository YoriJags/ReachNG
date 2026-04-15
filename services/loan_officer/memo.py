"""
AI Loan Officer — decision memo generator.

Takes a scored application and produces a formatted HTML memo
suitable for printing or emailing to the credit committee.
"""
from datetime import datetime


# ── Band styling ──────────────────────────────────────────────────────────────

_BAND_COLORS = {
    "A": ("#16a34a", "#dcfce7"),   # green
    "B": ("#2563eb", "#dbeafe"),   # blue
    "C": ("#d97706", "#fef3c7"),   # amber
    "D": ("#dc2626", "#fee2e2"),   # red
}

_DECISION_COLORS = {
    "Approve": "#16a34a",
    "Refer":   "#d97706",
    "Decline": "#dc2626",
}

_FLAG_COLORS = {
    "green":    ("#16a34a", "#dcfce7"),
    "amber":    ("#d97706", "#fef3c7"),
    "red":      ("#dc2626", "#fee2e2"),
    "critical": ("#7c2d12", "#fecdd3"),
}


def _flag_badge(flag: str, value) -> str:
    fg, bg = _FLAG_COLORS.get(flag, ("#374151", "#f3f4f6"))
    label = str(value).upper() if flag in ("critical", "red") else str(value)
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:4px;font-size:12px;font-weight:600;">{label}</span>'
    )


def generate_memo(app: dict, score: dict, mfb_name: str = "MFB") -> str:
    """
    Returns a standalone HTML string — the full credit decision memo.

    Parameters
    ----------
    app   : original application dict (from form submission)
    score : output of scorer.score_application(app)
    mfb_name : lender name for the header
    """
    band      = score.get("risk_band", "D")
    decision  = score.get("decision", "Decline")
    band_fg, band_bg   = _BAND_COLORS.get(band, ("#374151", "#f3f4f6"))
    dec_color = _DECISION_COLORS.get(decision, "#374151")

    computed  = score.get("computed", {})
    factors   = score.get("factors", {})
    hard_flag = score.get("hard_decline_triggered", False)
    now       = datetime.now().strftime("%d %B %Y, %H:%M")

    # ── Factor table rows ──────────────────────────────────────────────────
    factor_rows = ""
    factor_labels = {
        "dti":           "Debt-to-Income Ratio",
        "lti":           "Loan-to-Income Multiple",
        "loan_stacking": "Loan Stacking Risk",
        "loan_purpose":  "Loan Purpose",
        "collateral":    "Collateral",
    }
    for key, label in factor_labels.items():
        f = factors.get(key, {})
        if not f:
            continue
        badge = _flag_badge(f.get("flag", ""), f.get("value", ""))
        note  = f.get("note", "")
        factor_rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#374151;">{label}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{badge}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;font-size:13px;">{note}</td>
        </tr>"""

    # ── List items ─────────────────────────────────────────────────────────
    def bullet_list(items: list, color: str = "#374151") -> str:
        if not items:
            return "<p style='color:#9ca3af;font-style:italic;'>None identified.</p>"
        lis = "".join(f'<li style="margin-bottom:4px;color:{color};">{i}</li>' for i in items)
        return f'<ul style="margin:0;padding-left:20px;">{lis}</ul>'

    red_flags = score.get("red_flags", [])
    strengths = score.get("strengths", [])
    conditions = score.get("conditions", [])

    hard_decline_banner = ""
    if hard_flag:
        hard_decline_banner = """
        <div style="background:#fef2f2;border-left:4px solid #dc2626;padding:12px 16px;margin-bottom:20px;border-radius:4px;">
          <strong style="color:#dc2626;">HARD DECLINE TRIGGERED</strong>
          <p style="margin:4px 0 0;color:#991b1b;font-size:13px;">
            Rules engine flagged DTI &gt; 50% or 3+ concurrent loans. Claude analysis provided for context only.
          </p>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Loan Decision Memo — {app.get('applicant_name', 'Applicant')}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f9fafb; color: #111827; }}
    .page {{ max-width: 860px; margin: 32px auto; background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.12); overflow: hidden; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th {{ text-align: left; }}
  </style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div style="background:#1e293b;padding:24px 32px;display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="color:#94a3b8;font-size:11px;letter-spacing:.08em;text-transform:uppercase;">{mfb_name}</div>
      <div style="color:white;font-size:20px;font-weight:700;margin-top:4px;">Loan Credit Decision Memo</div>
    </div>
    <div style="text-align:right;">
      <div style="color:#94a3b8;font-size:12px;">Generated</div>
      <div style="color:white;font-size:13px;">{now}</div>
    </div>
  </div>

  <div style="padding:28px 32px;">

    {hard_decline_banner}

    <!-- Decision strip -->
    <div style="display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap;">
      <div style="flex:1;min-width:140px;background:{band_bg};border:1px solid {band_fg}33;border-radius:8px;padding:16px 20px;text-align:center;">
        <div style="font-size:11px;color:{band_fg};text-transform:uppercase;letter-spacing:.06em;font-weight:600;">Risk Band</div>
        <div style="font-size:48px;font-weight:800;color:{band_fg};line-height:1.1;">{band}</div>
        <div style="font-size:12px;color:{band_fg};opacity:.8;">
          {{"A":"Excellent","B":"Good","C":"Elevated","D":"High Risk"}}.get("{band}","")
        </div>
      </div>
      <div style="flex:2;min-width:200px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;">
        <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.06em;font-weight:600;">Decision</div>
        <div style="font-size:28px;font-weight:700;color:{dec_color};margin:4px 0;">{decision}</div>
        <div style="font-size:13px;color:#64748b;">Confidence: <strong>{score.get('confidence','—').title()}</strong></div>
      </div>
      <div style="flex:2;min-width:200px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;">
        <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.06em;font-weight:600;">Recommended Terms</div>
        <div style="font-size:14px;margin-top:6px;color:#1e293b;">
          <div><strong>Amount:</strong> ₦{score.get('recommended_amount_ngn', 0):,.0f}</div>
          <div><strong>Tenure:</strong> {score.get('recommended_tenure_months', '—')} months</div>
          <div><strong>Rate:</strong> {score.get('recommended_rate_pct', '—')}% p.a.</div>
        </div>
      </div>
    </div>

    <!-- Applicant details -->
    <h3 style="font-size:14px;font-weight:600;color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:8px;margin-bottom:16px;">Applicant Details</h3>
    <table style="margin-bottom:24px;">
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;width:180px;">Name</td>
        <td style="padding:4px 0;font-size:13px;font-weight:600;">{app.get('applicant_name','—')}</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;width:180px;">Phone</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('phone','—')}</td>
      </tr>
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;">Occupation</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('occupation','—')}</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;">BVN Verified</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('bvn_verified','Not checked')}</td>
      </tr>
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;">Employer / Business</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('employer_or_business','—')}</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;">Employment Type</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('employment_type','—')}</td>
      </tr>
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;">Monthly Income</td>
        <td style="padding:4px 0;font-size:13px;font-weight:600;">₦{app.get('monthly_income_ngn',0):,.0f}</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;">Address</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('address','—')}</td>
      </tr>
    </table>

    <!-- Loan request -->
    <h3 style="font-size:14px;font-weight:600;color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:8px;margin-bottom:16px;">Loan Request</h3>
    <table style="margin-bottom:24px;">
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;width:180px;">Requested Amount</td>
        <td style="padding:4px 0;font-size:13px;font-weight:600;">₦{app.get('loan_amount_ngn',0):,.0f}</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;width:180px;">Purpose</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('loan_purpose','—')}</td>
      </tr>
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;">Tenure</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('loan_tenure_months',12)} months</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;">Collateral</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('collateral_description','None offered')}</td>
      </tr>
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;">Monthly Repayment</td>
        <td style="padding:4px 0;font-size:13px;font-weight:600;">₦{computed.get('monthly_repayment',0):,.0f}</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;">DTI After Loan</td>
        <td style="padding:4px 0;font-size:13px;">{computed.get('dti_pct','—')}%</td>
      </tr>
      <tr>
        <td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;">Guarantor</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('guarantor_name','None')}</td>
        <td style="padding:4px 12px 4px 24px;color:#6b7280;font-size:13px;">Existing Loans</td>
        <td style="padding:4px 0;font-size:13px;">{app.get('existing_loan_count',0)}</td>
      </tr>
    </table>

    <!-- Factor flags -->
    <h3 style="font-size:14px;font-weight:600;color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:8px;margin-bottom:0;">Risk Factor Assessment</h3>
    <table style="margin-bottom:24px;">
      <thead>
        <tr>
          <th style="padding:8px 12px;background:#f8fafc;font-size:12px;color:#6b7280;font-weight:600;">Factor</th>
          <th style="padding:8px 12px;background:#f8fafc;font-size:12px;color:#6b7280;font-weight:600;">Status</th>
          <th style="padding:8px 12px;background:#f8fafc;font-size:12px;color:#6b7280;font-weight:600;">Note</th>
        </tr>
      </thead>
      <tbody>{factor_rows}</tbody>
    </table>

    <!-- Two-column: red flags + strengths -->
    <div style="display:flex;gap:20px;margin-bottom:24px;flex-wrap:wrap;">
      <div style="flex:1;min-width:240px;">
        <h3 style="font-size:14px;font-weight:600;color:#dc2626;margin-bottom:10px;">Red Flags</h3>
        {bullet_list(red_flags, "#dc2626")}
      </div>
      <div style="flex:1;min-width:240px;">
        <h3 style="font-size:14px;font-weight:600;color:#16a34a;margin-bottom:10px;">Strengths</h3>
        {bullet_list(strengths, "#16a34a")}
      </div>
    </div>

    <!-- Rationale -->
    <h3 style="font-size:14px;font-weight:600;color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:8px;margin-bottom:12px;">Credit Officer Rationale</h3>
    <p style="color:#374151;line-height:1.6;font-size:14px;margin-bottom:24px;">{score.get('rationale','—')}</p>

    <!-- Conditions -->
    {'<h3 style="font-size:14px;font-weight:600;color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:8px;margin-bottom:12px;">Disbursement Conditions</h3>' + bullet_list(conditions) + '<div style="margin-bottom:24px;"></div>' if conditions else ''}

    <!-- Officer action -->
    <div style="background:#eff6ff;border-left:4px solid #2563eb;padding:14px 18px;border-radius:4px;margin-bottom:28px;">
      <strong style="color:#1e40af;font-size:13px;">NEXT ACTION FOR LOAN OFFICER</strong>
      <p style="color:#1e3a8a;margin:6px 0 0;font-size:14px;">{score.get('officer_action','—')}</p>
    </div>

    <!-- Footer -->
    <div style="border-top:1px solid #e5e7eb;padding-top:16px;display:flex;justify-content:space-between;color:#9ca3af;font-size:11px;">
      <span>Generated by ReachNG · AI Loan Officer</span>
      <span>This memo is for internal credit committee use only. Not for distribution to applicant.</span>
    </div>

  </div>
</div>
</body>
</html>"""

    return html


def generate_memo_text(app: dict, score: dict) -> str:
    """Plain-text version of the memo for WhatsApp/SMS notification."""
    band     = score.get("risk_band", "D")
    decision = score.get("decision", "Decline")
    computed = score.get("computed", {})

    lines = [
        f"LOAN DECISION — {app.get('applicant_name', 'Applicant')}",
        f"Band: {band}  |  Decision: {decision}  |  Confidence: {score.get('confidence','—')}",
        f"",
        f"Amount: ₦{score.get('recommended_amount_ngn', 0):,.0f}",
        f"Tenure: {score.get('recommended_tenure_months', '—')} months",
        f"Rate:   {score.get('recommended_rate_pct', '—')}% p.a.",
        f"DTI:    {computed.get('dti_pct', '—')}%",
        f"",
    ]
    if score.get("red_flags"):
        lines.append("RED FLAGS:")
        for f in score["red_flags"]:
            lines.append(f"  • {f}")
        lines.append("")

    lines.append(f"ACTION: {score.get('officer_action', '—')}")
    return "\n".join(lines)
