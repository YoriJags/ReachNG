"""
Canonical vertical map — single source of truth.

Used by:
  - Dashboard SDR campaign picker (which verticals can be pitched)
  - SDR drafter (which prompt file to load + which extras to mention)
  - Brief primer seeding (which primers must exist)

Add a new vertical here, write a matching `agent/prompts/{vertical}.txt`,
add a matching primer to `services/brief/primers.py`, and the SDR can
pitch into it. No other code changes needed.

`extras` rule:
  - String → mention as an *included extra* AFTER the agent pitch, never the headline.
  - None    → no operational suite for this vertical yet — drafter leads with
              close-and-nurture only, no extras.
"""
from __future__ import annotations

VERTICALS: dict[str, dict] = {
    "real_estate": {
        "label":  "Real Estate",
        "extras": "Rent Roll + chase, KYC vault, Proof-of-Funds screener, Lawyer Handover Bundle, Property Concierge",
    },
    "recruitment": {
        "label":  "HR / Staffing / Recruitment",
        "extras": "full Nigerian payroll (PAYE/CRA/PENCOM/NHF), leave manager, attendance, probation tracker, policy oracle",
    },
    "legal": {
        "label":  "Legal Services",
        "extras": None,
    },
    "insurance": {
        "label":  "Insurance",
        "extras": None,
    },
    "fitness": {
        "label":  "Fitness / Wellness",
        "extras": None,
    },
    "events": {
        "label":  "Events / Hospitality",
        "extras": None,
    },
    "auto": {
        "label":  "Auto / Dealerships",
        "extras": None,
    },
    "cooperatives": {
        "label":  "Cooperatives / Thrift",
        "extras": None,
    },
    "fintech": {
        "label":  "Fintech",
        "extras": None,
    },
    "agriculture": {
        "label":  "Agriculture / Agribusiness",
        "extras": None,
    },
    "logistics": {
        "label":  "Logistics / Last-Mile",
        "extras": None,
    },
}


def list_verticals() -> list[str]:
    """All supported vertical slugs."""
    return list(VERTICALS.keys())


def vertical_label(vertical: str) -> str:
    return VERTICALS.get(vertical, {}).get("label", vertical.replace("_", " ").title())


def vertical_extras(vertical: str) -> str | None:
    """Operational suite blurb to mention as 'and-also' for vertical-matched prospects.
    None means no built suite for this vertical — drafter leads with the agent only.
    """
    return VERTICALS.get(vertical, {}).get("extras")
