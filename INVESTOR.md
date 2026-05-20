# ReachNG — Investor Brief

The agentic employee for premium Nigerian SMEs. Built in Lagos. Operating in Lagos and Abuja.

> ReachNG is the WhatsApp-native customer operator for premium Lagos and Abuja SMEs. EYO drafts every reply in the owner's voice, parses GTBank/OPay transfer screenshots, qualifies leads, reactivates dormant customers, and briefs the founder every morning. Every message is human-approved by default. We don't replace the team — we give them a colleague that never sleeps.

Last updated: 2026-05-20 · Stage: Pre-revenue, live product, first paid client imminent

---

## 1 · One-page snapshot

| | |
|---|---|
| **What we sell** | Monthly SaaS subscription. Owner pairs ReachNG to their existing WhatsApp number via Unipile QR. EYO operates from that number under HITL approval. |
| **Who we sell to** | Premium SMEs in Lagos and Abuja: luxury hospitality, real estate agencies (Banana Island / Ikoyi / Maitama tier), clinics, commercial law, family offices, professional services. |
| **Pricing (live)** | Starter ₦150k / Growth ₦300k / Scale ₦600k per month. 15% off annual prepay. |
| **Per-client gross margin** | 66 – 94% across all profile × tier combinations (see §3) |
| **Stack** | Python 3.12 + FastAPI + Mongo Atlas + Anthropic Haiku 4.5 + OpenAI Whisper + Unipile + Resend + Paystack + PostHog. Railway deploy. |
| **HQ** | Lagos, Nigeria |
| **Founder** | Oluyori Ajagun — back-office and risk operator (WFunded, formerly). Built the product from inside the pain it solves. |
| **Capital required for first 10 paying clients** | Negligible. Free tiers cover all infra. Cash positive in month 1 at first paid client. |

---

## 2 · The market

### TAM — Premium Lagos + Abuja SMEs

- **Lagos:** ~2.5M registered small/medium businesses. Premium subset (>20 staff, >₦50M revenue, or luxury-coded sector) ≈ **50,000-80,000 businesses.**
- **Abuja:** ~500,000 businesses. Premium subset (Maitama, Wuse, Asokoro, Jabi) ≈ **10,000-15,000.**
- **Combined premium tier** = ~**60,000-95,000 businesses.**

### Beachhead — Our ICP within TAM

Premium businesses that already live on WhatsApp for inbound, have 5+ staff, transact via bank transfer, and feel the late-evening leakage problem acutely:

- Luxury hospitality (premium restaurants, hotels, event venues, lounges)
- Real estate (sales + rental, Banana Island / Ikoyi / Eko Atlantic / Maitama tier)
- Clinics (aesthetic, dental, wellness, fertility)
- Commercial law and advisory
- Family offices
- High-ticket retail (auto, jewellery, art)

Conservative ICP count: ~**5,000-10,000 businesses across both cities**. At 2% penetration = 100-200 clients = ₦18-36M MRR on the current ladder.

### Why Lagos + Abuja, not all-Nigeria

- Concentration of premium businesses
- WhatsApp Business penetration ≈ 95%
- Naira + Paystack-native, no FX friction
- Founders are decision-makers who can sign in days, not months
- Operator (Yori) is on the ground in Lagos with a network

National expansion (Port Harcourt, Ibadan, Kano) is a year-2 move, not year-1.

### Buy-trigger

The premium-SME version of "AI for business" tools is broken in Nigeria. Generic foreign SaaS (HubSpot, Drift, Intercom) doesn't speak Paystack, naira, or Pidgin. Local tools are either thin CRMs or bulk SMS senders. There's no agentic WhatsApp operator built for this market. We're the first.

---

## 3 · Unit economics (see [ECONOMICS.md](./ECONOMICS.md) for the full breakdown)

### Cost floor per client per month (Unipile-paired, Mongo on free tier today)

| Profile | Per-call AI | Per-client fixed | Platform share (÷10) | **Total cost** |
|---|---:|---:|---:|---:|
| Light  | ₦2,520 | ₦25,600 | ₦6,100 | **₦34,200** |
| Medium | ₦7,620 | ₦25,600 | ₦6,100 | **₦39,300** |
| Heavy  | ₦18,840 | ₦25,600 | ₦6,100 | **₦50,500** |

Light = small restaurant / single agent. Medium = premium hospitality / mid clinic / established agency. Heavy = high-volume clinic / multi-location restaurant / busy agency.

### Gross margin per tier × profile

| | Light client | Medium client | Heavy client |
|---|---:|---:|---:|
| **Starter ₦150k**  | 77% | 74% | 66% |
| **Growth ₦300k**   | 89% | 87% | 83% |
| **Scale ₦600k**    | 94% | 93% | 92% |

**Worst case is 66% gross margin** (Heavy-usage client on Starter plan). Best case is 94%.

### What scales how

- **Per-call costs** (Whisper, Haiku, Vision): scale linearly with usage. Buffered ~30-50% above raw vendor pricing in the ledger to absorb FX swings and retries.
- **Per-client fixed:** Unipile per-account fee (~₦24k) is the dominant cost. Scales linearly with client count.
- **Platform fixed:** Railway + Resend + PostHog + Mongo are roughly fixed regardless of client count, but Mongo upgrades from free to M10 (~₦91k/mo) at ~10-12 clients. Modelled below.

---

## 4 · Revenue projections — three scenarios

All projections use Ladder B (₦150 / 300 / 600). Pilot pricing (33% off first 3 clients × 90 days) factored into year-1 numbers.

### Mix assumption

- Starter clients: ~50% of book (smaller premium SMEs)
- Growth clients: ~40% of book (mid-size premium)
- Scale clients: ~10% of book (luxury / multi-location)

This is the conservative weighting — Lagos/Abuja market data suggests Growth tier may end up ~50% as buyers self-select up.

### Scenario A — Conservative (slow ramp)

| Month | Clients | MRR | Monthly cost | Monthly profit | Margin |
|---:|---:|---:|---:|---:|---:|
| M3   | 3   | ₦450,000   | ₦170,000   | ₦280,000   | 62% (pilot pricing) |
| M6   | 8   | ₦1,800,000 | ₦330,000   | ₦1,470,000 | 82% |
| M12  | 20  | ₦5,250,000 | ₦830,000*  | ₦4,420,000 | 84% |
| M24  | 50  | ₦13,125,000| ₦2,080,000 | ₦11,045,000| 84% |

\*Includes Mongo M10 transition around client 10.

**Year-1 ARR exit: ₦63M.** Year-2 ARR exit: **₦157M.**

### Scenario B — Base case

| Month | Clients | MRR | Monthly cost | Monthly profit | Margin |
|---:|---:|---:|---:|---:|---:|
| M3   | 5   | ₦750,000   | ₦210,000   | ₦540,000   | 72% (pilot pricing) |
| M6   | 15  | ₦3,375,000 | ₦620,000   | ₦2,755,000 | 82% |
| M12  | 40  | ₦10,500,000| ₦1,720,000 | ₦8,780,000 | 84% |
| M24  | 100 | ₦26,250,000| ₦4,170,000 | ₦22,080,000| 84% |

**Year-1 ARR exit: ₦126M.** Year-2 ARR exit: **₦315M.**

### Scenario C — Aggressive (network effects + referral kick in)

| Month | Clients | MRR | Monthly cost | Monthly profit | Margin |
|---:|---:|---:|---:|---:|---:|
| M3   | 8   | ₦1,200,000 | ₦330,000   | ₦870,000   | 73% (pilot pricing) |
| M6   | 25  | ₦5,625,000 | ₦1,040,000 | ₦4,585,000 | 82% |
| M12  | 75  | ₦19,687,500| ₦3,200,000 | ₦16,487,500| 84% |
| M24  | 200 | ₦52,500,000| ₦8,340,000 | ₦44,160,000| 84% |

**Year-1 ARR exit: ₦236M.** Year-2 ARR exit: **₦630M.**

### Margin trajectory (all scenarios)

Margins **expand with scale**, not contract:
- Sub-10 clients: 66-89% (pilot pricing + lower volume)
- 10-50 clients: 82-87% (Mongo M10 cost absorbed)
- 50+ clients: 84-89% (per-client fixed share drops further)

The Unipile per-account fee is the only line that scales linearly with clients. Everything else compounds in our favour.

---

## 4.5 · Road to 1,000 clients (the headline goal)

1,000 paying clients ≈ 10-20% of the addressable premium SME beachhead in Lagos and Abuja. The path, broken into quarterly milestones, all on Ladder B pricing:

### Year 1 — Foundation (0 → 100)

| Quarter | Target clients (cumulative) | Net adds | MRR at quarter-end | Notes |
|---|---:|---:|---:|---|
| Q1 (M1-3)  | 5    | +5   | ₦750,000   | Pilot batch, hand-onboarded, 33% pilot discount in effect |
| Q2 (M4-6)  | 25   | +20  | ₦5,625,000 | Pricing live, founder-led sales, referrals start |
| Q3 (M7-9)  | 60   | +35  | ₦13,500,000| Vertical case studies live, Twitter authority cadence |
| Q4 (M10-12)| 100  | +40  | ₦22,500,000| First sales/CS hire mid-Q4 |

**Year-1 exit:** 100 clients · ₦22.5M MRR · **₦270M ARR**

### Year 2 — Velocity (100 → 600)

| Quarter | Target clients | Net adds | MRR | Notes |
|---|---:|---:|---:|---|
| Q5 (M13-15)| 175  | +75  | ₦39.4M | First SDR hire, paid acquisition unlocked |
| Q6 (M16-18)| 275  | +100 | ₦61.9M | Agency partnership channel live |
| Q7 (M19-21)| 425  | +150 | ₦95.6M | Conference + brand campaign, Abuja office |
| Q8 (M22-24)| 600  | +175 | ₦135.0M| 2nd engineer hire |

**Year-2 exit:** 600 clients · ₦135M MRR · **₦1.62B ARR**

### Year 3 — Compounding (600 → 1,000)

| Quarter | Target clients | Net adds | MRR | Notes |
|---|---:|---:|---:|---|
| Q9 (M25-27) | 750   | +150 | ₦168.8M | Voice Operator (outbound) launches |
| Q10 (M28-30)| 850   | +100 | ₦191.3M | National expansion (Port Harcourt, Ibadan) |
| Q11 (M31-33)| 925   | +75  | ₦208.1M | Vertical SDK / API offering |
| Q12 (M34-36)| **1,000** | +75 | **₦225.0M** | West Africa pilot (Accra, Nairobi) |

**Year-3 exit at 1,000 clients:** ₦225M MRR · **₦2.7B ARR · ~85% blended margin · ~₦191M monthly net profit.**

### Cost at each milestone

| Clients | MRR | Direct cost | Team cost | Mongo tier | Total cost | Net margin |
|---:|---:|---:|---:|---|---:|---:|
| 25    | ₦5.6M   | ₦780k    | Founder only | Atlas free | ₦780k    | 86% |
| 100   | ₦22.5M  | ₦3.5M    | +1 ops/CS    | M10 ₦91k   | ₦4M      | 82% |
| 250   | ₦56.3M  | ₦8.5M    | +SDR + accountant | M20 ₦232k | ₦11.5M | 80% |
| 500   | ₦112.5M | ₦16.7M   | +2 engineers + CS | M20      | ₦24M     | 79% |
| 1,000 | ₦225M   | ₦32M     | ~15-person org | M30 ₦617k | ₦48M     | 79% |

**Read:** even at 1,000 clients with a 15-person Lagos team, blended net margin sits ~79%. The model is built for compounding profitability, not just compounding revenue.

### Hire plan along the curve

| Milestone | Hires added |
|---|---|
| 25 clients   | First ops / customer success generalist |
| 75 clients   | First SDR (replaces founder-led outreach) |
| 100 clients  | Accountant / bookkeeper (PT) |
| 250 clients  | Lead engineer + CS lead |
| 500 clients  | 2 more engineers + 2 more SDR + Head of Sales |
| 1,000 clients| Country leads (Lagos / Abuja / PH), VP Eng, VP Customer Ops |

Final-state org: ~15 people. Revenue per employee at 1,000 clients = ₦180M/year. Industry benchmark for high-margin SaaS is ₦40-80M/employee. We'd be top-quartile.

### What the 1,000-client outcome looks like

- **₦2.7B annualised revenue**
- **₦2.3B annualised net profit**
- **15-person team across Lagos / Abuja / Port Harcourt**
- **Default agentic-employee platform for the Nigerian premium SME tier**
- **Optionality:** vertical SDKs (real estate, hospitality), API offering, regional expansion, acquisition target for global CRM consolidators (HubSpot, Salesforce) at 5-8× ARR multiple = ₦13-22B valuation

---

## 5 · Customer acquisition

### Channel today

- **Own SDR funnel** (Google Maps Places + Apollo + Apify + Twitter/LinkedIn signals → enrichment → Haiku-drafted email/WhatsApp outreach → HITL approval by Yori → send from hello@reachng.ng).
- **Pilot Application waitlist** at reachng.ng/waitlist (with PostHog tracking for source attribution).
- **Founder authority** — Yori posting on Twitter/LinkedIn about agent operations as the proof.

### CAC

- Variable cost: ~₦8k/mo Apify token, ~₦5k/mo for Resend + Anthropic on outreach. Call it **₦15k/mo of variable acquisition cost**.
- Yori's time: a real cost but uncapitalised for first ~20 clients.
- **Pure CAC per client ≤ ₦5,000** through bootstrapped channels. Effectively negligible.

### LTV (conservative)

- Average contract: 24 months (premium SaaS norm; switching cost is high once WhatsApp paired)
- Blended ARPC: ₦250,000/mo (across Starter/Growth/Scale)
- Gross margin: 84% blended
- **LTV = 24 × 250,000 × 0.84 = ₦5,040,000 per client**

### LTV / CAC

At ₦5,000 CAC and ₦5.04M LTV = **1,008× LTV/CAC ratio**. The benchmark anyone respects is >3×. This number won't hold once we run paid acquisition or hire SDRs, but the bootstrapped phase is exceptional.

### Paid CAC ceiling

If LTV is ₦5M and we want to keep LTV/CAC > 5×, we can spend up to **₦1M acquiring a client** before economics break. Plenty of headroom for paid social, partnership commissions, conference sponsorships when the time comes.

---

## 6 · Why this is defensible (the moats — see also [`memory/project_reachng_ai_moats.md`](../../Users/OAJAGUN/.claude/projects/c--VIIBE/memory/project_reachng_ai_moats.md))

The Claude / OpenAI / Google horizontal AI commoditisation question matters. Five moats:

1. **Distribution, not intelligence.** The hard part isn't drafting a reply — Haiku does that. The hard part is being wired into the SME's *actual* WhatsApp number, with HITL queue, receipt parsing, ledger reconciliation, Paystack subscription billing. Generic Claude doesn't ship that.
2. **Integration tax.** Unipile + Meta + Anthropic + OpenAI + Resend + Paystack + Mongo + LeanScrape took 4 months to integrate cleanly. Each week of work is a week a competitor would need.
3. **Vertical memory.** PAYE bands, Lagos Tenancy Law escalation, GTB/OPay/Kuda transfer patterns, Pidgin grammar, "Thank you sir" close — all encoded. A horizontal AI has to be told every time.
4. **The HITL UX is the product.** Owners want draft-and-tap, not autonomous AI. That's a UX product, not a model capability. Anthropic isn't shipping it.
5. **Closed feedback loop per client.** Every approved/edited draft tunes the next one in that client's account. T0.4 outcome learning compounds per-client.

**When Haiku gets 10× better, ReachNG gets 10× better — same code, cheaper inference.** The competitive layer is everything *around* the model.

---

## 7 · The voice-note safe-switch (a representative moat)

A specific example of how we win on trust where generic AI loses.

Lagos WhatsApp customers send voice notes in five languages: English, Pidgin, Yoruba, Igbo, Hausa. OpenAI Whisper handles English and Pidgin well. Yoruba/Igbo/Hausa work for clean sentences but slip on idioms or colloquial speech.

A generic AI tool would confidently mistranslate. ReachNG enforces a strict contract:

- **English / Pidgin:** transcript flows to drafter as text.
- **Yoruba/Igbo/Hausa, high confidence (≥90%):** transcript + Haiku-powered English translation surfaced side-by-side. EYO drafts the reply in English.
- **Anything low confidence:** **EYO does not draft.** HITL banner reads "language uncertain, listen to the audio before sending anything."

The line we won't cross: never let EYO confidently guess at a voice note it didn't fully understand. Premium owners pay extra for that honesty because their brand is on the line.

---

## 8 · Risk register

Top five risks, ranked by impact × probability.

### 1 · Unipile session expiry (mitigation in flight)

WhatsApp linked-device sessions expire after ~14 days of phone inactivity. Silent expiry = silent product stop. Mitigation: scheduled health-check (6h cadence) + portal banner + owner WhatsApp alert + PostHog event. Queued for build before first paid client. ~1 day work.

### 2 · Meta deprecates linked-device API or restricts third-party access

Lower-probability but high-impact. Mitigation: we already have Meta Cloud API integration as the fallback. If Unipile breaks, clients can migrate (with friction).

### 3 · Mongo Atlas free tier outgrown

Around 10-12 clients we move to M10 (₦91k/mo). Modelled in projections. Not a surprise.

### 4 · Currency volatility

All revenue is in NGN, most vendor costs are USD (Anthropic, OpenAI, Unipile, Resend). 20% NGN devaluation = ~10% cost-side hit on per-call costs (we have 30-50% buffer in the ledger). Manageable through pricing reviews.

### 5 · NDPR / data regulation

Lawful basis already encoded into BYO Leads ingest (consent gates, source-of-consent attestation, audit log, hard-delete on request). Lagos lawyer review queued before first paid client signs MSA.

---

## 9 · Use of capital (if any is raised)

Not raising on this doc, but plausible uses:

- **₦5-20M pre-seed friends-and-family:** 6 months of personal runway for Yori to focus full-time, ~₦2M Apify/ads budget, modest hardware/AV for video demos.
- **₦50-150M seed (US$ equivalent at growth):** First sales/SDR hire (Lagos), brand campaign for premium positioning, lawyer + accounting retainer, Mongo Atlas dedicated cluster, customer success ops, expand to Port Harcourt + Ibadan.
- **₦500M+ A round:** national + West African expansion, agency partnership channel, RHEL infrastructure scaling, voice-operator outbound build (Phase 5 in PLAN.md).

**The honest position:** the unit economics are strong enough to bootstrap to ₦150M+ ARR without external capital. Raising would accelerate, not enable.

---

## 10 · Why now

- **WhatsApp Business penetration in Nigeria** crossed 95% in 2024-2025. The channel is universal.
- **Haiku 4.5 / GPT-4o latency** crossed the "feels live" threshold in 2025 — sub-2s drafts are now possible at ~₦4 per call.
- **Lagos premium SMEs** are exiting COVID-era cost discipline and looking for force-multipliers, not headcount.
- **Founder-led AI tools** are out-shipping enterprise SaaS for the SME tier worldwide; Nigeria has no homegrown answer yet.
- **The integration tax** that protects us only gets thicker with every API we add. The moat compounds while competitors evaluate the entry cost.

---

## 11 · Status check

- ✅ Product live at [reachng.ng](https://www.reachng.ng)
- ✅ Self-serve signup + Paystack billing wired (end-to-end tested)
- ✅ HITL queue + WhatsApp pairing flow shipped
- ✅ Voice + Receipt + Morning Brief features shipped (T0.1, T0.2)
- ✅ PostHog product analytics live
- ✅ Pricing locked at Ladder B (₦150 / 300 / 600)
- 🟡 First paid client target: imminent
- 🟡 Unipile session-expiry health loop: queued
- 🟡 Phase 1.6 client book onboarding (vCard / WhatsApp share / paste): queued
- ⏳ Lawyer-reviewed MSA + DPA + NDA: drafted, pending Lagos counsel review

---

## 12 · How to verify

This is not a slide deck. Every number above can be verified against:

- [ECONOMICS.md](./ECONOMICS.md) — per-call cost rates with vendor cross-check
- [PRICING.md](./PRICING.md) — three pricing ladders modelled
- `services/usage_meter.py` — live cost ledger code
- `api/billing.py` + `templates/dashboard.html` — operator visibility today
- Live admin dashboard at `/dashboard` (Basic Auth gated)
- Public landing + signup at [reachng.ng](https://www.reachng.ng)

---

**Contact:** Oluyori Ajagun · hello@reachng.ng · WhatsApp +234 816 458 3657
