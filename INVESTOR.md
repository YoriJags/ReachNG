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
| **Pricing (live)** | 🌱 Solo ₦60k / ⭐ Team ₦120k / 👑 Empire ₦250k per month — founder pricing, first 50 clients. 15% off annual prepay. |
| **Pricing (model basis)** | All projections in §3–§5 are run at **live founder pricing** — blended ARPC **₦103k/mo** (50% Solo / 40% Team / 10% Empire). This is deliberately conservative: the standard rack rate (₦80k / ₦150k / ₦300k → blended ₦130k) lifts every figure ~26%, and the premium-anchor target (₦150k / ₦300k / ₦600k) is a Year-2/3 lever, not assumed here. |
| **Per-client gross margin** | 66 – 94% across all profile × tier combinations (see §3) |
| **Stack** | Python 3.12 + FastAPI + Mongo Atlas + Anthropic Haiku 4.5 + OpenAI Whisper + Unipile + Resend + Paystack + PostHog. Railway deploy. |
| **HQ** | Lagos, Nigeria |
| **Founder** | Oluyori Ajagun — back-office and risk operator (WFunded, formerly). Built the product from inside the pain it solves. |
| **Capital required for first 10 paying clients** | Negligible. Free tiers cover all infra. Cash positive in month 1 at first paid client. |

> ✅ **Re-run at live pricing (2026-05-31).** §3–§5 are now computed at live founder pricing — blended ARPC **₦103k** (matching ACQUISITION.md), corrected Unipile cost (₦8.8k/client, per PRICING.md §1). Net margins land **52–62%** (vs the 78–84% the old ₦150/300/600 model claimed); gross margins **38–92%** per tier×profile. Numbers here are the conservative founder-pricing floor — standard rack (₦80/150/300, blended ₦130k) is ~26% upside on every line. The old ₦150/300/600 figures were PRICING.md's *superseded* Ladder B and have been removed.

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

Corrected cost basis (matches [PRICING.md](./PRICING.md) §1): Unipile is ~₦8,800/client (first-10-accounts flat rate), not the ~₦24k earlier estimate. Per-client fixed = Unipile + Resend share = ₦12,000.

| Profile | Per-call AI | Per-client fixed | Platform share (÷10) | **Total cost** |
|---|---:|---:|---:|---:|
| Light  | ₦2,520 | ₦12,000 | ₦6,100 | **₦20,620** |
| Medium | ₦7,620 | ₦12,000 | ₦6,100 | **₦25,720** |
| Heavy  | ₦18,840 | ₦12,000 | ₦6,100 | **₦36,940** |

Light = small restaurant / single agent. Medium = premium hospitality / mid clinic / established agency. Heavy = high-volume clinic / multi-location restaurant / busy agency.

### Gross margin per tier × profile (at live founder pricing)

| | Light client | Medium client | Heavy client |
|---|---:|---:|---:|
| **🌱 Solo ₦60k**   | 66% | 57% | 38% |
| **⭐ Team ₦120k**  | 83% | 79% | 69% |
| **👑 Empire ₦250k**| 92% | 90% | 85% |

**Worst case is 38% gross margin** (Heavy-usage client on the founder-priced Solo tier — accepted as a deliberate founder-cohort cost; Meta-fallback routing or a Team upgrade recovers it). Best case is 92%. At standard rack (₦80/150/300) the Solo floor rises to 43% Light / 16% Heavy → which is exactly why heavy Solo clients are auto-prompted to upgrade.

### What scales how

- **Per-call costs** (Whisper, Haiku, Vision): scale linearly with usage. Buffered ~30-50% above raw vendor pricing in the ledger to absorb FX swings and retries.
- **Per-client fixed:** Unipile per-account fee (~₦8.8k) is the dominant per-client line. Scales linearly with client count; Meta-Cloud fallback removes it entirely where a client doesn't need their own number paired.
- **Platform fixed:** Railway + Resend + PostHog + Mongo are roughly fixed regardless of client count, but Mongo upgrades from free to M10 (~₦91k/mo) at ~10-12 clients. Modelled below.

---

## 4 · Revenue projections — three scenarios

All projections use **live founder pricing** — blended ARPC **₦103,000/mo**. No extra pilot discount is stacked: founder pricing *is* the discount. Cost lines are independent of price, so they carry over from the previous model unchanged.

### Mix assumption

- Solo clients: ~50% of book (smaller premium SMEs)
- Team clients: ~40% of book (mid-size premium)
- Empire clients: ~10% of book (luxury / multi-location)

Blended ARPC = 0.5×₦60k + 0.4×₦120k + 0.1×₦250k = **₦103,000**. This is the conservative weighting — Lagos/Abuja market data suggests Team tier may end up ~50% as buyers self-select up, which raises the blend.

### Scenario A — Conservative (slow ramp)

| Month | Clients | MRR | Monthly cost | Monthly profit | Margin |
|---:|---:|---:|---:|---:|---:|
| M3   | 3   | ₦309,000   | ₦170,000   | ₦139,000   | 45% (fixed cost ÷ few clients) |
| M6   | 8   | ₦824,000   | ₦330,000   | ₦494,000   | 60% |
| M12  | 20  | ₦2,060,000 | ₦830,000*  | ₦1,230,000 | 60% |
| M24  | 50  | ₦5,150,000 | ₦2,080,000 | ₦3,070,000 | 60% |

\*Includes Mongo M10 transition around client 10.

**Year-1 ARR exit: ₦24.7M.** Year-2 ARR exit: **₦61.8M.**

### Scenario B — Base case

| Month | Clients | MRR | Monthly cost | Monthly profit | Margin |
|---:|---:|---:|---:|---:|---:|
| M3   | 5   | ₦515,000   | ₦210,000   | ₦305,000   | 59% |
| M6   | 15  | ₦1,545,000 | ₦620,000   | ₦925,000   | 60% |
| M12  | 40  | ₦4,120,000 | ₦1,720,000 | ₦2,400,000 | 58% |
| M24  | 100 | ₦10,300,000| ₦4,170,000 | ₦6,130,000 | 60% |

**Year-1 ARR exit: ₦49.4M.** Year-2 ARR exit: **₦123.6M.**

### Scenario C — Aggressive (network effects + referral kick in)

| Month | Clients | MRR | Monthly cost | Monthly profit | Margin |
|---:|---:|---:|---:|---:|---:|
| M3   | 8   | ₦824,000   | ₦330,000   | ₦494,000   | 60% |
| M6   | 25  | ₦2,575,000 | ₦1,040,000 | ₦1,535,000 | 60% |
| M12  | 75  | ₦7,725,000 | ₦3,200,000 | ₦4,525,000 | 59% |
| M24  | 200 | ₦20,600,000| ₦8,340,000 | ₦12,260,000| 60% |

**Year-1 ARR exit: ₦92.7M.** Year-2 ARR exit: **₦247.2M.**

### Margin trajectory (all scenarios)

Net margin **stabilises around 60%** at founder pricing (vs ~84% the old inflated model claimed):
- Sub-10 clients: 45-59% (platform fixed cost diluted across few clients)
- 10-50 clients: ~60% (Mongo M10 cost absorbed)
- 50+ clients: ~60% steady (per-client fixed share keeps dropping, offset by team hires)

Two clean levers lift this without new product: (1) standard rack pricing ₦80/150/300 once past the founder cohort (+~26% to revenue, straight to margin), and (2) Meta-Cloud fallback on price-sensitive Solo clients (removes the ₦8.8k Unipile line). Everything else compounds in our favour.

---

## 4.5 · Road to 1,000 clients (the headline goal)

1,000 paying clients ≈ 10-20% of the addressable premium SME beachhead in Lagos and Abuja. The path, broken into quarterly milestones, all at live founder pricing (blended ARPC ₦103k — conservative; standard rack lifts every line ~26%):

### Year 1 — Foundation (0 → 100)

| Quarter | Target clients (cumulative) | Net adds | MRR at quarter-end | Notes |
|---|---:|---:|---:|---|
| Q1 (M1-3)  | 5    | +5   | ₦515,000   | Founder batch, hand-onboarded, founder pricing in effect |
| Q2 (M4-6)  | 25   | +20  | ₦2,575,000 | Pricing live, founder-led sales, referrals start |
| Q3 (M7-9)  | 60   | +35  | ₦6,180,000 | Vertical case studies live, Twitter authority cadence |
| Q4 (M10-12)| 100  | +40  | ₦10,300,000| First sales/CS hire mid-Q4 |

**Year-1 exit:** 100 clients · ₦10.3M MRR · **₦123.6M ARR**

### Year 2 — Velocity (100 → 600)

| Quarter | Target clients | Net adds | MRR | Notes |
|---|---:|---:|---:|---|
| Q5 (M13-15)| 175  | +75  | ₦18.0M | First SDR hire, paid acquisition unlocked |
| Q6 (M16-18)| 275  | +100 | ₦28.3M | Agency partnership channel live |
| Q7 (M19-21)| 425  | +150 | ₦43.8M | Conference + brand campaign, Abuja office |
| Q8 (M22-24)| 600  | +175 | ₦61.8M | 2nd engineer hire |

**Year-2 exit:** 600 clients · ₦61.8M MRR · **₦741.6M ARR**

> Year-2/3 figures still assume founder pricing for *every* client — deeply conservative, since the founder rate is capped at the first 50. At standard rack (blended ₦130k) Year-2 exit is ₦78M MRR / ₦936M ARR; at the premium-anchor target (blended ₦255k) it reverts to the old ₦1.6B-class numbers. We model the floor on purpose.

### Year 3 — Compounding (600 → 1,000)

| Quarter | Target clients | Net adds | MRR | Notes |
|---|---:|---:|---:|---|
| Q9 (M25-27) | 750   | +150 | ₦77.3M | Voice Operator (outbound) launches |
| Q10 (M28-30)| 850   | +100 | ₦87.6M | National expansion (Port Harcourt, Ibadan) |
| Q11 (M31-33)| 925   | +75  | ₦95.3M | Vertical SDK / API offering |
| Q12 (M34-36)| **1,000** | +75 | **₦103.0M** | West Africa pilot (Accra, Nairobi) |

**Year-3 exit at 1,000 clients (founder pricing floor):** ₦103M MRR · **₦1.236B ARR · ~52% blended net margin · ~₦53.7M monthly net profit.** At standard rack pricing this is ₦130M MRR / ₦1.56B ARR.

### Cost at each milestone

Includes Claude Pro/Max operator-tooling cost in the founder-toolset line (Pro at start, Max 5× at ~15 clients, Max 20× at ~50 clients).

| Clients | MRR | Direct cost | Team cost | Mongo tier | Operator tools | Total cost | Net margin |
|---:|---:|---:|---:|---|---:|---:|---:|
| 25    | ₦2.6M   | ₦820k    | Founder only            | Atlas free | Claude Max 5× ₦160k | ₦980k    | 62% |
| 100   | ₦10.3M  | ₦3.5M    | +1 ops/CS               | M10 ₦91k   | Max 20× ₦320k       | ₦4.4M    | 57% |
| 250   | ₦25.8M  | ₦8.5M    | +SDR + accountant       | M20 ₦232k  | Max 20× ₦320k       | ₦11.9M   | 54% |
| 500   | ₦51.5M  | ₦16.7M   | +2 engineers + CS       | M20        | 2× Max 20× ₦640k    | ₦24.7M   | 52% |
| 1,000 | ₦103M   | ₦32M     | ~15-person org          | M30 ₦617k  | 4× Max 20× ₦1.28M   | ₦49.3M   | 52% |

**Read:** even at 1,000 clients on the *founder-pricing floor*, with a 15-person Lagos team and full Claude Max for every operator, blended net margin holds at **~52%**. That is the conservative case — standard rack pricing pushes it back toward 60%+. The model is built for compounding profitability, not just compounding revenue.

### Hire plan along the curve

| Milestone | Hires added |
|---|---|
| 25 clients   | First ops / customer success generalist |
| 75 clients   | First SDR (replaces founder-led outreach) |
| 100 clients  | Accountant / bookkeeper (PT) |
| 250 clients  | Lead engineer + CS lead |
| 500 clients  | 2 more engineers + 2 more SDR + Head of Sales |
| 1,000 clients| Country leads (Lagos / Abuja / PH), VP Eng, VP Customer Ops |

Final-state org: ~15 people. Revenue per employee at 1,000 clients = ₦82M/year (founder-pricing floor; ₦104M at standard rack). Industry benchmark for high-margin SaaS is ₦40-80M/employee. We'd be at or above the top of the range.

### What the 1,000-client outcome looks like

- **₦1.236B annualised revenue** (founder-pricing floor; ₦1.56B at standard rack)
- **~₦642M annualised net profit** (~52% blended)
- **15-person team across Lagos / Abuja / Port Harcourt**
- **Default agentic-employee platform for the Nigerian premium SME tier**
- **Optionality:** vertical SDKs (real estate, hospitality), API offering, regional expansion, acquisition target for global CRM consolidators (HubSpot, Salesforce) at 5-8× ARR multiple = ₦6.2-9.9B valuation

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
- Blended ARPC: ₦103,000/mo (Solo/Team/Empire at live founder pricing)
- Gross margin: ~75% blended (Light-Medium-skewed SME base)
- **LTV = 24 × 103,000 × 0.75 = ₦1,854,000 per client** (≈ ₦2.34M at standard rack)

### LTV / CAC

At ₦5,000 CAC and ₦1.85M LTV = **371× LTV/CAC ratio**. The benchmark anyone respects is >3×. This number won't hold once we run paid acquisition or hire SDRs, but the bootstrapped phase is exceptional.

### Paid CAC ceiling

If LTV is ₦1.85M and we want to keep LTV/CAC > 5×, we can spend up to **₦370,000 acquiring a client** before economics break. Plenty of headroom for paid social, partnership commissions, conference sponsorships when the time comes.

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

## 6.5 · Why Meta's AI launch is our tailwind, not our threat

On 3 Jun 2026 Meta put a free AI agent on every business WhatsApp. The reflex question — *"doesn't Meta just crush you?"* — has it backwards. **Meta didn't enter our market. They paid to open it.**

1. **They bought our market education.** Convincing a 50-year-old Lekki landlord that "an AI can run my WhatsApp" used to take a demo and a leap of faith. Meta is spending billions making that idea normal. We stop being the strange pitch and become the obvious *upgrade* — to a thing the buyer now already wants.
2. **Their scale is the ceiling we exploit.** A horizontal agent serving 200M+ merchants can't reconcile a ₦90k transfer screenshot to a specific Saturday booking, won't remember the customer refuses the corner table, won't hold the one discount the owner banned. Generic by mandate. **EYO is one business deep.** Meta is a mile wide and an inch deep — structurally, it cannot follow us into the money moment.
3. **We're demand on their rails, not a rival.** EYO runs on Meta's official Cloud API: ban-safe, it drives *more* WhatsApp volume for Meta, and — because EYO is reply-centric — near-zero messaging COGS (₦650–₦5.2k/client; see [ECONOMICS.md §4.1](./ECONOMICS.md)). Platforms protect what feeds them. The platform-risk question inverts into **platform alignment.**

**The Meta API bottleneck — and our head start.** Meta's rails are powerful but high-friction to actually switch on. That gap between *"the rails exist"* and *"a Lagos SME getting value from them"* is exactly where we sit:

| Meta API bottleneck | Where ReachNG is ahead + aligned |
|---|---|
| **WABA + business verification** — every business must verify on Business Manager, register a number, pass review (days-to-weeks, document-heavy). Most Lagos SMEs stall here. | **Done-for-you onboarding** onto the official rails, *plus* instant Unipile QR start while verification processes. We remove the activation energy Meta requires. |
| **Template approval + the 24h window** — any message outside a customer's 24h reply window needs a Meta-approved template (review, rejections, delay). A generic agent hits this wall constantly. | EYO is **reply-centric** (lives inside the free 24h service window) and routes cold outreach to email. We sidestep the wall *by design* — and keep messaging COGS near zero. |
| **The agent is generic + shallow today** — thin brand-voice control; deep custom-tools / knowledge / handoff hooks not yet published. Businesses wanting real depth have nowhere to go. | We already **are** the depth layer — money reconciliation, per-customer memory, owner control, Naija voice. We ride the official rails today and plug into the deep-integration hooks the day Meta ships them. |

> **Meta makes WhatsApp the AI sales desk. EYO is what runs on it the moment the sale involves real money.**

**The timing edge:** almost no Nigerian SME has priced in the consequence yet — that a free generic agent *raises customer expectations overnight while quietly leaking money* in the exact Naija spots (transfers, voice notes, haggling, memory) it can't handle. Whoever explains that first owns the framing. We're first, and we're already built to be the answer.

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

### 2 · Meta deprecates the linked-device API or restricts third-party access

Lower-probability but high-impact — and scoped to the *unofficial* linked-device path (Unipile). Mitigation: per-client Meta **Cloud API** routing is already built (`send_whatsapp_for_client`), so clients migrate to the official rails with minimal friction. Note this risk is **separate from** Meta's Jun 2026 Business Agent launch, which is a tailwind, not a threat (see §6.5) — that launch runs on the same official Cloud API we already integrate.

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

- **Meta turned WhatsApp into an AI sales desk (Jun 2026).** It normalised "AI on WhatsApp" for every Nigerian SME overnight and handed us a pre-educated market that now *expects* exactly what we sell — while leaving the money moment (transfers, voice notes, haggling, memory) wide open. We're already built for it and on the same official rails. See §6.5.
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
- ✅ Pricing locked + live: 🌱 Solo ₦60k / ⭐ Team ₦120k / 👑 Empire ₦250k (founder, first 50)
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
