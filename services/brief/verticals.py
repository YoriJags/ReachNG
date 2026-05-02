"""
Canonical vertical map — single source of truth.

Used by:
  - Dashboard SDR campaign picker (which verticals can be pitched, in what order)
  - SDR drafter (which prompt file to load, which framing to use, which extras to mention)
  - Brief primer seeding (which primers must exist)

Add a new vertical here, write a matching `agent/prompts/{vertical}.txt`,
add a matching primer to `services/brief/primers.py`, and the SDR can
pitch into it. No other code changes needed.

Field semantics:
  label             — human-friendly name shown in pickers.
  pitch_mode        — "inbound_closer" | "workload_removal".
                      Determines the headline framing the SDR drafter uses.
                        - inbound_closer  → "we close the leads you already have"
                        - workload_removal → "we run the operational back-office that frees your team"
  outreach_priority — "tier_1" | "tier_2" | "internal".
                      tier_1   → cold outreach prioritised here. Inbound-driven verticals where the agent close pitch lands hard.
                      tier_2   → can be pitched but the sales cycle is longer / pain is diffuse. Use only when we have warm intros.
                      internal → never cold-pitched. Reserved for our own SDR funnel meta-vertical.
  extras            — operational suite blurb to mention as 'and-also' for vertical-matched prospects.
                      None means no built suite for this vertical — drafter leads with the pitch_mode framing only.
"""
from __future__ import annotations

VERTICALS: dict[str, dict] = {
    # ── Tier 1: inbound-driven, agent-close pitch lands hard ──
    "real_estate": {
        "label":             "Real Estate",
        "pitch_mode":        "inbound_closer",
        "outreach_priority": "tier_1",
        "extras":            "Rent Roll + chase, KYC vault, Proof-of-Funds screener, Lawyer Handover Bundle, Property Concierge",
    },
    "insurance": {
        "label":             "Insurance",
        "pitch_mode":        "inbound_closer",
        "outreach_priority": "tier_1",
        "extras":            None,
    },
    "fitness": {
        "label":             "Fitness / Wellness",
        "pitch_mode":        "inbound_closer",
        "outreach_priority": "tier_1",
        "extras":            None,
    },
    "auto": {
        "label":             "Auto / Dealerships",
        "pitch_mode":        "inbound_closer",
        "outreach_priority": "tier_1",
        "extras":            None,
    },
    "events": {
        "label":             "Events / Hospitality",
        "pitch_mode":        "inbound_closer",
        "outreach_priority": "tier_1",
        "extras":            None,
    },
    "legal": {
        "label":             "Legal Services",
        "pitch_mode":        "inbound_closer",
        "outreach_priority": "tier_1",
        "extras":            None,
    },

    # ── Tier 2: workload-removal pitch, longer cycle, warmer intros preferred ──
    "recruitment": {
        "label":             "HR / Staffing / Recruitment",
        "pitch_mode":        "workload_removal",
        "outreach_priority": "tier_2",
        "extras":            "full Nigerian payroll (PAYE/CRA/PENCOM/NHF), leave manager, attendance, probation tracker, policy oracle",
    },
    "cooperatives": {
        "label":             "Cooperatives / Thrift",
        "pitch_mode":        "workload_removal",
        "outreach_priority": "tier_2",
        "extras":            None,
    },
    "fintech": {
        "label":             "Fintech",
        "pitch_mode":        "workload_removal",
        "outreach_priority": "tier_2",
        "extras":            None,
    },
    "agriculture": {
        "label":             "Agriculture / Agribusiness",
        "pitch_mode":        "workload_removal",
        "outreach_priority": "tier_2",
        "extras":            None,
    },
    "logistics": {
        "label":             "Logistics / Last-Mile",
        "pitch_mode":        "workload_removal",
        "outreach_priority": "tier_2",
        "extras":            None,
    },
}


def list_verticals() -> list[str]:
    """All supported vertical slugs, ordered priority-first."""
    return list(VERTICALS.keys())


def list_tier_1() -> list[str]:
    """Inbound-closer verticals — prioritise these for cold outreach."""
    return [v for v, m in VERTICALS.items() if m.get("outreach_priority") == "tier_1"]


def list_tier_2() -> list[str]:
    """Workload-removal verticals — pitch only with warm intros / longer cycle."""
    return [v for v, m in VERTICALS.items() if m.get("outreach_priority") == "tier_2"]


def vertical_label(vertical: str) -> str:
    return VERTICALS.get(vertical, {}).get("label", vertical.replace("_", " ").title())


def vertical_extras(vertical: str) -> str | None:
    """Operational suite blurb to mention as 'and-also' for vertical-matched prospects.
    None means no built suite for this vertical — drafter leads with pitch_mode framing only.
    """
    return VERTICALS.get(vertical, {}).get("extras")


def vertical_pitch_mode(vertical: str) -> str:
    """'inbound_closer' or 'workload_removal'. Default to inbound_closer if unknown."""
    return VERTICALS.get(vertical, {}).get("pitch_mode", "inbound_closer")
