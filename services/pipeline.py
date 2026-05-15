"""
Operator sales pipeline — Yori's own kanban view across 4 stages.

This is the embedded CRM exposed as a single read-only view, sourced
entirely from existing collections. No new schema.

Stages
------
1. Waitlist        — `waitlist` rows with invited_at IS NULL
2. Invited         — `waitlist` rows with invited_at IS NOT NULL AND signed_up_at IS NULL
3. In Conversation — `signups` rows with status='pending' (Paystack init, no charge yet)
4. Paid            — `clients` rows with payment_status='paid'

Rows are flattened to a uniform `PipelineCard` shape so the template
renders the same component across all four columns.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from database import get_db


def _iso(v) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else (v if isinstance(v, str) else None)


def _card_from_waitlist(row: dict) -> dict:
    return {
        "id":            str(row.get("_id", "")),
        "stage":         "waitlist" if not row.get("invited_at") else "invited",
        "title":         row.get("business_name") or row.get("name") or "—",
        "subtitle":      row.get("name") or "",
        "vertical":      row.get("vertical") or "",
        "city":          row.get("city") or "Lagos",
        "phone":         row.get("phone"),
        "email":         row.get("email"),
        "note":          row.get("brief_pain"),
        "source":        row.get("source") or "direct",
        "position":      row.get("position"),
        "created_at":    _iso(row.get("created_at")),
        "invited_at":    _iso(row.get("invited_at")),
    }


def _card_from_signup(row: dict) -> dict:
    return {
        "id":            str(row.get("_id", "")),
        "stage":         "in_conversation",
        "title":         row.get("business_name") or "—",
        "subtitle":      row.get("owner_name") or "",
        "vertical":      row.get("vertical") or "",
        "city":          row.get("city") or "Lagos",
        "phone":         row.get("owner_phone"),
        "email":         row.get("owner_email"),
        "note":          f"Plan: {row.get('plan', '—')} · {('annual' if row.get('annual') else 'monthly')}",
        "source":        "signup",
        "reference":     row.get("paystack_reference"),
        "created_at":    _iso(row.get("created_at")),
    }


def _card_from_client(row: dict) -> dict:
    return {
        "id":            str(row.get("_id", "")),
        "stage":         "paid",
        "title":         row.get("name") or "—",
        "subtitle":      row.get("owner_name") or "",
        "vertical":      row.get("vertical") or "",
        "city":          (row.get("location") or {}).get("city") if isinstance(row.get("location"), dict) else "Lagos",
        "phone":         row.get("owner_phone"),
        "email":         row.get("owner_email"),
        "note":          f"₦{(row.get('monthly_fee_ngn') or 0):,}/mo · {row.get('plan', '—')}",
        "source":        "paid",
        "paid_until":    _iso(row.get("paid_until")),
        "created_at":    _iso(row.get("created_at")),
    }


def get_pipeline() -> dict:
    """Return all 4 columns + counts. Single Mongo round-trip per collection."""
    db = get_db()

    waitlist_uninvited = list(
        db["waitlist"].find({"invited_at": None}).sort("position", 1).limit(200)
    )
    waitlist_invited = list(
        db["waitlist"].find({
            "invited_at": {"$ne": None},
            "signed_up_at": None,
        }).sort("invited_at", -1).limit(200)
    )
    signups_pending = list(
        db["signups"].find({"status": "pending"}).sort("created_at", -1).limit(200)
    ) if "signups" in db.list_collection_names() else []

    # Paid clients — exclude demo/sandbox/internal flags
    paid_clients = list(
        db["clients"].find({
            "payment_status": "paid",
            "active": True,
        }).sort("created_at", -1).limit(200)
    )

    return {
        "columns": [
            {
                "key":   "waitlist",
                "label": "Waitlist",
                "hint":  "Joined the list — not yet invited",
                "count": len(waitlist_uninvited),
                "cards": [_card_from_waitlist(r) for r in waitlist_uninvited],
            },
            {
                "key":   "invited",
                "label": "Invited / Demo",
                "hint":  "Invite sent — awaiting signup",
                "count": len(waitlist_invited),
                "cards": [_card_from_waitlist(r) for r in waitlist_invited],
            },
            {
                "key":   "in_conversation",
                "label": "In Conversation",
                "hint":  "Started checkout — Paystack pending",
                "count": len(signups_pending),
                "cards": [_card_from_signup(r) for r in signups_pending],
            },
            {
                "key":   "paid",
                "label": "Paid",
                "hint":  "Active paying clients",
                "count": len(paid_clients),
                "cards": [_card_from_client(r) for r in paid_clients],
            },
        ],
        "total_in_pipeline": (
            len(waitlist_uninvited)
            + len(waitlist_invited)
            + len(signups_pending)
            + len(paid_clients)
        ),
    }
