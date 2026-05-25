"""
Onboard ReachNG as Client #0 — dogfood mode.

Creates the `ReachNG` entry in the `clients` collection so the self-outreach
campaign can route through the existing HITL + drafter + scorecard machinery
exactly the way a paying client would.

Run from project root:
    python -m scripts.onboard_reachng_as_client

Idempotent — safe to re-run; updates without overwriting outreach history.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import structlog

from database import get_db

log = structlog.get_logger()


CLIENT_NAME = "ReachNG"

BRIEF = """\
ReachNG is a Lagos-built AI WhatsApp operator (EYO) for premium Nigerian
SMEs whose money enters the business via WhatsApp. EYO drafts every reply
in the owner's voice from the owner's own paired number, reads bank
transfer screenshots from GTBank / OPay / Kuda / UBA / PalmPay, speaks
five Nigerian languages on voice notes, remembers every customer, and
sends a 7am cash brief. Nothing sends without the owner's tap until they
explicitly earn Autopilot.

Pricing:
  - Solo    ₦60,000/month
  - Team    ₦120,000/month
  - Empire  ₦250,000/month
Founder cohort pricing locked for first 50 paying clients.

We are NOT: a generic AI chatbot, an SMS blaster, an outsourced call
centre, a cheap chatbot like RheoChat / Obeks / Runarm, or anything that
holds client funds.
"""

QUALIFYING_QUESTIONS = [
    "How many WhatsApp customer enquiries does your business receive per week?",
    "What's the average value of a closed deal / booking / transaction?",
    "Who currently handles replies — you, a team, or nobody on weekends?",
    "What payment method do most customers use — bank transfer, Paystack, cash?",
    "Have you ever lost a customer because a reply came too late?",
]

CLOSING_ACTION = (
    "Get the prospect to spend 60 seconds on the live demo at reachng.ng. "
    "If they reply asking for more, schedule a 15-minute WhatsApp call with "
    "Yori. Never push for a meeting in the first touch."
)

NEVER_SAY = [
    # SDR / pitch-deck tropes
    "leverage", "synergy", "ecosystem", "robust", "seamless", "circle back",
    "touch base", "ping you", "loop you in", "hope this finds you well",
    "I hope all is well", "AI-powered", "next-generation", "cutting-edge",
    "revolutionary", "automate", "10x", "growth hack",
    # Forbidden endearments (every ReachNG outbound)
    "babe", "love", "dear", "darling", "sweetie", "hun", "boo", "bae",
    # Self-mis-positioning
    "an agency", "a platform", "a SaaS",
]

PRICING_RULES = """\
Quote tiers in this exact format:
  Solo ₦60,000/month · Team ₦120,000/month · Empire ₦250,000/month
Never discount in the first touch. If pressed on price, offer the founder
cohort lock — the first 50 paying customers keep their tier price for life.
Annual prepay = 15% off. Never offer < ₦60k Starter under any pressure.
"""


def upsert_client() -> dict:
    db = get_db()
    clients = db["clients"]
    now = datetime.now(timezone.utc)

    existing = clients.find_one({"name": CLIENT_NAME})
    set_doc = {
        "name":                 CLIENT_NAME,
        "vertical":             "b2b_saas",
        "brief":                BRIEF,
        "agent_name":           "EYO",
        "preferred_channel":    "email",          # Self-outreach via Resend hello@reachng.ng
        "active":               True,
        "plan":                 "internal",
        "payment_status":       "internal",
        "monthly_fee_ngn":      0,
        "city":                 "Lagos",
        "cities":               ["Lagos", "Abuja"],
        "whatsapp_provider":    "unipile",
        "daily_send_limit":     25,               # Conservative: 25/day cold outreach max
        "product":              "reachng",
        "autopilot":            False,            # HARD: every send through HITL
        "owner_phone":          None,             # Set later via env / portal
        "signal_listening":     False,
        "holding_message":      "",
        "qualifying_questions": QUALIFYING_QUESTIONS,
        "closing_action":       CLOSING_ACTION,
        "never_say":            NEVER_SAY,
        "pricing_rules":        PRICING_RULES,
        "outreach_warmup_skip": False,            # Apply 10/25/50 ramp even to us
    }

    if existing:
        # Don't clobber pairing, outreach_started_at, portal_token, or
        # accumulated history — only sync brief-level fields.
        keep = {"created_at", "onboarded_at", "outreach_started_at",
                "portal_token", "portal_created_at", "whatsapp_account_id",
                "whatsapp_accounts", "whatsapp_connected_at"}
        update_only = {k: v for k, v in set_doc.items() if k not in keep}
        clients.update_one({"name": CLIENT_NAME}, {"$set": update_only})
        log.info("client_zero_updated", name=CLIENT_NAME)
        return {"action": "updated", "name": CLIENT_NAME, "id": str(existing["_id"])}

    set_doc["created_at"]         = now
    set_doc["onboarded_at"]       = now
    set_doc["outreach_started_at"] = now
    result = clients.insert_one(set_doc)
    log.info("client_zero_created", name=CLIENT_NAME, id=str(result.inserted_id))
    return {"action": "created", "name": CLIENT_NAME, "id": str(result.inserted_id)}


if __name__ == "__main__":
    try:
        out = upsert_client()
        print(f"OK — {out['action']} '{out['name']}' (id={out['id']})")
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
