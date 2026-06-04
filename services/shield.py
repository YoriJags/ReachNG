"""
EYO Shield — fake-transfer / scam detector (invention #1).

"I've sent it 🙏" fraud is endemic in Nigerian commerce. Shield scores an
already-extracted bank-transfer receipt and warns the owner BEFORE goods are
released. It NEVER auto-declines — the owner always decides (HITL).

Pure + dependency-free: takes a `ReceiptData`-like object (or dict) from
`tools.receipt_vision` plus optional context — the amount expected, the
client's own account, references seen on earlier receipts, and whether this
sender has been flagged before — and returns a deterministic risk verdict with
plain-language reasons.

Signals (each adds to a risk score):
  • status not 'success' (pending / failed) — money may not have landed
  • amount doesn't match what's owed
  • paid into an account that isn't the client's
  • recipient name doesn't match the client's business
  • transaction reference reused from an earlier receipt (edited/reused screenshot)
  • sender is a known repeat offender
  • image barely legible (manual check warranted)
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

RISK_CLEAR  = "clear"
RISK_REVIEW = "review"
RISK_HIGH   = "high"

_NOT_SETTLED = {"pending", "processing", "in progress", "in-progress", "ongoing", "reversed"}


def _get(receipt: Any, key: str, default=None):
    if receipt is None:
        return default
    if isinstance(receipt, dict):
        return receipt.get(key, default)
    return getattr(receipt, key, default)


def _digits(s: Any) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _name_match(name: Optional[str], candidates: Optional[Iterable[str]]) -> bool:
    """Loose containment match on alpha-only, lowercased names. Returns True
    when there's nothing to compare so we never penalise on missing data."""
    n = re.sub(r"[^a-z]", "", (name or "").lower())
    if not n:
        return True
    for c in (candidates or []):
        cc = re.sub(r"[^a-z]", "", (c or "").lower())
        if cc and (cc in n or n in cc):
            return True
    return False


def assess_transfer(
    receipt: Any,
    *,
    expected_amount: Optional[float] = None,
    client_account: Optional[str] = None,
    client_account_names: Optional[Iterable[str]] = None,
    prior_references: Optional[Iterable[str]] = None,
    repeat_offender: bool = False,
) -> dict:
    """Deterministic fraud-risk verdict for one receipt.

    Returns: {risk, score, reasons[], verify, is_receipt}
      risk   = "clear" | "review" | "high"
      verify = True when the owner should check before releasing goods
    """
    if not _get(receipt, "is_receipt", False):
        return {"risk": RISK_CLEAR, "score": 0, "reasons": [],
                "verify": False, "is_receipt": False}

    reasons: list[str] = []
    score = 0

    status = (_get(receipt, "status") or "").strip().lower()
    if status == "failed":
        score += 60
        reasons.append("Receipt shows a FAILED transaction — no money moved.")
    elif status in _NOT_SETTLED:
        score += 40
        reasons.append("Status isn't 'success' yet — the money may not have landed. Confirm in your bank app.")

    amount = _get(receipt, "amount_ngn")
    if expected_amount and amount is not None:
        try:
            if abs(float(amount) - float(expected_amount)) > max(1.0, float(expected_amount) * 0.01):
                score += 30
                reasons.append(
                    f"Amount (₦{float(amount):,.0f}) doesn't match the ₦{float(expected_amount):,.0f} expected.")
        except (TypeError, ValueError):
            pass

    rcpt_acct = _digits(_get(receipt, "recipient_account"))
    my_acct = _digits(client_account)
    if my_acct and rcpt_acct:
        if rcpt_acct[-10:] != my_acct[-10:]:
            score += 50
            reasons.append("The receipt was paid into an account that isn't yours.")
    elif client_account_names and _get(receipt, "recipient_name"):
        if not _name_match(_get(receipt, "recipient_name"), client_account_names):
            score += 20
            reasons.append("Recipient name doesn't match your business account.")

    ref = (_get(receipt, "reference") or "").strip()
    if ref and prior_references and ref in set(prior_references):
        score += 60
        reasons.append("This transaction reference was already used — possible reused or edited screenshot.")

    if repeat_offender:
        score += 40
        reasons.append("This sender has sent a questionable receipt before.")

    conf = _get(receipt, "confidence") or 0.0
    try:
        if float(conf) and float(conf) < 0.4:
            score += 10
            reasons.append("The image is hard to read — worth a manual check.")
    except (TypeError, ValueError):
        pass

    risk = RISK_HIGH if score >= 50 else RISK_REVIEW if score >= 25 else RISK_CLEAR
    return {"risk": risk, "score": score, "reasons": reasons,
            "verify": risk != RISK_CLEAR, "is_receipt": True}


def shield_alert_text(contact_name: Optional[str], receipt: Any, verdict: dict) -> str:
    """Owner-facing WhatsApp warning. Only call when verdict['verify'] is True.

    Honest + non-accusatory toward the customer — EYO surfaces doubt, the owner
    confirms. Never tells the owner the payment IS fake, only that it's unconfirmed.
    """
    amt = _get(receipt, "amount_ngn")
    amt_s = f"₦{float(amt):,.0f}" if amt is not None else "a payment"
    head = "🚨 Verify before releasing" if verdict.get("risk") == RISK_HIGH else "⚠️ Worth a quick check"
    lines = [f"{head} — {contact_name or 'a customer'} sent {amt_s}."]
    lines += [f"• {r}" for r in verdict.get("reasons", [])[:3]]
    lines.append("EYO couldn't confirm this one. Check your bank app before you hand anything over.")
    return "\n".join(lines)
