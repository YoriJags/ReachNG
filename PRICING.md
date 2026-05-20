# ReachNG — Pricing Working Doc

Locked premises (don't relitigate):
- **Unipile 100%** for WhatsApp. No Meta Cloud API. Per-client fixed cost ~₦24k/mo + shared infra.
- **HITL non-negotiable.** Every outbound is human-approved unless owner explicitly flips Autopilot per reply-type.
- **Lagos + Abuja pilot.** Premium SME positioning. Hand-onboarded, selective intake.
- **First paid client target:** lock pricing today so signup + pricing page reflect reality before any paid signup.

Last updated: 2026-05-20

---

## 1 · Cost floor per client (Unipile-only, Mongo Atlas free tier)

From [ECONOMICS.md](./ECONOMICS.md) §6, with Meta Cloud option removed, Unipile assumed, and Mongo on free tier (₦0 today):

| Profile | Per-call AI | Per-client fixed (Unipile + Resend) | Platform share (÷10 clients) | **Total cost/mo** |
|---|---:|---:|---:|---:|
| Light  | 2,520 | 12,000 | 6,100 | **~₦20,620** |
| Medium | 7,620 | 12,000 | 6,100 | **~₦25,720** |
| Heavy  | 18,840 | 12,000 | 6,100 | **~₦36,940** |

These are the floors. Any price below means a loss on that profile.

**Unipile pricing reality (corrected 2026-05-20):** First 10 connected accounts = $55/mo flat (~₦88,000 total = ₦8,800/client). Then $5.5 per additional (11-50), $5 (51-200), $4.5 (201-1k). Per-client Unipile cost stays in the ₦7,400-8,800 band across all scales.

**Platform share (₦6,100/client at 10 clients)** includes Railway + Resend Pro + PostHog + Claude Pro subscription + domain + Apify SDR funnel. Claude upgrades to Max 5× (~₦160k) around 15 clients, Max 20× (~₦320k) around 50 clients. Still negligible per-client at scale (~₦3k each at 100 clients).

**Note on Mongo:** you're on Atlas free tier (M0, 512MB) today, so MongoDB cost is ₦0. When client volume + memory data outgrows free tier (around client 8-12 depending on usage), expect to move to M10 (~₦91,000/mo). Re-run the floor table at that point — every profile will rise by ~₦9k. Still healthy on the locked ladder.

---

## 2 · The three plausible ladders

### Ladder A — Light bump (₦100 / 200 / 400)

| Plan | Price | Margin on Light | Margin on Medium | Margin on Heavy |
|---|---:|---:|---:|---:|
| Starter | ₦100,000 | +₦62,600 (63%) | +₦57,500 (58%) | +₦46,300 (46%) |
| Growth  | ₦200,000 | +₦162,600 (81%) | +₦157,500 (79%) | +₦146,300 (73%) |
| Scale   | ₦400,000 | +₦362,600 (91%) | +₦357,500 (89%) | +₦346,300 (87%) |

**Read:** Starter tight on heavy clients (46%). Growth and Scale clean.

### Ladder B — Operator-grade (₦150 / 300 / 600) — *previously locked, superseded — see note below*

| Plan | Price | Margin on Light | Margin on Medium | Margin on Heavy |
|---|---:|---:|---:|---:|
| Starter | ₦150,000 | +₦112,600 (75%) | +₦107,500 (72%) | +₦96,300 (64%) |
| Growth  | ₦300,000 | +₦262,600 (88%) | +₦257,500 (86%) | +₦246,300 (82%) |
| Scale   | ₦600,000 | +₦562,600 (94%) | +₦557,500 (93%) | +₦546,300 (91%) |

**Read:** every tier × every profile margin >64%. Worst case (Heavy on Starter) is still healthy 64%. Headroom for surprise spikes and the eventual Mongo M10 + Claude Max upgrades.

### Ladder C — Premium-anchor (₦200 / 400 / 800)

| Plan | Price | Margin on Light | Margin on Medium | Margin on Heavy |
|---|---:|---:|---:|---:|
| Starter | ₦200,000 | +₦162,600 (81%) | +₦157,500 (79%) | +₦146,300 (73%) |
| Growth  | ₦400,000 | +₦362,600 (91%) | +₦357,500 (89%) | +₦346,300 (87%) |
| Scale   | ₦800,000 | +₦762,600 (95%) | +₦757,500 (95%) | +₦746,300 (93%) |

**Read:** aggressive but defensible. "₦200k/mo is two days of a senior receptionist's salary, except this one never sleeps." Risk: prices out non-luxury verticals (beauty, small hospitality), narrows TAM.

---

## 3 · How the math behaves at scale

At 10 paying clients (Ladder B, mix of usage):

| Mix | Monthly revenue | Monthly cost | Monthly profit | Margin |
|---|---:|---:|---:|---:|
| 5 Starter + 3 Growth + 2 Scale | ₦2.85M | ₦420,000 | ₦2.43M | 85% |
| 3 Starter + 5 Growth + 2 Scale | ₦3.15M | ₦425,000 | ₦2.73M | 87% |
| 2 Starter + 4 Growth + 4 Scale | ₦3.90M | ₦440,000 | ₦3.46M | 89% |

**Read:** annualised ₦29-42M revenue from 10 clients. Strong unit economics. Even on Ladder B alone, 10 clients gives a healthy runway with very thin OpEx (Atlas free tier + Railway + Resend = real fixed costs under ₦60k/mo).

### Reaching 50 clients on Ladder B

Assume 25 Starter, 20 Growth, 5 Scale = ₦12.75M MRR = **₦153M ARR**.

⚠️ At ~10-12 paying clients we'll outgrow Atlas free tier. Move to M10 (~₦91k/mo). Blended margin still ~88% at scale. Real numbers.

---

## 4 · Annual prepay (keep or adjust)

Current PRODUCTS.md offers **15% off annual prepay**. With Ladder B:

| Plan | Monthly | Annual prepay (15% off) | Cash collected | Equivalent monthly |
|---|---:|---:|---:|---:|
| Starter | ₦150,000 | ₦1,530,000 | ₦1,530,000 | ₦127,500 |
| Growth  | ₦300,000 | ₦3,060,000 | ₦3,060,000 | ₦255,000 |
| Scale   | ₦600,000 | ₦6,120,000 | ₦6,120,000 | ₦510,000 |

**Cash on day 1** if a client takes Scale annual = ₦6.12M. That alone funds 4 months of platform fixed costs.

**Recommendation: keep 15% annual discount.** It's the founder-friendly close on a longer commitment.

---

## 5 · Plan inclusions (what changes by tier)

Before locking prices, lock what's IN each plan. Strawman:

| Feature | Starter | Growth | Scale |
|---|:-:|:-:|:-:|
| EYO on owner's WhatsApp via Unipile pairing | ✓ | ✓ | ✓ |
| HITL draft queue | ✓ | ✓ | ✓ |
| Voice note transcription (EN/Pidgin/Yo/Ig/Ha safe-switch) | ✓ | ✓ | ✓ |
| Receipt screenshot reader | ✓ | ✓ | ✓ |
| Morning Owner Brief | ✓ | ✓ | ✓ |
| Business Brief intake + tone learning | ✓ | ✓ | ✓ |
| Per-vertical Control Room | ✓ | ✓ | ✓ |
| Re-engagement (Past / Dormant / Hot bucket triage) | — | ✓ | ✓ |
| BYO Leads ingest (vCard / paste / CSV / WhatsApp share) | — | ✓ | ✓ |
| Outcome learning loop (T0.4) | — | ✓ | ✓ |
| Proactive Intelligence (festival nudges, capacity, birthdays) | — | — | ✓ |
| Co-Pilot (owner asks EYO questions) | — | — | ✓ |
| Multi-location coordination | — | — | ✓ |
| Voice Operator (outbound voice agent) | — | — | ✓ |
| Priority response (15 min during business hours) | — | — | ✓ |
| Architecture tour + bespoke modules | — | — | ✓ |

This forces an honest reason for each upgrade. Owners can see what they get by stepping up.

---

## 6 · Pilot-phase pricing (first 3-5 clients only)

Live pricing should be Ladder B. But for the **first 3 pilot clients**, a one-time pilot discount makes sense to reduce friction and generate case studies:

| Plan | Live price | Pilot price (first 90 days) | Lock |
|---|---:|---:|---|
| Starter | ₦150,000 | ₦100,000 | converts to live price month 4 |
| Growth | ₦300,000 | ₦200,000 | converts month 4 |
| Scale | ₦600,000 | ₦400,000 | converts month 4 |

Frame to pilot owners: *"You're getting our first-customer rate. After 90 days you move to standard pricing or cancel, your choice."* That's defensible, not a discount-spiral.

---

## 7 · Recommendation to lock today

1. **Ladder B (₦150 / 300 / 600 monthly).** 65-89% margin across all client profiles. Headroom for surprises.
2. **15% off annual prepay.** Keep. Closes long deals fast.
3. **Plan inclusions per §5.** Forces clean upgrade paths.
4. **Pilot pricing per §6** for first 3 clients only, time-boxed to 90 days.

If this looks right, downstream code updates needed:

- `services/platform_settings.py::get_plan_pricing()` → set new tier values
- `templates/marketing/pricing.html` → headline numbers, feature delta matrix
- `templates/marketing/signup.html` → plan picker labels
- `api/marketing.py::PLAN_PRICING` → fallback constants
- `PRODUCTS.md` → canonical tier definitions
- Welcome email + portal copy → reflect new amounts

I can ship all 6 in one bundle in ~30 minutes once you sign off on Ladder B (or pick a different ladder, or tune the numbers).

---

## 8 · The questions only you can answer

Before I ship anything:

1. **Ladder A / B / C — which one?** Default is B.
2. **Pilot pricing — yes or no?** Default yes for first 3 clients, off after that.
3. **What's the highest you'd actually quote a Banana Island estate agency or a Maitama clinic with a straight face?** Calibrates whether Scale should be ₦600k, ₦800k, or higher.
4. **What's the *lowest* you'd take from a small Surulere restaurant founder who really wants in?** Calibrates whether we keep Starter at ₦150k or add a Lite ₦100k.

Drop your four answers and I'll lock + ship.
