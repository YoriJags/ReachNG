"""
Scenario Library — pre-built rule bundles per vertical.

Clients open the Scenarios tab in their portal, see scenarios relevant to their
vertical, and one-click activate the bundle. Each scenario seeds 2-4 rules into
their `client_rules` collection.

This keeps the manual rule-writing burden low for the first 80% of common
playbooks, while still allowing fully-custom rules on top.

Adding a scenario: drop an entry into SCENARIOS[vertical]. The shape is locked
so the portal can render any vertical without case-by-case logic.
"""
from __future__ import annotations

from typing import TypedDict

from services.client_rules import add_rule


class ScenarioRule(TypedDict, total=False):
    name: str
    behavior_text: str
    trigger_keywords: list[str]
    trigger_intent: str
    escalate_to_owner: bool


class Scenario(TypedDict):
    key: str
    label: str
    summary: str
    rules: list[ScenarioRule]


SCENARIOS: dict[str, list[Scenario]] = {
    "hospitality": [
        {
            "key": "birthday-booking",
            "label": "Birthday booking enquiry",
            "summary": "Treat birthday parties differently — confirm guest count, lock the date with a deposit, propose private section.",
            "rules": [
                {
                    "name": "Birthday playbook",
                    "behavior_text": "When 'birthday', 'bday', or 'b-day' appears, propose the private section, confirm exact date + guest count, quote minimum spend, and ask for a 50% deposit via Paystack to hold the date.",
                    "trigger_keywords": ["birthday", "bday", "b-day", "birthday party"],
                },
                {
                    "name": "Birthday deposit nudge",
                    "behavior_text": "Always include a Paystack deposit link for birthday bookings — the slot is not held without it.",
                    "trigger_keywords": ["birthday", "bday"],
                },
            ],
        },
        {
            "key": "corporate-event",
            "label": "Corporate event enquiry",
            "summary": "Corporate events get a written proposal route — escalate to the owner for pricing approval.",
            "rules": [
                {
                    "name": "Corporate event escalate",
                    "behavior_text": "When 'corporate', 'team outing', 'company event', or 'office party' appears, acknowledge the enquiry warmly, ask for date / headcount / budget, and tell the customer a tailored proposal will follow within 24 hours.",
                    "trigger_keywords": ["corporate", "team outing", "company event", "office party"],
                    "escalate_to_owner": True,
                },
            ],
        },
        {
            "key": "vip-table",
            "label": "VIP table / bottle service",
            "summary": "VIP enquiries get bottle minimums and the table-host introduction.",
            "rules": [
                {
                    "name": "VIP table playbook",
                    "behavior_text": "When 'VIP', 'bottle', 'table service', or 'reserved table' appears, quote the bottle minimum, mention the dedicated table host, and ask for the deposit to lock the slot.",
                    "trigger_keywords": ["vip", "bottle", "table service", "reserved table"],
                },
            ],
        },
    ],

    "real_estate": [
        {
            "key": "pof-qualification",
            "label": "Proof-of-Funds gating for luxury properties",
            "summary": "For ₦100M+ enquiries, request PoF before booking a viewing.",
            "rules": [
                {
                    "name": "PoF gate for luxury",
                    "behavior_text": "Before scheduling any viewing for a property priced ₦100M or above, politely ask the buyer for Proof of Funds — this is standard procedure for our luxury inventory and protects everyone's time.",
                    "trigger_keywords": ["viewing", "view", "see the property", "see the house", "inspection"],
                },
            ],
        },
        {
            "key": "diaspora-buyer",
            "label": "Diaspora buyer handling",
            "summary": "Buyers in UK/US timezones get video-tour offers and a written brief.",
            "rules": [
                {
                    "name": "Diaspora video tour",
                    "behavior_text": "If the buyer mentions they are based abroad / in UK / US / diaspora, offer a live video tour as the first step before booking an in-person viewing. Confirm their timezone and propose 2-3 slots.",
                    "trigger_keywords": ["diaspora", "abroad", "london", "uk", "us", "states", "uae", "dubai", "canada"],
                },
            ],
        },
        {
            "key": "off-market",
            "label": "Off-market enquiry",
            "summary": "Off-market enquiries escalate to owner — these are high-value.",
            "rules": [
                {
                    "name": "Off-market escalate",
                    "behavior_text": "When 'off-market', 'private listing', 'discreet', or 'not on the website' appears, acknowledge politely and tell the buyer a senior agent will follow up personally within the day. Do NOT share specific addresses or prices in writing for off-market inventory.",
                    "trigger_keywords": ["off-market", "off market", "private listing", "discreet", "not on the website"],
                    "escalate_to_owner": True,
                },
            ],
        },
    ],

    "education": [
        {
            "key": "diaspora-admission",
            "label": "Diaspora parent admission enquiry",
            "summary": "Parents abroad get the prospectus + video-tour invite immediately, regardless of Lagos time.",
            "rules": [
                {
                    "name": "Diaspora admission playbook",
                    "behavior_text": "When the parent indicates they are based abroad (UK / US / Canada / UAE), send the prospectus and entrance-assessment details right away, and offer a live video tour. Reference timezone friendliness.",
                    "trigger_keywords": ["abroad", "london", "uk", "atlanta", "us", "states", "canada", "dubai", "uae", "diaspora", "relocating"],
                },
            ],
        },
        {
            "key": "scholarship-enquiry",
            "label": "Scholarship / bursary enquiry",
            "summary": "Scholarship enquiries route to admissions with a softer tone.",
            "rules": [
                {
                    "name": "Scholarship enquiry",
                    "behavior_text": "When 'scholarship', 'bursary', 'financial aid', or 'discount' appears, share the scholarship-application pack, the deadline, and the assessment day. Be warm, never gatekeep.",
                    "trigger_keywords": ["scholarship", "bursary", "financial aid", "discount", "fee waiver"],
                    "escalate_to_owner": True,
                },
            ],
        },
    ],

    "professional_services": [
        {
            "key": "conflict-check",
            "label": "Conflict-check protocol",
            "summary": "Before quoting on a new matter, run the conflict-check ask.",
            "rules": [
                {
                    "name": "Conflict check",
                    "behavior_text": "Before quoting fees or scheduling a consultation, politely ask for the names of all parties involved in the matter so we can run a conflict check. Frame this as standard firm policy — not optional.",
                },
            ],
        },
        {
            "key": "confidentiality-affirm",
            "label": "Confidentiality affirmation",
            "summary": "Affirm confidentiality upfront for sensitive enquiries.",
            "rules": [
                {
                    "name": "Confidentiality affirm",
                    "behavior_text": "When 'confidential', 'private', 'sensitive', 'dispute', or 'investigation' appears, open the reply with a single sentence affirming strict confidentiality before asking any follow-up questions.",
                    "trigger_keywords": ["confidential", "private", "sensitive", "dispute", "investigation"],
                },
            ],
        },
    ],

    "small_business": [
        {
            "key": "deposit-to-book",
            "label": "Deposit-to-book policy",
            "summary": "Always require a deposit to confirm any booking.",
            "rules": [
                {
                    "name": "Deposit to book",
                    "behavior_text": "No slot is confirmed without a deposit. Always send the Paystack link with the booking confirmation and tell the customer the slot is held for 30 minutes pending payment.",
                    "trigger_keywords": ["book", "booking", "appointment", "slot", "reserve"],
                },
            ],
        },
        {
            "key": "regular-loyalty",
            "label": "Returning customer loyalty",
            "summary": "Returning customers skip the deposit; address them by name.",
            "rules": [
                {
                    "name": "Loyalty tone",
                    "behavior_text": "If memory tells you this customer is a returning regular, skip the deposit ask, address them by first name, and reference what they usually book.",
                },
            ],
        },
    ],
}


def list_for_vertical(vertical: str) -> list[Scenario]:
    return SCENARIOS.get((vertical or "").lower(), [])


def list_all() -> dict[str, list[Scenario]]:
    return dict(SCENARIOS)


def activate_scenario(client_id: str, vertical: str, scenario_key: str) -> dict:
    """Seed all rules from `scenario_key` into the client's rules collection.

    Idempotent-ish — re-activation does NOT dedupe; clients can delete duplicates
    from the portal. We tag each seeded rule with `source_scenario` so we can
    show "X rules from scenario Y" in the UI.

    Returns {"inserted": int, "scenario": Scenario|None}.
    """
    scenarios = list_for_vertical(vertical)
    match = next((s for s in scenarios if s["key"] == scenario_key), None)
    if not match:
        return {"inserted": 0, "scenario": None}

    inserted = 0
    for r in match["rules"]:
        try:
            add_rule(
                client_id=client_id,
                name=r["name"],
                behavior_text=r["behavior_text"],
                trigger_keywords=list(r.get("trigger_keywords") or []),
                trigger_intent=r.get("trigger_intent"),
                escalate_to_owner=bool(r.get("escalate_to_owner")),
                source_scenario=scenario_key,
            )
            inserted += 1
        except Exception:
            continue
    return {"inserted": inserted, "scenario": match}
