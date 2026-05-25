"""
Dry-run preview of the ReachNG self-outreach drafter.

Generates email drafts against 5 hand-curated Lagos sample profiles and
prints them to stdout. NOTHING sends. NOTHING is queued. No DB writes.

Run from C:\\VIIBE\\ReachNG:
    python -m scripts.dry_run_outreach

Cost: ~5 × ₦4 ≈ ₦20 in Haiku tokens.
"""
from __future__ import annotations

import sys
from services.reachng_self_outreach import draft_with_link


# 5 plausible Lagos prospects across the priority verticals. Mix of
# decision-maker present/absent and review excerpt present/absent so we
# stress-test how the drafter handles thin vs rich enrichment.
SAMPLES = [
    {
        "label":     "1 · Premium hospitality (Victoria Island)",
        "business_name":   "Cocoon Lagos",
        "vertical":  "hospitality",
        "address":   "Eko Atlantic, Victoria Island, Lagos",
        "category":  "Rooftop restaurant & lounge",
        "rating":    4.6,
        "reviews_excerpt": "Food and view are 10/10 but they took 4 hours to confirm my reservation on a Saturday. Lost patience and went to Cantonese.",
        "contact_name":  "Adunni Okafor",
        "contact_title": "General Manager",
        "website":   "https://cocoon.ng",
        "contact_id": "demo_cocoon",
    },
    {
        "label":     "2 · Luxury real estate (Banana Island)",
        "business_name":   "Sandhill Properties",
        "vertical":  "real_estate",
        "address":   "1 Adeola Odeku, Ikoyi, Lagos",
        "category":  "Estate agent · luxury residential",
        "rating":    4.8,
        "reviews_excerpt": "Excellent agents but PoF verification took 9 days — I had moved on by then.",
        "contact_name":  "Tunde Bakare",
        "contact_title": "Managing Partner",
        "website":   "https://sandhillproperties.ng",
        "contact_id": "demo_sandhill",
    },
    {
        "label":     "3 · Boutique law firm (Ikoyi) — sparse enrichment",
        "business_name":   "Akinwale & Co.",
        "vertical":  "professional_services",
        "address":   "Awolowo Road, Ikoyi, Lagos",
        "category":  "Boutique law firm",
        "rating":    4.4,
        "reviews_excerpt": None,
        "contact_name":  None,
        "contact_title": None,
        "website":   "https://akinwaleandco.com",
        "contact_id": "demo_akinwale",
    },
    {
        "label":     "4 · Aesthetic clinic (Lekki Phase 1)",
        "business_name":   "Mira Aesthetics",
        "vertical":  "clinics",
        "address":   "Admiralty Way, Lekki Phase 1, Lagos",
        "category":  "Skin & aesthetic clinic",
        "rating":    4.7,
        "reviews_excerpt": "Amazing facials but the WhatsApp number never responds outside 9-5. Try DM-ing for a Saturday slot — good luck.",
        "contact_name":  "Dr. Mira Adesina",
        "contact_title": "Founder",
        "website":   "https://miraaesthetics.ng",
        "contact_id": "demo_mira",
    },
    {
        "label":     "5 · Fashion atelier (Yaba)",
        "business_name":   "Adire by Tomi",
        "vertical":  "small_business",
        "address":   "Herbert Macaulay Way, Yaba, Lagos",
        "category":  "Adire & ready-to-wear atelier",
        "rating":    4.9,
        "reviews_excerpt": "Beautiful pieces but answering DMs is slow — I waited 2 weeks for a quote on a wedding order.",
        "contact_name":  "Tomi Adeyemi",
        "contact_title": "Owner",
        "website":   "https://adirebytomi.com",
        "contact_id": "demo_tomi",
    },
]


def main() -> int:
    print(r"""
╔════════════════════════════════════════════════════════════════════════╗
║  ReachNG self-outreach — DRY RUN PREVIEW                               ║
║  Nothing sends. Nothing queues. Nothing writes to Mongo.               ║
║  Sender persona: Yori, founder. Channel: email via hello@reachng.ng.   ║
╚════════════════════════════════════════════════════════════════════════╝
""".strip())
    failures = 0
    for sample in SAMPLES:
        label = sample.pop("label")
        print(f"\n────────────────────────────────────────────────────────────────────────")
        print(f"  {label}")
        print(f"  {sample['business_name']} · {sample.get('category','')}")
        if sample.get("contact_name"):
            print(f"  decision-maker: {sample['contact_name']}, {sample.get('contact_title','')}")
        else:
            print(f"  decision-maker: (none — sparse enrichment)")
        print(f"────────────────────────────────────────────────────────────────────────")
        try:
            out = draft_with_link(**sample)
        except Exception as e:
            failures += 1
            print(f"  ✗ FAILED: {e}")
            continue
        word_count = len([w for w in (out["message"] or "").split() if w])
        print(f"\n  Subject:  {out['subject']}")
        print(f"  Body ({word_count} words):\n")
        for line in (out["message"] or "").splitlines():
            print(f"      {line}")
    print(f"\n────────────────────────────────────────────────────────────────────────")
    print(f"Done — 5 drafts generated, {failures} failure(s).")
    print(f"Eyeball the copy. If it lands: kill the dry-run mental gate and run the")
    print(f"real campaign against 50 hand-curated Lagos businesses with HITL on every send.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
