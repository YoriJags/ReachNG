"""
ReachNG-branded subscription receipts.

When a client pays for their ReachNG subscription via Paystack, we generate a
clean, on-brand HTML receipt (not Paystack's generic one), email it to them,
and store the record so they can re-download from their portal at any time.

Storage
-------
  subscription_receipts collection:
    { _id, client_id, client_name, owner_email, plan, plan_label,
      amount_ngn, paystack_reference, paid_at, annual,
      receipt_number, html  }

  receipt_number format: RNG-<YYYYMM>-<incrementing_pad>
  e.g. RNG-202605-0001, RNG-202605-0002

Public
------
  generate_receipt(signup_doc, paid_at) -> dict
    Renders the HTML, allocates a receipt_number, persists, returns the doc.

  render_receipt_html(receipt_doc) -> str
    Pure render given a stored receipt doc. Used by portal/admin views.

  email_receipt(receipt_doc) -> None
    Send via Resend through tools.outreach.send_email (force_smtp=True).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from database import get_db

log = structlog.get_logger()


def _receipts():
    return get_db()["subscription_receipts"]


def _next_receipt_number(now: datetime) -> str:
    """Returns RNG-YYYYMM-NNNN sequential within the calendar month."""
    period = now.strftime("%Y%m")
    counters = get_db()["counters"]
    doc = counters.find_one_and_update(
        {"_id": f"receipt:{period}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,  # pymongo 4 default; we read .seq after
    )
    seq = (doc or {}).get("seq", 1)
    return f"RNG-{period}-{seq:04d}"


# ─── HTML render ─────────────────────────────────────────────────────────────

def render_receipt_html(receipt: dict) -> str:
    """Pure-function render. Caller passes a stored receipt doc."""
    amount = float(receipt.get("amount_ngn") or 0)
    amount_str = f"₦{amount:,.0f}"
    paid_at: datetime = receipt.get("paid_at") or datetime.now(timezone.utc)
    paid_str = paid_at.strftime("%d %B %Y · %H:%M WAT")
    receipt_no = receipt.get("receipt_number", "RNG-PENDING")
    client_name = receipt.get("client_name") or "Customer"
    owner_email = receipt.get("owner_email") or ""
    plan_label = receipt.get("plan_label") or receipt.get("plan", "subscription").title()
    ref = receipt.get("paystack_reference") or "-"
    annual = bool(receipt.get("annual"))
    period_label = "12 months (annual)" if annual else "1 month"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Receipt {receipt_no} · ReachNG</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
          background:#f8f4ec; color:#14110d; margin:0; padding:32px 16px; }}
  .receipt {{ max-width:640px; margin:0 auto; background:#fff;
              border:1px solid #e8ddc8; border-radius:14px; padding:38px 44px; }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-start;
           border-bottom:1px solid #e8ddc8; padding-bottom:18px; margin-bottom:24px; }}
  .brand .logo {{ font-family:Georgia,serif; font-size:24px; font-weight:600;
                  letter-spacing:-0.5px; color:#14110d; }}
  .brand .logo .ng {{ color:#ff5500; }}
  .brand .tag {{ font-size:11px; letter-spacing:0.18em; text-transform:uppercase;
                 color:#9b917f; font-weight:700; margin-top:4px; }}
  .meta {{ text-align:right; font-size:12px; color:#6b6356; line-height:1.7; }}
  .meta strong {{ color:#14110d; }}
  h1 {{ font-family:Georgia,serif; font-size:22px; font-weight:600; margin:0 0 4px;
         letter-spacing:-0.4px; }}
  .pill {{ display:inline-block; background:#0e6b30; color:#fff; font-size:10px;
           letter-spacing:0.16em; text-transform:uppercase; font-weight:700;
           padding:4px 12px; border-radius:100px; margin-top:6px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:24px; font-size:14px; }}
  th {{ text-align:left; padding:10px 0; border-bottom:1px solid #e8ddc8;
        font-size:11px; text-transform:uppercase; letter-spacing:0.06em; color:#6b6356; }}
  td {{ padding:14px 0; border-bottom:1px solid #f0e9dc; vertical-align:top; }}
  .total td {{ font-size:17px; font-weight:700; color:#14110d;
               padding-top:18px; border-bottom:0; }}
  .total td.amt {{ color:#ff5500; }}
  .foot {{ margin-top:30px; padding-top:18px; border-top:1px solid #e8ddc8;
           font-size:12px; color:#6b6356; line-height:1.7; }}
  .foot strong {{ color:#14110d; }}
  .print-cta {{ margin-top:24px; text-align:center; }}
  .print-cta button {{ background:#14110d; color:#fff; border:0; padding:10px 22px;
                       border-radius:8px; font-size:13px; font-weight:700; cursor:pointer; }}
  @media print {{ body {{ background:#fff; padding:0; }} .receipt {{ box-shadow:none; border:0; }} .print-cta {{ display:none; }} }}
</style>
</head>
<body>
<div class="receipt">
  <div class="head">
    <div class="brand">
      <div class="logo">Reach<span class="ng">NG</span></div>
      <div class="tag">Subscription receipt</div>
    </div>
    <div class="meta">
      <div><strong>{receipt_no}</strong></div>
      <div>{paid_str}</div>
      <div style="margin-top:6px;">Paystack ref: {ref}</div>
    </div>
  </div>

  <h1>Thank you, {client_name}.</h1>
  <div class="pill">Paid</div>

  <table>
    <thead>
      <tr><th>Description</th><th style="text-align:right;">Amount</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>
          <strong>ReachNG {plan_label}</strong><br>
          <span style="color:#6b6356;font-size:13px;">Subscription period: {period_label}</span><br>
          <span style="color:#6b6356;font-size:13px;">Billed to: {owner_email}</span>
        </td>
        <td style="text-align:right;font-weight:600;">{amount_str}</td>
      </tr>
      <tr class="total">
        <td>Total paid</td>
        <td class="amt" style="text-align:right;">{amount_str}</td>
      </tr>
    </tbody>
  </table>

  <div class="print-cta">
    <button onclick="window.print()">Print / Save as PDF</button>
  </div>

  <div class="foot">
    <strong>ReachNG</strong> · The agentic employee for Nigerian SMEs.<br>
    Lagos, Nigeria · hello@reachng.ng · <a href="https://www.reachng.ng" style="color:#ff5500;">www.reachng.ng</a><br>
    This receipt is for your records. No tax invoice is required unless requested.
  </div>
</div>
</body>
</html>
"""


# ─── Persistence ─────────────────────────────────────────────────────────────

def generate_receipt(*, signup: dict, client_id: Optional[str] = None,
                     paid_at: Optional[datetime] = None) -> dict:
    """Build, persist, and return a receipt for a successful subscription
    payment. `signup` is the doc in the `signups` collection (or shape-equivalent).
    """
    now = paid_at or datetime.now(timezone.utc)
    receipt_number = _next_receipt_number(now)
    doc = {
        "receipt_number":     receipt_number,
        "client_id":          str(client_id) if client_id else None,
        "client_name":        signup.get("business_name"),
        "owner_name":         signup.get("owner_name"),
        "owner_email":        signup.get("owner_email"),
        "owner_phone":        signup.get("owner_phone"),
        "plan":               signup.get("plan"),
        "plan_label":         signup.get("plan_label"),
        "amount_ngn":         float(signup.get("amount_ngn") or 0),
        "annual":             bool(signup.get("annual")),
        "paystack_reference": signup.get("paystack_reference"),
        "paid_at":            now,
        "created_at":         now,
    }
    doc["html"] = render_receipt_html(doc)
    _receipts().insert_one(doc)
    log.info("subscription_receipt_generated",
             receipt_no=receipt_number, business=signup.get("business_name"))
    return doc


def get_receipt_by_number(receipt_number: str) -> Optional[dict]:
    return _receipts().find_one({"receipt_number": receipt_number})


def list_receipts_for_client(client_name: Optional[str] = None,
                             client_id: Optional[str] = None,
                             limit: int = 50) -> list[dict]:
    q: dict = {}
    if client_id:
        q["client_id"] = str(client_id)
    elif client_name:
        q["client_name"] = client_name
    else:
        return []
    return list(_receipts().find(q, projection={"html": 0}).sort("paid_at", -1).limit(limit))


# ─── Email delivery via Resend ───────────────────────────────────────────────

async def email_receipt(receipt: dict) -> bool:
    """Email the rendered receipt to the owner. Returns True on success."""
    owner_email = receipt.get("owner_email")
    if not owner_email:
        log.warning("receipt_email_skipped_no_address", receipt_no=receipt.get("receipt_number"))
        return False
    try:
        from tools.outreach import send_email
        client_name = receipt.get("client_name") or "there"
        receipt_no = receipt.get("receipt_number", "")
        amount = float(receipt.get("amount_ngn") or 0)
        plan_label = receipt.get("plan_label") or "ReachNG subscription"
        subject = f"Your ReachNG receipt · {receipt_no}"
        text = (
            f"Hi {client_name},\n\n"
            f"Thank you for your payment. Your receipt is attached below.\n\n"
            f"Receipt: {receipt_no}\n"
            f"Plan:    {plan_label}\n"
            f"Amount:  ₦{amount:,.0f}\n\n"
            f"You can also re-download any time from your portal.\n\n"
            f"— ReachNG\nhello@reachng.ng\n"
        )
        await send_email(
            to_email=owner_email,
            subject=subject,
            body=text,
            html=receipt.get("html") or render_receipt_html(receipt),
            force_smtp=True,  # routes via Resend from hello@reachng.ng
        )
        log.info("subscription_receipt_emailed",
                 receipt_no=receipt_no, email=owner_email)
        return True
    except Exception as exc:
        log.warning("subscription_receipt_email_failed",
                    error=str(exc), receipt_no=receipt.get("receipt_number"))
        return False


def ensure_receipt_indexes() -> None:
    coll = _receipts()
    coll.create_index([("receipt_number", 1)], unique=True, name="receipt_no_unique")
    coll.create_index([("client_id", 1), ("paid_at", -1)], name="by_client_recent")
    coll.create_index([("client_name", 1), ("paid_at", -1)], name="by_client_name_recent")
    coll.create_index([("paystack_reference", 1)], name="by_paystack_ref")
