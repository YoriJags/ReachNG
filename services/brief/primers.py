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

    VerticalPrimer(
        vertical="recruitment",
        label="HR / Staffing / Recruitment",
        vocabulary=[
            "shortlist", "candidate", "JD", "screening", "probation",
            "PAYE", "PENCOM", "NHF", "CRA", "headcount", "retainer",
            "contract staff", "permanent", "background check",
        ],
        default_tone="professional, organised, calm-under-pressure",
        default_qualifying_questions=[
            "How many roles are you trying to fill right now?",
            "Are these contract or permanent positions?",
            "What's your timeline to onboard?",
            "Have you defined the JD or do you need help shaping it?",
        ],
        default_objections=[
            "We've used agencies before and got bad shortlists",
            "Your fee is too high",
            "We can post on LinkedIn / Jobberman ourselves",
            "We need someone yesterday",
        ],
        default_cta="book a 15-min scoping call",
        compliance_notes=[
            "NDPR applies to candidate CV data",
            "Avoid disclosing one candidate's details to another client",
            "Background checks require candidate consent in writing",
        ],
        never_say_defaults=[
            "guaranteed hire",
            "we know everyone in your industry",
            "100% retention",
        ],
        sample_one_liner="Lagos staffing partner for finance, tech, and ops roles — vetted shortlists in 7 days.",
    ),

    VerticalPrimer(
        vertical="fintech",
        label="Fintech",
        vocabulary=[
            "KYC", "BVN", "NIN", "limit", "tier", "settlement", "MCC",
            "chargeback", "merchant", "wallet", "payout", "PCIDSS",
            "CBN sandbox", "PSSP", "PSP", "switching",
        ],
        default_tone="precise, compliant, founder-grade",
        default_qualifying_questions=[
            "What stage are you at — pre-launch, beta, or live?",
            "Are you a PSSP, PSP, MMO, or something else?",
            "Who's your settlement bank / sponsor?",
            "What's your monthly transaction volume?",
        ],
        default_objections=[
            "We can build this in-house",
            "Our compliance team won't approve a third-party",
            "We're already using [competitor]",
        ],
        default_cta="book a technical scoping call",
        compliance_notes=[
            "CBN regulations apply — never claim we are licensed",
            "NDPR + PCIDSS for any card data handling",
            "Marketing claims about 'instant settlement' need disclaimers",
        ],
        never_say_defaults=[
            "regulated by the CBN",
            "guaranteed instant",
            "no chargebacks",
            "fully PCI compliant out of the box",
        ],
        sample_one_liner="Lagos-built payment infrastructure for Nigerian SMEs.",
    ),

    VerticalPrimer(
        vertical="agriculture",
        label="Agriculture / Agribusiness",
        vocabulary=[
            "off-take", "input financing", "smallholder", "aggregator",
            "yield", "season", "harvest", "cold chain", "warehouse receipt",
            "extension", "AGSMEIS", "NIRSAL", "anchor borrower",
        ],
        default_tone="grounded, practical, peer-to-peer with operators",
        default_qualifying_questions=[
            "What crops or livestock are you working with?",
            "Are you producing, aggregating, processing, or distributing?",
            "Do you have off-takers lined up or still searching?",
            "What's your hectarage / monthly volume?",
        ],
        default_objections=[
            "Margins are too thin to add tooling",
            "Network is bad in our farm location",
            "We've been burned by tech promises before",
        ],
        default_cta="book a 15-min call",
        compliance_notes=[
            "Avoid claims about NIRSAL / CBN / AGSMEIS approval — we are not a financier",
            "Do not promise off-takers we have not signed",
        ],
        never_say_defaults=[
            "guaranteed off-take",
            "guaranteed yield improvement",
            "we are partnered with NIRSAL",
        ],
        sample_one_liner="Off-take and aggregation operator serving Lagos & South-West farms.",
    ),

    VerticalPrimer(
        vertical="logistics",
        label="Logistics / Last-Mile",
        vocabulary=[
            "rider", "dispatch", "SLA", "POD", "consignment", "manifest",
            "fleet", "route", "load factor", "turnaround", "geofence",
            "third-party logistics", "3PL", "last-mile", "intra-city",
        ],
        default_tone="operational, fast, no-fluff",
        default_qualifying_questions=[
            "How many deliveries / shipments per day?",
            "Intra-city, inter-state, or both?",
            "Own fleet, contracted riders, or hybrid?",
            "What's your biggest pain — late deliveries, lost packages, or rider management?",
        ],
        default_objections=[
            "We've tried logistics tooling and it didn't fit our flow",
            "Our riders won't use another app",
            "Our customers prefer WhatsApp updates",
        ],
        default_cta="book a 20-min ops walkthrough",
        compliance_notes=[
            "Lagos State Transport regulations apply for inter-state",
            "Driver/rider data is NDPR-covered",
        ],
        never_say_defaults=[
            "guaranteed on-time",
            "zero failed deliveries",
            "we replace your dispatcher",
        ],
        sample_one_liner="Last-mile dispatch operator covering Lagos mainland and island corridors.",
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
