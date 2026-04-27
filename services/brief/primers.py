"""
Vertical primers — Lagos-tuned defaults per industry.

Seeded into Mongo on app boot (idempotent — only inserts if missing). Edit
in the admin dashboard, not here, once the system is live; this file is the
seed-of-record only.
"""
from __future__ import annotations

from services.brief.store import VerticalPrimer, upsert_primer, get_primer
import structlog

log = structlog.get_logger()


_SEEDS: list[VerticalPrimer] = [
    VerticalPrimer(
        vertical="real_estate",
        label="Real Estate",
        vocabulary=[
            "unit", "viewing", "PoF", "service charge", "agreement",
            "agency fee", "legal fee", "caution deposit", "subject to status",
            "owner-occupier", "outright sale", "off-plan", "title",
        ],
        default_tone="aspirational, professional, calm-confident",
        default_qualifying_questions=[
            "What's your budget range?",
            "When are you looking to move in?",
            "Which areas are you considering?",
            "Is this for self-occupation, family, or investment?",
            "Do you need furnished or unfurnished?",
        ],
        default_objections=[
            "Agency fee is too high",
            "I want to see it first before committing",
            "I'm just browsing",
            "Owner is asking for too much",
            "I prefer to deal directly with the landlord",
        ],
        default_cta="book a viewing",
        compliance_notes=[
            "Lagos Tenancy Law applies to residential leases",
            "Never quote prices that are not authorised by the principal",
            "Disclose agency relationship at first contact",
        ],
        never_say_defaults=[
            "guaranteed appreciation",
            "no risk",
            "the owner is desperate",
            "below market value",
        ],
        sample_one_liner="Boutique luxury rentals across Banana Island, Ikoyi, and Eko Atlantic.",
    ),

    VerticalPrimer(
        vertical="legal",
        label="Legal Services",
        vocabulary=[
            "consultation", "retainer", "engagement letter", "scope of work",
            "billable", "draft", "review", "deed", "filing fee",
        ],
        default_tone="trust-building, precise, measured",
        default_qualifying_questions=[
            "What's the matter you'd like advice on?",
            "Is there a deadline or court date involved?",
            "Have you instructed counsel on this before?",
            "Are we acting individually or for a company?",
        ],
        default_objections=[
            "Lawyers are too expensive",
            "I'd rather try to resolve this myself first",
            "I'm not sure if I really need a lawyer",
        ],
        default_cta="book a consultation",
        compliance_notes=[
            "NBA Rules of Professional Conduct govern advertising tone",
            "Avoid guarantees of outcome",
            "Confidentiality applies from first contact",
        ],
        never_say_defaults=[
            "we will win this case",
            "guaranteed outcome",
            "cheaper than other lawyers",
        ],
        sample_one_liner="Family and property law boutique serving high-net-worth Lagos individuals.",
    ),

    VerticalPrimer(
        vertical="insurance",
        label="Insurance",
        vocabulary=[
            "premium", "claim", "rider", "coverage", "exclusion", "policy",
            "underwriter", "NAICOM", "indemnity", "endorsement",
        ],
        default_tone="trust-building, calm, factual",
        default_qualifying_questions=[
            "What kind of cover are you looking for — life, health, motor, property?",
            "Do you currently have a policy in force?",
            "Who would the cover be for — yourself, family, business?",
            "What's prompted you to look into this now?",
        ],
        default_objections=[
            "Insurance companies never pay claims",
            "I already have one through work",
            "It's too expensive",
            "I'd rather invest the money",
        ],
        default_cta="get a quote",
        compliance_notes=[
            "NAICOM disclosure requirements apply",
            "All material terms must be clear before binding",
            "Avoid guaranteed-return language for life products",
        ],
        never_say_defaults=[
            "guaranteed payout",
            "no exclusions apply",
            "claims are always paid",
        ],
        sample_one_liner="Independent broker placing life, health, and motor cover for Lagos professionals.",
    ),

    VerticalPrimer(
        vertical="fitness",
        label="Fitness & Wellness",
        vocabulary=[
            "session", "program", "transformation", "member", "split",
            "macros", "PR", "rep", "block", "deload", "trial class",
        ],
        default_tone="energetic, motivational, supportive — not preachy",
        default_qualifying_questions=[
            "What's the main goal — strength, fat loss, mobility, sport?",
            "How does your week look — when can you train?",
            "Have you trained consistently before?",
            "Any injuries or conditions we should plan around?",
        ],
        default_objections=[
            "I don't have time",
            "I've tried before and it didn't stick",
            "Gyms intimidate me",
            "It's too far from where I am",
        ],
        default_cta="book a free trial class",
        compliance_notes=[
            "No medical claims without a disclaimer",
            "Never present training as a substitute for medical care",
        ],
        never_say_defaults=[
            "guaranteed weight loss",
            "doctor recommended",
            "lose X kg in Y weeks",
        ],
        sample_one_liner="Strength-led personal training for busy professionals in VI and Lekki.",
    ),

    VerticalPrimer(
        vertical="events",
        label="Events & Hospitality",
        vocabulary=[
            "package", "deposit", "rider", "load-in", "run-of-show",
            "minimum spend", "covers", "AV", "decor", "MC", "vendor",
        ],
        default_tone="warm, organised, reassuring",
        default_qualifying_questions=[
            "What's the event — wedding, corporate, birthday, launch?",
            "What's your date and rough headcount?",
            "Do you have a venue or are we sourcing?",
            "What's your overall budget envelope?",
        ],
        default_objections=[
            "It's too expensive",
            "Another vendor offered me less",
            "I want to see references first",
            "Can I pay closer to the date?",
        ],
        default_cta="book a planning call",
        compliance_notes=[
            "Deposits and cancellation terms must be in writing",
            "Vendor liability and insurance disclosures where applicable",
        ],
        never_say_defaults=[
            "we never have weather problems",
            "this is the cheapest in Lagos",
        ],
        sample_one_liner="End-to-end wedding production in Lagos and destination weddings West Africa.",
    ),

    VerticalPrimer(
        vertical="auto",
        label="Auto Sales & Service",
        vocabulary=[
            "VIN", "service history", "warranty", "tokunbo", "registered",
            "duty", "test drive", "trade-in", "financing", "diagnostic",
        ],
        default_tone="straightforward, knowledgeable, no-nonsense",
        default_qualifying_questions=[
            "Which model and year are you targeting?",
            "Is this for personal, family, or business use?",
            "Are you trading in or buying outright?",
            "Do you need financing or paying cash?",
        ],
        default_objections=[
            "Other dealers are cheaper",
            "I want to see service records first",
            "I'd rather buy from abroad",
            "I want to bring my mechanic to inspect",
        ],
        default_cta="book a test drive",
        compliance_notes=[
            "Disclose accident history if known",
            "Title and customs documentation must be authentic",
        ],
        never_say_defaults=[
            "no accidents ever — guaranteed",
            "this is the lowest price in Lagos",
        ],
        sample_one_liner="Foreign-used premium SUVs and sedans, fully customs-cleared and inspected.",
    ),

    VerticalPrimer(
        vertical="cooperatives",
        label="Cooperatives & Thrift",
        vocabulary=[
            "contribution", "payout", "cycle", "member", "guarantor",
            "registration fee", "monthly due", "rotating", "esusu", "ajo",
        ],
        default_tone="warm, communal, transparent",
        default_qualifying_questions=[
            "Are you joining as an individual or with a group?",
            "What contribution amount works for your cycle?",
            "Have you been part of a cooperative before?",
            "Who will be your guarantor?",
        ],
        default_objections=[
            "I've heard of cooperatives that ran away with money",
            "I prefer to save with a bank",
            "What if I miss a contribution?",
        ],
        default_cta="book an onboarding call",
        compliance_notes=[
            "Avoid investment-product framing — this is mutual savings",
            "Be explicit about contribution and payout rules",
        ],
        never_say_defaults=[
            "guaranteed returns",
            "investment opportunity",
            "we are regulated by CBN",
        ],
        sample_one_liner="Workplace thrift cooperative for Lagos SME teams — transparent rotating savings.",
    ),
]


def seed_default_primers() -> dict:
    """Insert any primer that isn't yet in Mongo. Existing primers are NOT overwritten."""
    inserted = 0
    skipped = 0
    for primer in _SEEDS:
        if get_primer(primer.vertical):
            skipped += 1
            continue
        upsert_primer(primer)
        inserted += 1
    log.info("vertical_primers_seeded", inserted=inserted, skipped=skipped, total=len(_SEEDS))
    return {"inserted": inserted, "skipped": skipped, "total": len(_SEEDS)}
