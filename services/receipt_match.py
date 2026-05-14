"""
Receipt Catcher — match + draft.

Given a `ReceiptData` from `tools.receipt_vision` and the inbound sender's phone,
find the open obligation it likely settles, then draft a customer reply.

Match priority (most specific first):
  1. Closer lead (Active conversation — inbound match wins)
  2. Rent ledger (estate_rent_ledger, status=open, tenant matched by phone)
  3. Invoice chaser (chased_invoices, status=sent, debtor matched by phone)
  4. School fees (sf_students, paid=False, parent matched by phone)
  5. Unmatched — still acknowledge politely + flag to owner

Drafts are queued via HITL — never auto-sent. Owner approves before the customer
receives the acknowledgement. Mismatches (wrong amount, suspicious receipt) are
flagged in the queued draft + escalated for human eyeballs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

import structlog
from bson import ObjectId

from database import get_db
from tools.receipt_vision import ReceiptData

log = structlog.get_logger()


# ─── Match result ─────────────────────────────────────────────────────────────

MatchType = Literal["rent", "invoice", "school_fees", "closer_lead", "unmatched"]
MatchVerdict = Literal["exact", "underpaid", "overpaid", "no_open_balance", "unmatched"]


@dataclass
class MatchResult:
    match_type: MatchType
    verdict: MatchVerdict
    expected_ngn: Optional[float]
    delta_ngn: Optional[float]          # received - expected (negative = underpaid)
    record_id: Optional[str]            # _id of the matched doc
    record_label: Optional[str]         # human label ("April rent for Unit 3B", "Invoice INV-0042")
    client_doc: Optional[dict]          # the owning client (for HITL routing)
    debtor_name: Optional[str]
    debtor_phone: Optional[str]
    notes: list[str]                    # things to surface in the HITL queue


# ─── Public API ───────────────────────────────────────────────────────────────

def match_receipt(receipt: ReceiptData, sender_phone: str) -> MatchResult:
    """
    Find the open obligation this receipt most likely settles.

    sender_phone is the WhatsApp number that sent the screenshot. We use it
    (not the receipt's sender_name) to scope the search — names get mangled
    by bank apps, phone numbers don't.
    """
    notes: list[str] = []
    if not receipt.is_receipt:
        return MatchResult(
            match_type="unmatched", verdict="unmatched",
            expected_ngn=None, delta_ngn=None, record_id=None, record_label=None,
            client_doc=None, debtor_name=None, debtor_phone=sender_phone,
            notes=["image not classified as a receipt"],
        )

    if not receipt.amount_ngn:
        notes.append("vision could not extract amount — owner must verify")

    db = get_db()

    # 1. Rent ledger — most common in Lagos real estate
    rent = _try_rent_match(db, sender_phone, receipt.amount_ngn)
    if rent:
        rent.notes = notes + rent.notes
        return rent

    # 2. Invoice chaser
    invoice = _try_invoice_match(db, sender_phone, receipt.amount_ngn)
    if invoice:
        invoice.notes = notes + invoice.notes
        return invoice

    # 3. School fees
    sf = _try_school_fees_match(db, sender_phone, receipt.amount_ngn)
    if sf:
        sf.notes = notes + sf.notes
        return sf

    # 4. Closer lead (open deal — deposit may have just arrived)
    closer = _try_closer_match(db, sender_phone, receipt.amount_ngn)
    if closer:
        closer.notes = notes + closer.notes
        return closer

    return MatchResult(
        match_type="unmatched", verdict="unmatched",
        expected_ngn=None, delta_ngn=None,
        record_id=None, record_label=None, client_doc=None,
        debtor_name=receipt.sender_name, debtor_phone=sender_phone,
        notes=notes + ["no open invoice / rent / fee / lead matches this sender"],
    )


# ─── Matchers ─────────────────────────────────────────────────────────────────

def _verdict(expected: Optional[float], received: Optional[float]) -> tuple[MatchVerdict, Optional[float]]:
    """Compare expected vs received, return verdict + delta."""
    if expected is None or received is None:
        return "unmatched", None
    delta = round(received - expected, 2)
    if abs(delta) < 1:          # naira-rounding tolerance
        return "exact", delta
    return ("overpaid", delta) if delta > 0 else ("underpaid", delta)


def _try_rent_match(db, phone: str, amount: Optional[float]) -> Optional[MatchResult]:
    tenant = db["estate_tenants"].find_one({"phone": phone, "status": "active"})
    if not tenant:
        return None
    charge = db["estate_rent_ledger"].find_one(
        {"tenant_id": str(tenant["_id"]), "status": "open"},
        sort=[("due_date", 1)],
    )
    if not charge:
        return MatchResult(
            match_type="rent", verdict="no_open_balance",
            expected_ngn=None, delta_ngn=None,
            record_id=str(tenant["_id"]), record_label="tenant has no open rent charge",
            client_doc=_find_client(db, tenant.get("landlord_company")),
            debtor_name=tenant.get("tenant_name"), debtor_phone=phone,
            notes=["tenant matched but no open rent — possibly early/duplicate payment"],
        )
    expected = float(charge.get("amount_ngn", 0)) or None
    verdict, delta = _verdict(expected, amount)
    unit = db["estate_units"].find_one({"_id": ObjectId(charge["unit_id"])})
    label = f"{charge.get('period', 'rent')} — {(unit or {}).get('label', 'Unit')}"
    return MatchResult(
        match_type="rent", verdict=verdict,
        expected_ngn=expected, delta_ngn=delta,
        record_id=str(charge["_id"]), record_label=label,
        client_doc=_find_client(db, tenant.get("landlord_company")),
        debtor_name=tenant.get("tenant_name"), debtor_phone=phone,
        notes=[],
    )


def _try_invoice_match(db, phone: str, amount: Optional[float]) -> Optional[MatchResult]:
    invoice = db["chased_invoices"].find_one(
        {"debtor_phone": phone, "status": "sent"},
        sort=[("sent_at", -1)],
    )
    if not invoice:
        return None
    expected = float(invoice.get("amount_ngn", 0)) or None
    verdict, delta = _verdict(expected, amount)
    label = f"Invoice {invoice.get('reference', invoice.get('_id'))}"
    return MatchResult(
        match_type="invoice", verdict=verdict,
        expected_ngn=expected, delta_ngn=delta,
        record_id=str(invoice["_id"]), record_label=label,
        client_doc=_find_client(db, invoice.get("client_name")),
        debtor_name=invoice.get("debtor_name"), debtor_phone=phone,
        notes=[],
    )


def _try_school_fees_match(db, phone: str, amount: Optional[float]) -> Optional[MatchResult]:
    student = db["sf_students"].find_one(
        {"parent_phone": phone, "active": True, "paid": False}
    )
    if not student:
        return None
    paid_so_far = float(student.get("amount_paid", 0))
    balance = float(student.get("fee_amount", 0)) - paid_so_far
    verdict, delta = _verdict(balance if balance > 0 else None, amount)
    label = f"School fees — {student.get('student_name')}"
    return MatchResult(
        match_type="school_fees", verdict=verdict,
        expected_ngn=balance if balance > 0 else None, delta_ngn=delta,
        record_id=str(student["_id"]), record_label=label,
        client_doc=_find_client_by_id(db, student.get("school_id")),
        debtor_name=student.get("parent_name"), debtor_phone=phone,
        notes=[],
    )


def _try_closer_match(db, phone: str, amount: Optional[float]) -> Optional[MatchResult]:
    lead = db["closer_leads"].find_one(
        {"contact_phone": phone, "status": {"$ne": "closed"}},
        sort=[("updated_at", -1)],
    )
    if not lead:
        return None
    # Closer leads don't have a fixed expected amount — verdict is "exact" if amount present
    verdict: MatchVerdict = "exact" if amount else "unmatched"
    label = f"Lead — {lead.get('inquiry_text', '')[:60]}"
    client_id = lead.get("client_id")
    return MatchResult(
        match_type="closer_lead", verdict=verdict,
        expected_ngn=None, delta_ngn=None,
        record_id=str(lead["_id"]), record_label=label,
        client_doc=_find_client_by_id(db, client_id),
        debtor_name=lead.get("contact_name") or lead.get("client_name"),
        debtor_phone=phone,
        notes=["open lead — receipt may be the deposit or full settlement"],
    )


# ─── Client lookups ───────────────────────────────────────────────────────────

def _find_client(db, name: Optional[str]) -> Optional[dict]:
    if not name:
        return None
    import re
    return db["clients"].find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})


def _find_client_by_id(db, client_id: Optional[str]) -> Optional[dict]:
    if not client_id:
        return None
    try:
        return db["clients"].find_one({"_id": ObjectId(client_id)})
    except Exception:
        return None


# ─── Drafting ─────────────────────────────────────────────────────────────────

def draft_acknowledgement(receipt: ReceiptData, match: MatchResult) -> str:
    """
    Compose the WhatsApp acknowledgement the customer will see (after HITL approval).
    Tone: warm, specific, Nigerian-business-natural. No emojis except a single ✓.
    """
    name = (match.debtor_name or "").split()[0] if match.debtor_name else None
    salute = f"Hi {name}" if name else "Hi"

    amt = receipt.amount_ngn
    bank = receipt.bank or "your bank"
    ref = receipt.reference

    # Build the verb-phrase
    amt_phrase = f"₦{amt:,.0f}" if amt else "your transfer"
    ref_phrase = f" (ref {ref})" if ref else ""

    if match.match_type == "unmatched":
        return (
            f"{salute}, thanks — we've received {amt_phrase} from {bank}{ref_phrase}. "
            "Could you let us know what this payment is for so I can credit it correctly? "
            "If it was sent to us by mistake, please confirm so we can refund."
        )

    if match.verdict == "exact":
        return (
            f"{salute}, thank you ✓ Your {amt_phrase} payment for {match.record_label} "
            f"is confirmed{ref_phrase}. Your receipt will follow shortly. We appreciate you."
        )

    if match.verdict == "underpaid":
        short = abs(match.delta_ngn or 0)
        return (
            f"{salute}, thank you — we've received {amt_phrase}{ref_phrase} towards "
            f"{match.record_label}. There's a balance of ₦{short:,.0f} still outstanding. "
            "Were you planning to send the balance separately, or shall we set up an instalment? "
            "Either works — let me know."
        )

    if match.verdict == "overpaid":
        excess = match.delta_ngn or 0
        return (
            f"{salute}, thank you ✓ Your {amt_phrase} payment{ref_phrase} is confirmed for "
            f"{match.record_label}. You've actually sent ₦{excess:,.0f} more than the balance — "
            "would you like the excess refunded, held as credit for next month, or applied to "
            "another invoice? Let me know what works."
        )

    if match.verdict == "no_open_balance":
        return (
            f"{salute}, thanks — we've received {amt_phrase}{ref_phrase}. Just confirming, "
            "we don't have an outstanding balance for you on file — would you like this held "
            "as credit, or refunded? Happy to do either."
        )

    # Fallback
    return (
        f"{salute}, thank you — we've received {amt_phrase} from {bank}{ref_phrase}. "
        "I'll review and confirm shortly."
    )


# ─── HITL queueing ────────────────────────────────────────────────────────────

def queue_receipt_ack(receipt: ReceiptData, match: MatchResult, sender_phone: str) -> Optional[str]:
    """
    Persist the receipt event + queue the customer-facing acknowledgement to HITL.

    Returns the approval doc _id, or None if we deliberately skipped (e.g. not a receipt).
    """
    db = get_db()

    # 1. Log the receipt event regardless of match — audit + analytics
    event = {
        "received_at":    datetime.now(timezone.utc),
        "sender_phone":   sender_phone,
        "receipt":        receipt.model_dump(),
        "match_type":     match.match_type,
        "match_verdict":  match.verdict,
        "expected_ngn":   match.expected_ngn,
        "delta_ngn":      match.delta_ngn,
        "record_id":      match.record_id,
        "record_label":   match.record_label,
        "client_name":    (match.client_doc or {}).get("name"),
        "notes":          match.notes,
    }
    try:
        db["receipt_events"].insert_one(event)
    except Exception as e:
        log.warning("receipt_event_persist_failed", error=str(e))

    # 2. Skip drafting for very-low-confidence non-receipts
    if not receipt.is_receipt and receipt.confidence < 0.3:
        log.info("receipt_skipped_not_a_receipt", phone=sender_phone)
        return None

    # 3. Mark the matched record as claim-paid (best-effort, idempotent-ish)
    _stamp_record_claim(db, match)

    # 4. Compose draft + push through HITL
    message = draft_acknowledgement(receipt, match)

    # contact_id: try to reuse the existing contact, else create a lightweight stub
    contact_id = _resolve_contact_id(db, sender_phone, match)

    # source = "receipt_catcher" — transactional, brief-gate skipped
    from tools.hitl import queue_draft
    try:
        approval_id = queue_draft(
            contact_id=contact_id,
            contact_name=match.debtor_name or "Customer",
            vertical=(match.client_doc or {}).get("vertical") or "general",
            channel="whatsapp",
            message=message,
            phone=sender_phone,
            source="receipt_catcher",
            client_name=(match.client_doc or {}).get("name"),
            inbound_context=f"[receipt: {receipt.bank or 'bank'} ₦{receipt.amount_ngn or '?'} "
                            f"ref {receipt.reference or '—'}] verdict={match.verdict}",
        )
        log.info(
            "receipt_ack_queued",
            verdict=match.verdict, match_type=match.match_type,
            phone=sender_phone, approval=approval_id,
        )
        return approval_id
    except Exception as e:
        log.error("receipt_ack_queue_failed", error=str(e), phone=sender_phone)
        return None


def _stamp_record_claim(db, match: MatchResult) -> None:
    """Best-effort: mark the matched obligation as 'claimed paid' pending verification."""
    if not match.record_id or match.match_type == "unmatched":
        return
    now = datetime.now(timezone.utc)
    try:
        if match.match_type == "rent":
            db["estate_rent_ledger"].update_one(
                {"_id": ObjectId(match.record_id)},
                {"$set": {"claimed_paid": True, "claim_received_at": now}},
            )
        elif match.match_type == "invoice":
            db["chased_invoices"].update_one(
                {"_id": ObjectId(match.record_id)},
                {"$set": {"claimed_paid": True, "claim_received_at": now}},
            )
        elif match.match_type == "school_fees":
            db["sf_students"].update_one(
                {"_id": ObjectId(match.record_id)},
                {"$set": {"claimed_paid": True, "claim_received_at": now}},
            )
    except Exception as e:
        log.warning("receipt_claim_stamp_failed", error=str(e), kind=match.match_type)


def _resolve_contact_id(db, phone: str, match: MatchResult) -> str:
    """Find or create a contacts doc for this phone, return its _id as str."""
    contacts = db["contacts"]
    found = contacts.find_one({"phone": phone})
    if found:
        return str(found["_id"])
    # Lightweight stub — full contact gets created the moment the owner approves the reply
    stub = {
        "phone":        phone,
        "contact_name": match.debtor_name or "Customer",
        "vertical":     (match.client_doc or {}).get("vertical") or "general",
        "client_name":  (match.client_doc or {}).get("name"),
        "source":       "receipt_catcher",
        "created_at":   datetime.now(timezone.utc),
    }
    res = contacts.insert_one(stub)
    return str(res.inserted_id)
