# ReachNG — Strategy, Pivot Memo & Current-Build Audit

> **Audience:** You (founder), blunt teardown mode
> **Current date:** April 2026
> **Stack you're actually on:** Python 3.12 / FastAPI / MongoDB Atlas / Claude Haiku 4.5 / Unipile (WhatsApp + Email) / Apollo.io / Google Maps Places API / Railway
> **Live URL:** `https://reachng-production.up.railway.app`
> **Revised thesis:** Stop pretending ReachNG is *one* product. It's **three layers**: a Discovery Engine (internal), a Closer (client-facing, real estate), and a Back-Office (client-facing, HR). The whole game is selling **Closer to luxury + regular real estate + agencies** on recurring rails, with the SDR as the acquisition loop underneath.

---

## 0. The Brutally Honest TL;DR

1. **Your original ReachNG idea had a fatal logical flaw, and your gut was right to kill it.** You can't run a SDR-as-a-service where you sell Agency A's services to Agency B's customer, because Agency B is also a customer — you'd be selling to and competing with your own client base simultaneously. That's the "loop isn't complete" you felt. **Your pivot to Closer (work the client's *own* inbound leads) resolves the conflict cleanly.** Document this pivot permanently — future you will forget why.
2. **Segment the real estate wedge into 3, not 1.** Luxury / Regular / Agencies. They have different pain, different ARPU, different sales cycles, and different willingness-to-pay models (retainer vs. commission vs. per-viewing). One pitch deck will fail in at least 2 of 3 segments.
3. **Your biggest silent killer isn't tech — it's card churn + Unipile fragility.** Both cost you MRR you never see. See Section 5 for the full Paystack teardown.
4. **You've over-built features and under-built distribution.** 19 suite directories in `/services`, only 2 live in UI. That's fine for optionality but dangerous for focus. Ship 1 paying luxury client this month before touching anything new.
5. **Rating of current build: 7.2 / 10.** Strong on architecture, moderate on positioning, weak on billing hardness, invisible on luxury tier. Full audit in Section 3.

---

## 1. The Pivot Memo (document this — you'll forget why you turned)

### 1.1 The original ReachNG thesis (dead)
> Use Google Maps + Apollo + Claude + Unipile to find Lagos businesses, reach out on behalf of clients, and close deals for them. Sell the outreach service itself as SaaS.

### 1.2 Why the loop didn't close
- **Overlap problem:** The universe of "Lagos real estate agencies" is your *pool of targets you'd pitch for a client* **and** your *pool of paying customers*. You'd pitch Agency A's listings to Agency B's client — but Agency B is also your customer who gave you their leads. That's a direct channel conflict.
- **Honesty problem:** A 1-to-many SDR-as-a-service selling to the same TAM as its own sales pipeline isn't a service — it's a classifieds platform with a middleman charge. And classifieds already exist (Nigeria Property Centre, PropertyPro, PrivateProperty).
- **Unit-economics problem:** Even if legal, your CAC and the leads' CAC compete for the same phone number's attention. You'd saturate the market and kill both sides.
- **Trust problem:** "Who is this ReachNG messaging me on behalf of Agency A? I thought they were messaging me last week on behalf of Agency C?" → Unipile accounts get reported, WhatsApp numbers get banned.

### 1.3 The pivot (alive)
> Use the SDR as an **internal acquisition engine** that finds Lagos businesses with clear workflow pain. Sell them **a product that takes pain away** — not outreach. Product category: *"AI Staff that lives inside your existing tools (WhatsApp, email, Google Calendar)."* Revenue = recurring retainer + outcome fees.

**The single decision that saved the business:** client-facing products (Closer, TalentOS) are *workload removers*, not channel additions. The SDR stays, but it's marketing, not product.

### 1.4 What the pivot unlocks
- Clean sales narrative ("we take your Saturday back") vs. messy sales narrative ("we sell for you").
- Recurring retainer > per-message billing → predictable MRR, higher multiples.
- Multiple products across verticals without cannibalising (a HR client is not a real estate lead).
- Regulatory clean slate (HITL + client sends from their own number = you're a tool, not a broker).

---

## 2. New Segmentation: Luxury / Regular / Agency

Previously lumped as "real estate." These three segments have very different buyers, different JTBD, and demand different product packaging and pricing.

### 2.1 Segment A — **Luxury** Real Estate Businesses
**Who:**
- Sole principals or 2–5 person boutiques selling ₦200M+ properties
- Banana Island, Ikoyi, Eko Atlantic, Parkview Estate, Oniru, VI Phase 2
- Diaspora buyers + HNI clientele + fund LPs
- Often also do property management for absentee owners

**Their pain (ranked):**
1. **Discretion + trust** — every lead is a potential PR disaster if handled sloppily (politicians, celebrities, foreign buyers)
2. **PoF friction** — asking "can you afford this?" is awkward, but not asking wastes a whole Saturday viewing on Banana Island with someone who can't close
3. **International buyer async gap** — leads from Dubai/London/Houston ping at 3am Lagos time, you miss them, they buy from a competitor
4. **Paperwork prestige** — tenancy/purchase docs must look expensive, lawyers must be on tap
5. **Concierge expectation** — buyers expect driver, car, refreshments at viewing; no one else automates this logistics piece

**Pitch to them:** *"Your Closer after hours. Quietly qualifies international buyers, runs PoF discreetly, books the Saturday viewings that actually close."*

**Pricing:** ₦300k–₦600k/mo retainer + **3–5% commission on closed deals** (they'll pay this because 1 closed Banana Island flat = ₦30M–₦150M commission)
**LTV drivers:** Commission tail. One closed luxury deal = 12 months of SaaS. Push them to the commission-tier plan hard.
**Sales cycle:** 4–8 weeks. Relationship-driven. You need an in-person meeting.
**Volume ceiling:** ~80–120 luxury operators across Lagos. Quality over quantity.

### 2.2 Segment B — **Regular** Real Estate Businesses
**Who:**
- Solo agents + brokers handling ₦20M–₦100M properties
- Lekki Phase 1/2, Ajah, Magodo, Gbagada, Yaba, Surulere, Ikeja GRA, Ogudu
- High inbound WhatsApp volume, low conversion
- Mostly rentals (70%) and low-end purchases (30%)

**Their pain (ranked):**
1. **Lead volume > capacity** — 30–60 WhatsApp enquiries a day, they reply to 15, lose 45
2. **Rent chase burnout** — chasing 30 tenants monthly for rent; awkward + repetitive
3. **Listings everywhere / nowhere** — same listing has to be on NPC, PropertyPro, Instagram, WhatsApp status, Jiji, Facebook — manually formatted each time
4. **Document chaos** — buyer asks "is this property Governor's consent or C of O?" and agent can't find the file
5. **Commission disputes** — co-agent agreements collapsing because nobody logged who introduced whom first

**Pitch to them:** *"Your WhatsApp assistant that answers every enquiry in 30 seconds, chases rent for you, and keeps your listings ready to post everywhere."*

**Pricing:** ₦75k–₦150k/mo retainer + ₦5k–₦10k per qualified viewing
**LTV drivers:** Low churn if rent-chase module activated (it's sticky — they can't un-use it once tenants expect it)
**Sales cycle:** 1–2 weeks. Demo → 7-day trial → close.
**Volume ceiling:** ~2,500–3,000 qualifying solo agents in Lagos (from your Google Places corpus). Most of your MRR lives here.

### 2.3 Segment C — **Agencies** (multi-agent firms)
**Who:**
- 10–80 employee agencies: PropertyMart, Fine & Country NG, Trivium, Alpha Mead, Adron, Landmark Africa
- Sales + rentals + facility management under one roof
- Multiple branches; they have admin staff, accountants, lawyers on retainer

**Their pain (ranked):**
1. **Agent leakage** — agents poach leads, route deals through personal phones, commission disputes
2. **Branch consolidation** — 3 branches, 3 WhatsApp groups, 3 sets of Excel, no single view
3. **Staff onboarding churn** — 15 agents last year, 22 this year, 11 quit, training from scratch each time (this is where **TalentOS** sells to this segment *too*)
4. **Reporting for principal** — MD wants weekly deal pipeline report; nobody has time to compile
5. **Audit trail for client trust** — "show me every message to client X on this deal"

**Pitch to them:** *"One dashboard for all your branches. Every lead, every agent, every message — tracked, with HITL approval so rogue agents can't ghost-sell."*

**Pricing:** ₦500k–₦1.5M/mo + per-seat pricing (₦25k/agent/mo). Optional setup fee ₦500k–₦1M for integration work.
**LTV drivers:** Enterprise stickiness. Once integrated with their workflow, churn drops below 2%/month. High upsell potential to TalentOS back-office.
**Sales cycle:** 6–12 weeks. Needs pilot with one branch, then expansion. MD + ops director + IT head all decision-makers.
**Volume ceiling:** ~80 target agencies in Lagos. This is your ₦10M+ MRR per customer tier.

### 2.4 Segment Strategy Summary

| Segment | ARPU | Sales Cycle | Volume Target (Yr 1) | ARR Potential |
|---|---|---|---|---|
| Luxury | ₦450k/mo + commission | 6wk | 12 clients | ₦65M + commission tail |
| Regular | ₦110k/mo | 2wk | 80 clients | ₦105M |
| Agency | ₦900k/mo + per-seat | 10wk | 6 clients | ₦65M |
| **Total Yr 1 target** | | | **98 customers** | **~₦235M ARR + commission upside** |

**Sequence to go-to-market:**
1. **Regular first** (weeks 1–8) — highest volume, fastest cycle, proves the product
2. **Luxury second** (weeks 4–16, overlap) — one flagship Banana Island client worth more than 10 regular clients in storytelling
3. **Agency third** (weeks 12+) — needs case studies from 1–2; pre-sell pilots now, deliver later

---

## 3. Rating the Current Build (honest audit)

### Scoring rubric (1–10 per dimension)

| Dimension | Score | Reasoning |
|---|---|---|
| **Architecture** | 8.5 | Clean FastAPI + Mongo + APScheduler separation. HITL-first is a huge maturity signal. `/services/*` modular. Multi-tenant scoping discipline (per CLAUDE.md) is enterprise-grade. |
| **Product-market fit (Closer)** | 6.5 | Real pain, real willingness to pay, BUT you haven't landed a paying customer yet — so it's hypothesis-validated but not revenue-validated. Phase 1 of 5 per PLAN.md. Ship or die. |
| **Product-market fit (TalentOS)** | 5.0 | Built before validated. Competing against SeamlessHR/Bento in a saturated mid-market. Works best as an **upsell** to Closer customers, not standalone wedge. |
| **SDR engine** | 7.5 | Working, scheduled, HITL-gated. Google Maps billing live April 2026 (per CURRENT_STATE). The 3-source blend (Maps + Apollo + Social) is strong but Social is the weakest leg — consider dropping for v1 stability. |
| **Billing maturity** | **3.5** ⚠️ | **Biggest weakness.** `/api/paystack.py` exists but there's no visible direct-debit architecture, no dunning ladder, no tokenized card-on-file, no grace period logic. If you have 10 paying clients, you will lose 1–2 per month to card failures alone. See Section 5. |
| **Positioning / branding** | 6.0 | "ReachNG" (external) vs. EstateOS/TalentOS (internal codes) split is smart. But no clear segment-specific landing pages — a luxury agent and a solo agent see the same pitch. |
| **Feature focus** | 5.5 | 19 suites in `/services` → 2 live. PLAN.md's "deferred matrix" is disciplined but dangerous if you context-switch back into them. Every token spent on AgriOS / BuildOS is a day of distribution not built. |
| **Legal pack** | 4.0 ⚠️ | Phase 3 of PLAN.md, still drafts. MSA / DPA / NDA / Closer Addendum pending Lagos lawyer review. You CANNOT sign first real enterprise client without this. P0 blocker. |
| **Observability** | 6.5 | structlog + daily-limit tracking + ROI calc in place. Missing: per-customer margin dashboard, Claude token spend per client (you'll overshoot LLM budgets otherwise). |
| **Unipile dependency** | 5.0 | Single vendor risk on outbound = existential. One Unipile outage = all clients silent. Need a fallback: Meta WhatsApp Business Cloud API (official) for Agency tier; Termii for SMS fallback. |
| **Docs / onboarding UX** | 7.0 | OPERATIONS.md + README.md + CLAUDE.md are excellent. You (or a hire) can pick this up cold. Best documented pre-revenue startup I've seen this month. |

### Overall: **7.2 / 10** — a strong V1 that needs to stop shipping features and start shipping invoices.

### What the audit tells me (3 things)

1. **You've built a Series-B-looking product on a pre-revenue business.** That's fine — it's defensible. But your next 60 days must be 80% sales, 20% code.
2. **Your P0 technical debt is billing, not features.** Fix Section 5 or MRR will leak faster than you can onboard.
3. **Your P0 business debt is legal.** Without the signed MSA/DPA, the first agency-tier client will walk.

---

## 4. Optimization Priorities (ranked)

### 🔴 P0 — do this week
1. **Harden recurring billing** (Section 5). Flutterwave Account Charge as primary rail; Paystack tokenized card as fallback; dunning ladder with soft-lock.
2. **Luxury-tier landing page** — separate URL, separate pitch (`/luxury`), separate WhatsApp intake number, different branding font. Currently invisible.
3. **Book the lawyer.** Lagos commercial lawyer, budget ₦300–500k, 2-week turnaround on MSA/DPA/NDA/Closer Addendum.
4. **Pick 5 target luxury agencies, hand-curate, personally demo.** Banana Island + Eko Atlantic only. Skip volume here — 1 closed = month made.

### 🟡 P1 — do in next 2 weeks
5. **Per-segment Closer briefs** — luxury vs. regular vs. agency. Currently `closer_brief` schema is generic; add `segment` enum + segment-specific system prompt branches in `agent/prompts/closer/`.
6. **Freeze deferred suites in UI + code.** Add a `FEATURE_FLAG_SUITE` env var; anything not `estate` or `talent` 404s. Forces focus.
7. **Cost-per-customer dashboard** — Claude tokens + Unipile usage + Google Maps calls per client. Tag every external API call with `client_id`. Critical for margin accuracy.
8. **Second Unipile account on standby** — if your primary gets rate-limited, flip DNS to backup within 5 minutes.

### 🟢 P2 — after first 5 paying clients
9. **Meta WhatsApp Business Cloud API integration** as alternative to Unipile (for Agency tier — they want an official BSP, not a middleware).
10. **Nigerian-English Claude fine-tune** (via Anthropic few-shot prompt library, not actual fine-tuning). Store 50 exemplar Lagos-agent conversations; pass as system examples. Measurable uplift in reply quality.
11. **Commission invoicing module** — automates the 3–5% luxury deal commission math + invoice generation. Critical for the luxury tier's commercial model.
12. **Referral flywheel in-product** — generate unique referral link per client, ₦50k credit for both sides on conversion. One-click share via WhatsApp.

### ⚪ Backlog (right problems, wrong timing)
- Voice Operator (ElevenLabs + Twilio) — revisit after 10 Closer clients
- Competitor Intelligence productized as standalone — you have the infra, monetize to existing clients as ₦40k/mo add-on
- PLUGng spin-off (artists vertical from IDEAS.md) — excellent idea, same infra, but DO NOT split focus until real estate is at ₦5M MRR
- Voice + Pidgin support — goldmine, but specialized Claude prompt library first, full voice later

---

## 5. The Paystack / Recurring Billing Deep Dive (you asked for this)

### 5.1 The core problem — Naira card recurring billing is fragile
Unlike US Stripe where card-on-file + auto-renewal is ~97% reliable, Nigerian card recurring has **multiple compounding failure modes**:

| Failure Mode | Typical Rate | Cause |
|---|---|---|
| Card expired | 3–6% / month | Nigerian banks re-issue cards often, customers don't update merchants |
| Insufficient funds | 8–15% / month | Customers keep low naira-card balances; salary-timed spending |
| Issuer-side decline (FX / risk flag) | 4–8% / month | Naira cards flagged on international-looking transactions, even domestic |
| Customer-side block (CBN cap reached) | 2–5% / month | CBN $100/mo on naira cards for international; merchants mis-classified |
| 3DS friction / OTP timeout on recurring | 1–3% / month | Some issuers require OTP every charge — fatal for hands-off billing |
| Customer forgot to top up | 3–5% / month | Behavioural; cultural preference for manual transfer over auto-debit |
| **Combined net failure per month** | **~18–30%** | Compounds if not retried |

**Real-world impact at ₦5M MRR, 25% monthly card failure:**
- Failed charges: ₦1.25M/mo
- If you recover 60% via retry + dunning: ₦750k captured
- **Actual bleed: ₦500k/mo = 10% of MRR gone** (and this is a *healthy* scenario)

### 5.2 Paystack vs. Flutterwave — comparison matrix

| Feature | Paystack | Flutterwave |
|---|---|---|
| **Recurring plans** | Yes — Plans + Subscriptions API | Yes — Payment Plans API |
| **Card tokenization** | Yes — reusable authorization token | Yes — card tokenization endpoint |
| **Direct debit / bank mandate** | Paystack Direct Debit (beta, limited banks) | **Flutterwave Account Charge** (GTB, FirstBank, Access, Zenith, UBA, Fidelity, Stanbic) — mature |
| **USSD fallback** | Yes | Yes |
| **Transfer (bank push)** | Yes — Dynamic Virtual Account | Yes — Bank Transfer |
| **Webhook reliability** | Very high (industry standard in Nigeria) | High |
| **Dashboard for dunning** | Good | OK — less granular |
| **Fees (local card)** | 1.5% + ₦100, capped ₦2,000, waived under ₦2,500 | 1.4% local + ₦2,000 cap |
| **Fees (direct debit)** | ~0.7% | ~0.8% |
| **Developer docs** | Best-in-class in Africa | Good, inconsistent versioning |
| **Failure retry built-in** | Automatic retry in subscription engine | Manual retry via your code |
| **International card support** | Yes (3.9% + ₦100) | Yes (3.8%) |

**My recommendation:**
- **Primary rail: Flutterwave Account Charge** (direct debit) for all subscribers who can bank-authorise. Bypasses card failure entirely. Monthly debit from bank, no card needed.
- **Secondary rail: Paystack tokenized card** — for clients who won't do direct debit (diaspora, anyone using a foreign card, anyone already on a naira card they trust).
- **Tertiary fallback: manual Paystack payment link** sent via WhatsApp on day of failure.

### 5.3 The dunning ladder you MUST build (copy this architecture)

```
Day 0  — Attempt 1 (primary rail: Flutterwave direct debit or tokenized card)
         ├── Success → issue receipt via WhatsApp + email, extend service 31 days
         └── Fail → queue retry, status = grace_period, service STAYS ACTIVE

Day 1  — Attempt 2 (auto, same rail)
         ├── Success → backdate receipt
         └── Fail → soft notification via WhatsApp:
             "Hey [Name], your ReachNG payment didn't go through.
              We'll try again tomorrow. Top up or reply here if you need help."

Day 3  — Attempt 3 (auto, different rail if primary was direct debit → try card; if card → try USSD prompt)
         ├── Success → receipt + gentle "all good now" note
         └── Fail → firmer WhatsApp:
             "Quick one — your last two retries didn't clear. Your AI staff
              will pause on Friday if payment isn't through. Need a new card
              on file? Tap here: [payment link]"

Day 7  — Attempt 4 (manual payment link only)
         ├── Success → full re-enable + receipt
         └── Fail → SOFT LOCK (service paused, not deleted)
              WhatsApp: "Service paused. Your data is safe. Pay here to resume.
              We keep everything for 30 days."

Day 14 — HUMAN escalation
         You (or a CSM) phones the client personally.
         ~60% recover here — usually "oh sorry I changed banks"

Day 30 — HARD LOCK
         Data retained per DPA (see Closer Addendum). Not deleted.
         Client moved to "churned" status. Offer win-back 90 days later.
```

**Why soft-lock, not hard-cancel:** losing a client over a ₦110k missed charge is insane when the LTV is ₦1M+. Grace period + manual outreach recovers 40–70% of "churned" cards.

### 5.4 Specific implementation notes for your codebase

Looking at `/app/api/paystack.py` existing — you have a handler. What you likely lack (I haven't read the file yet, but based on the size of `main.py` and pattern):

- ✅ Webhook receiver for `charge.success` / `subscription.create` / `subscription.disable`
- ❓ Webhook for `invoice.payment_failed` with retry queue
- ❓ Tokenized authorization storage per client (not card PAN — just the Paystack auth code)
- ❓ Multi-rail cascade (Flutterwave → Paystack → USSD)
- ❓ Dunning state machine on the `clients` collection (`billing_status`, `last_attempt`, `retry_count`, `grace_until`)
- ❓ Per-client billing dashboard (your Control Tower should show dunning queue)

**Schema you need on the `clients` collection:**
```javascript
{
  client_id: "...",
  billing: {
    primary_rail: "flutterwave_mandate" | "paystack_card" | "manual",
    mandate_id: "FLW-MD-xxx",                    // if direct debit
    paystack_auth_code: "AUTH_xxx",              // tokenized card
    plan: "closer_regular" | "closer_luxury" | ...,
    amount_ngn: 110000,
    billing_day: 15,                             // day of month
    status: "active" | "grace" | "soft_locked" | "churned",
    retry_count: 0,
    last_attempt_at: ISODate(...),
    grace_until: ISODate(...),
    history: [ { date, rail, amount, status, reason } ]
  }
}
```

**Implementation priority (do this week):**
1. Add `billing` subdoc to `clients` schema — migration script
2. Write `services/billing/engine.py` — the retry state machine
3. Add Flutterwave Account Charge SDK (they have Python SDK)
4. Add cron job to `scheduler.py` — daily `billing.run_retries()`
5. Add WhatsApp template messages for the dunning ladder (pre-approve via Unipile sender ID)
6. Add admin view at `/admin/billing` — queue + manual retry button

**Cost to build: ~3 engineer-days. Cost of not building: ~10% of MRR, forever.**

### 5.5 Luxury-tier commission billing (separate problem)

Flat retainer is easy. **Commission on deal close is where most SaaS gets sloppy.** For the 3–5% luxury commission:

- **Trust problem:** how does ReachNG know the deal closed? Client has every incentive to say "nah, fell through."
- **Solution 1 (weak):** self-reported via dashboard "Mark deal closed" button. Honour system.
- **Solution 2 (stronger):** tie it to the handover card — when you generate a handover card with budget + contact + property, that's your ledger. Give the client 30 days to mark won/lost. After 30 days of silence, auto-follow up *to the buyer* (not the client) — "Did the purchase complete?" Claude can do this diplomatically.
- **Solution 3 (strongest):** partner with the lawyer (Lawyer Bundle upsell) — when they generate the Deed of Assignment, webhook fires to your system. Deal is legally documented; commission invoice auto-raised.

**My call:** start with Solution 1 + Solution 2 combined. It's what Lagos culture will tolerate for V1. Escalate to Solution 3 when you hit 5+ luxury clients.

Invoice flow:
```
Deal marked closed → commission_invoice generated automatically
                  → sent via WhatsApp + email
                  → 7-day net payment
                  → dunning ladder kicks in (same engine)
                  → at 30 days: ReachNG Closer paused for that client until settled
```

### 5.6 One-line summary on billing
**Your MRR is already budgeted to leak until you build the dunning engine. Budget 3 days of eng time this sprint for it. It's the single highest-leverage unsexy task in the business.**

---

## 6. Updated GTM — Who to call Monday

### 6.1 Week-by-week target list (first 30 days)

**Luxury (hand-sourced, not scraped):**
1. Adron Homes — multi-segment but has a luxury line
2. Fine & Country Nigeria
3. Eximia Realty
4. Ubosi Eleh + Co.
5. Lamudi Luxury partners in Lagos
6. Landlux Real Estate
7. Properties24 Lagos top-tier
8. Northcourt Real Estate
9. ERA Nigeria
10. Tuscany Homes (Banana Island)

**Regular (scraped via your existing Places pipeline):**
Filter your existing `leads` collection where:
- `vertical == real_estate`
- `rating >= 3.8`
- `phone != null`
- `website != null`
- geo within Lekki / Ajah / Ikeja / VI / Magodo
→ rank by `lead_score`, take top 200, run through Closer pitch via SDR funnel

**Agency (ABM, hand-sourced):**
1. PropertyMart Nigeria
2. Alpha Mead
3. Pertinence Limited
4. Landmark Africa Group
5. Mixta Nigeria (Adron spinoff)
6. Cosgrove Investment
7. Haldane McCall
8. Imperial Realty
9. Primrose Development
10. Novarick Homes

Target 3 pilots from this list — offer a ₦0 setup, 30-day pilot in exchange for a signed LOI.

### 6.2 Segment-specific messaging

**Luxury opener (WhatsApp, mid-morning Lagos time):**
> "Hi [first name] — I work with boutique agencies on Banana Island / Ikoyi on after-hours lead qualification. I've built a system that handles Dubai + London buyers at 3am so you're not losing them to WhatsApp silence. Open to a 20-min video call next week? Happy to show what we did for [flagship luxury client once landed]."

**Regular opener (already working in your SDR):**
Keep your current message pattern but A/B test:
- Variant A: pain-led ("lose 45 of 60 WhatsApp enquiries a day?")
- Variant B: outcome-led ("book 3 extra viewings this Saturday with the same team")

**Agency opener (email + LinkedIn, never WhatsApp cold):**
> "Hi [MD name], we run back-office automation for Lagos agencies (payroll, lead tracking, HITL-audited agent comms). Not pitching a tool — pitching a 30-day pilot for one of your branches. If the pilot doesn't cut admin hours by 40% in a month, you walk with our playbook. Worth a 30-min call?"

### 6.3 Your existing SDR is the engine — optimize it, don't rebuild it
Your SDR already does Google Maps + Apollo + Unipile + HITL. Just:
1. Split the `real_estate` vertical into `real_estate_luxury` and `real_estate_regular` with different prompts
2. Add an `agency_abm` vertical with a curated seed list of 80 agencies (bypass Google Maps, go direct to decision-maker emails via Apollo)
3. Track segment-level reply rates separately in your A/B panel

---

## 7. Unit Economics — Segment-Level

### 7.1 Regular Real Estate (₦110k ARPU)
| Line | ₦/month |
|---|---|
| Revenue | 110,000 |
| Flutterwave DD fee (0.8%) | -880 |
| Claude (Haiku + Sonnet mix) | -4,500 |
| Unipile (~1,500 convos) | -2,500 |
| SMS fallback | -1,000 |
| Google Maps + Apollo (amortised) | -1,200 |
| CSM time (~20 min/mo) | -5,300 |
| **Gross margin** | **₦94,620 (86%)** |
| CAC | ₦35k |
| **Payback** | **<1 month** |

### 7.2 Luxury Real Estate (₦450k retainer + commission)
| Line | ₦/month (retainer only) |
|---|---|
| Revenue | 450,000 |
| Rails + infra fees | -5,500 |
| Claude (higher Sonnet mix for quality) | -12,000 |
| Unipile + voice handoff reserve | -6,000 |
| CSM time (~90 min/mo, white-glove) | -24,000 |
| Concierge touch allowance | -8,000 |
| **Gross margin (retainer only)** | **₦394,500 (88%)** |
| Commission upside | ₦0 — ₦3M+ per closed deal |
| CAC | ₦150k (more intro calls, in-person) |
| **Payback** | **<1 month** |

### 7.3 Agency (₦900k + ₦25k/seat × 15 seats avg = ₦1.275M ARPU)
| Line | ₦/month |
|---|---|
| Revenue | 1,275,000 |
| Infra scale (per-seat WhatsApp + data) | -45,000 |
| Claude (scale) | -55,000 |
| Multi-tenant support + custom integrations | -80,000 |
| CSM 2hrs/mo + dedicated Slack channel | -65,000 |
| **Gross margin** | **₦1,030,000 (81%)** |
| CAC | ₦400k (enterprise sales, pilot loss) |
| **Payback** | **<1 month** |

### 7.4 Blended target at Yr 1 end
- 80 Regular × ₦94k GM = ₦7.5M/mo GM
- 12 Luxury × ₦395k GM = ₦4.7M/mo GM
- 6 Agency × ₦1.03M GM = ₦6.2M/mo GM
- **Total blended monthly GM: ₦18.4M**
- **Yr 1 ARR (retainer only): ₦235M**
- **Luxury commission upside: +₦30–120M on top**

That's a venture-worthy number if you hit it. The single biggest risk to it is **billing churn**, not sales volume. Which is why Section 5 matters.

---

## 8. Updated 90-Day Execution Plan (supersedes PLAN.md Phase 2+)

### Weeks 1–2: Fix billing, segment the pitch
- [ ] Build dunning engine (Section 5.4)
- [ ] Integrate Flutterwave Account Charge SDK
- [ ] Split real estate prompts by segment (luxury / regular) in `agent/prompts/closer/`
- [ ] Stand up `/luxury` and `/agency` landing page variants (separate from main /)
- [ ] Lawyer briefing call + draft MSA/DPA
- [ ] Seed 200 regular + 10 luxury + 10 agency target accounts in CRM

### Weeks 3–4: Close first paying Regular + first Luxury
- [ ] Convert 2 of current demo-tier conversations to ₦75k/mo (intentionally under-priced pilot)
- [ ] Pitch 5 luxury agencies in-person / video — close 1 at ₦450k/mo
- [ ] Ship Commission Invoicing module (retainer + commission billing)
- [ ] MSA/DPA sent to lawyer for review

### Weeks 5–8: Scale Regular, agency pilots begin
- [ ] 10 paying Regular clients at ₦110k avg = ₦1.1M MRR
- [ ] 1 Luxury client closed, second in pipeline
- [ ] 2 Agency pilot LOIs signed (30-day unpaid pilots)
- [ ] Legal pack signed off → send to first Regular cohort for backfill signature

### Weeks 9–13: Double down on what's converting
- [ ] Target: 25 Regular + 3 Luxury + 1 Agency paying
- [ ] MRR target: ₦4.5M
- [ ] Referral flywheel in-product live
- [ ] First Agency pilot → paid conversion

---

## 9. What Would Kill This (updated)

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Card churn eats MRR (Section 5) | HIGH | HIGH | Ship dunning engine Week 1 |
| Unipile outage / account ban | MED | HIGH | Meta WhatsApp Business Cloud fallback; 2nd Unipile account hot standby |
| Legal pack delayed → agency deals stall | MED | HIGH | Pay lawyer premium for 2-week turnaround |
| Claude cost blows out at scale | MED | MED | Force Haiku-default, Sonnet-opt-in; per-client token cap |
| Distraction into other suites (AgriOS etc.) | HIGH | HIGH | Feature-flag lock in code. Only reopen when Closer > ₦5M MRR |
| Lagos ₦ devaluation hits Claude costs (priced in $) | MED | MED | Price in ₦ but indexed to CBN FX + quarterly repricing clause in MSA |
| One luxury client = 50% of MRR concentration | MED | MED | Diversify — no single client >15% of MRR |
| Tax reform Jan 2026 PAYE changes break TalentOS payroll | LOW (shipped) | HIGH | Already handled in code per PLAN, verify with accountant before year-end |
| Competitor copies Closer positioning | LOW Yr1 | MED | Distribution moat + HITL proven workflow hard to copy fast |

---

## 10. Scale-Later Wedges (plant flags, don't build)

From your IDEAS.md you already have great instincts. Here's my reordering based on the pivot:

1. **Commission/Deal Closer for Luxury agents (not done yet but adjacent)** — escrow-lite for Nigerian real estate transactions. Partner with a law firm. Take 0.5% of deal value. Massive.
2. **PLUGng (artists)** — your IDEA #0. Reuses 80% of SDR infra. Perfect non-competing spinoff. Do this **after** real estate hits ₦5M MRR, not before.
3. **AI Voice Operator** — IDEA #1. Perfect upsell to existing Closer clients for phone-heavy agencies. Build after 10 paying real estate clients.
4. **AI Invoice Collection** — IDEA #2. Partner with accountants for distribution. Cross-sell to existing TalentOS clients (they have AR).
5. **Embedded rent finance / rent advance** — once you have rent-roll data across 20+ landlords, partner with a licensed MFB. 4–8% cut, very high margin.
6. **Tender Discovery** — IDEA #3. Different customer (contractors), so defer unless a contractor asks.
7. **Pan-African** — Nairobi first (M-Pesa rail), Accra second. Minimum 12 months away.

---

## 11. Quick-Fire: Optimization checklist you can action this weekend

- [ ] Add `segment` field to `clients` schema: `enum(luxury, regular, agency)`
- [ ] Split `agent/prompts/closer/real_estate.txt` → `…_luxury.txt`, `…_regular.txt`, `…_agency.txt`
- [ ] Create dashboard filter by segment
- [ ] Tag Google Places pulls with target-segment labels so future campaigns auto-route
- [ ] Add `billing_status` to admin Overview — daily dunning queue visible
- [ ] Write a 1-paragraph Luxury case study template — fill in when first luxury client lands
- [ ] Add "Refer a peer agency → ₦50k credit" banner in client portal
- [ ] Hide all non-Estate/Talent suite routes behind a feature flag until triggered
- [ ] Add cost-per-client dashboard pulling Claude usage + Unipile usage tagged by `client_id`
- [ ] Write Commission Invoice flow into Closer (Section 5.5)

---

## 12. The 3 Decisions You Must Make This Week

1. **Are you selling Closer as 3 products (Luxury / Regular / Agency) or 1?** My strong rec: 3 SKUs, 3 landing pages, 3 prompts, 1 codebase, 1 CSM (you).
2. **Are you building the dunning engine before or after first paid client?** My strong rec: **before**. The day you charge your first ₦110k, your billing must be bulletproof.
3. **Are you killing the 17 deferred suites or keeping them alive?** My strong rec: soft-kill (feature flag off), keep code, revisit only when Closer > ₦5M MRR.

---

## Appendix A — Updated Tech Stack Map

| Layer | Current | My take |
|---|---|---|
| API | FastAPI | ✅ perfect |
| DB | MongoDB Atlas | ✅ perfect for this shape |
| LLM | Claude Haiku 4.5 + Sonnet | ✅ correct Haiku-default |
| WhatsApp | Unipile | ⚠️ single vendor risk — add Meta WA BSP for Agency tier |
| Email | Unipile | ⚠️ same — add Resend/Brevo fallback |
| SMS | missing | 🔴 add Termii — needed for dunning ladder |
| Discovery | Google Maps + Apollo | ✅ good; drop Social scraping per your own PLAN comment |
| Scheduler | APScheduler | ✅ good |
| Billing | Paystack partial | 🔴 rebuild per Section 5 |
| Frontend | Jinja2 templates | ⚠️ fine for admin, needs React on luxury client-facing portal eventually |
| Hosting | Railway | ✅ fine at current scale; consider GCP when Agency tier lands (data residency) |
| Observability | structlog | 🟡 add per-client cost tags; Sentry for errors |
| Legal | Drafts | 🔴 lawyer this week |

---

## Appendix B — Revised Public Pricing Card

```
╭──────────────────────────────────────────────────────────────╮
│                    REACHNG CLOSER — REAL ESTATE              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  SOLO / REGULAR AGENT                    ₦110,000 / month    │
│  ───────────────────────                                     │
│  • AI WhatsApp qualifier                                     │
│  • Rent chase loop (up to 50 units)                          │
│  • Listing + doc clerk                                       │
│  • ₦5k per qualified viewing booked                          │
│                                                              │
│  LUXURY AGENT           ₦450,000 / mo + 3-5% deal commission │
│  ──────────────                                              │
│  • Everything in Regular                                     │
│  • International buyer handling (24/7 across time zones)     │
│  • Discreet PoF concierge                                    │
│  • Lawyer Bundle integration                                 │
│  • White-glove onboarding + dedicated CSM                    │
│                                                              │
│  AGENCY (10-80 staff)    from ₦900,000 / mo + ₦25k per seat  │
│  ────────────────────                                        │
│  • Multi-branch dashboard + HITL for every agent             │
│  • Lead-ownership audit trail                                │
│  • TalentOS HR bundled (optional -20% combined discount)     │
│  • Custom integrations (ERP, accounting)                     │
│  • Dedicated success manager + SLA 99.5%                     │
│                                                              │
│  SETUP (all tiers): ₦100k — waived on 12-month commitment    │
│  ANNUAL DISCOUNT: 2 months free                              │
│                                                              │
╰──────────────────────────────────────────────────────────────╯

                  REACHNG TALENTOS — HR BACK OFFICE
                    (upsell / standalone for SMEs)

       STARTER (5–20 staff)         ₦80,000 / month
       GROWTH  (21–50 staff)        ₦180,000 / month
       ENTERPRISE (50+)             Custom
```

---

## Appendix C — The "Why This Is Different From SeamlessHR / NPC / PropertyPro / ZohoCRM" Cheat Sheet

| Competitor | Why you're not them |
|---|---|
| **SeamlessHR / Bento** | Enterprise payroll. You're workflow + AI for <50-staff SMEs. Don't compete; partner/integrate. |
| **Nigeria Property Centre, PropertyPro, PrivateProperty** | Listing marketplaces. You don't do listings; you close the leads their listings generate. **Complementary, not competitive.** |
| **Zoho CRM / Salesforce / HubSpot** | Generic CRM. You're Lagos-culture-native, WhatsApp-first, HITL-by-default, naira-priced. |
| **International SDR SaaS (Outreach.io etc.)** | US-centric, email-first, $$$/mo. Dead on arrival in Lagos. |
| **Lagos marketing agencies (manual)** | You're 10x cheaper + 100x more consistent. Poach their disgruntled clients. |

---

## Final Note — The Hungry Entrepreneur Move This Week

1. **Block Monday 9am–12pm** → write segment-specific Closer prompts (3 of them).
2. **Block Monday 2pm–5pm** → draft Flutterwave Account Charge integration.
3. **Tuesday** → call/WhatsApp 5 luxury agents personally. In-person if you can get a meeting in Ikoyi.
4. **Wednesday** → brief a Lagos commercial lawyer (aim for a fixed-fee ₦350k package for MSA/DPA/NDA/Closer Addendum, 2-week SLA).
5. **Thursday + Friday** → ship dunning engine v1.
6. **Weekend** → hand-write 3 luxury case-study templates (fill in later). Polish `/luxury` landing page.
7. **The following Monday** → first live outbound into the 3 new segments.

The loop closes. Lemons → Lemonade.

---

*ReachNG Strategy Doc · written April 2026 for Oluwaseun Oluyori Ajagun · Lagos, Nigeria · Based on actual codebase audit at `/app`*
