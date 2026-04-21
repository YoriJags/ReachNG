# Real Estate + HR Automation SaaS — Lagos Pressure Test & Strategy

> **Audience:** You (founder), honest teardown mode  
> **Stack in hand:** Google APIs (Places, Maps, Workspace, Gmail), Claude API, recurring billing (to be built)  
> **Thesis in one sentence:** Sell "invisible employees" to Lagos real estate agencies and SMEs — AI agents that do the boring, repeatable, high-volume work nobody wants to do — priced as cheap recurring SaaS, sold via a Google-Places-powered outbound machine *you* also operate for them as an upsell.

---

## 0. The Brutal TL;DR

- **Stop calling it "automation SaaS."** Nigerian SMEs don't buy software; they buy **outcomes and staff replacements**. Reposition as "AI Staff" you rent out monthly.
- **Real Estate is the better wedge than HR.** HR has SeamlessHR (processed ₦1T in payroll in 2025) + Bento + PaidHR locking down the mid-market. Real estate is fragmented, software-phobic, and full of ₦50k/mo willingness-to-pay pockets. Land here first.
- **Your unfair advantage is not Claude.** Everyone has Claude. Your unfair advantage is **Google Places API → 3,600+ verifiable real estate agencies** + a direct-debit-backed billing rail that survives card failure rates. Distribution is the moat.
- **Biggest Lagos killer you're underestimating:** card failure + subscription churn from expired naira cards. Solve this at architecture level on day 1 (Flutterwave Account Charge / direct debit) or your MRR will look like a sawtooth.
- **Don't build a platform. Build 3 narrow agents, each worth a full salary replaced.** Price each at ₦35–80k/mo. Bundle at ₦150k/mo. That's your first ₦10M MRR path.

---

## 1. Market Reality — Lagos Pressure Test

### 1.1 Real Estate (primary wedge)
| Signal | Data | So what |
|---|---|---|
| Total agencies in Nigeria | ~3,614 verified (Oct 2025), 16,265 listings on NPC | Your TAM for outbound is knowable and finite. Good. |
| Proptech usage among surveyed pros | 71% use *something* (listings, valuation, mgmt) | They're not software-virgins — they'll buy if pitched right |
| #1 barrier to PMS adoption | Lack of awareness, then cost | **Don't sell software. Sell hours saved / deals closed.** |
| Infra reality | Power outages, unreliable internet, data distrust | Must work on mobile-first, offline-tolerant, WhatsApp-native |
| Mortgage access | Only 10% of households | Rent-dominant market. Rent collection / tenant mgmt is the hot loop. |
| Documentation pain | Title verification delays, incomplete paperwork | Huge AI-assist opportunity (Claude vision + doc parsing) |

**Archetype to sell to:**  
**The "One-Man Army" Agent** — 1 principal + 2–5 staff, 30–150 listings, operating Lekki/Ikeja/Ikoyi/VI. They spend 60% of their week on: (1) chasing rent, (2) qualifying WhatsApp leads, (3) forwarding listings to buyer groups, (4) scheduling property viewings, (5) formatting proposals. **Every single one of these is automatable.**

### 1.2 HR (secondary, defer to Phase 2)
| Signal | Data | So what |
|---|---|---|
| Incumbent | SeamlessHR — ₦1T payroll processed 2025, Wema/OPay/AXA clients | **Don't fight them on payroll.** You lose. |
| Competitors | Bento, PaidHR, Workpay, HRGym | Crowded. Every one has direct sales teams. |
| 2026 tax reform | New PAYE rules effective Jan 1 2026 | **Compliance chaos = opening**, but SeamlessHR already shipped it (Nov 2025). |
| SME white space | <50 employee companies still on Excel + WhatsApp groups | Real. Not where the big boys fight. |

**HR wedge to pick:** *not payroll*. Instead: **recruitment automation + onboarding + leave/attendance for <50-person SMEs**. Bento starts at mid-market; you own the 5–50 employee gap where founders are still screening CVs by hand at midnight.

---

## 2. The Product Bets (ranked by conviction)

### 🥇 Product 1 — "Agent OS" for Real Estate (Lead wedge)
Sell as **3 AI Staff**, each replacing a ~₦80–150k/mo human hire:

#### Agent A: **"Bisi" — The Lead Qualifier** (launch first)
- WhatsApp Business API + Claude
- Agency's WhatsApp number forwards new inbound leads → Claude asks qualifying questions (budget, location, timeline, Stamp duty/agency fee awareness, financing ready?)
- Auto-tags: hot / warm / tire-kicker
- Books site visits via Google Calendar integration
- Hands off hot leads to agent with full context summary
- **Price:** ₦45k/mo per WhatsApp line
- **Claude cost estimate:** ~₦3–6k/mo per client (Haiku/Sonnet 4.5 mix)
- **Margin:** 85%+

#### Agent B: **"Chike" — The Rent Chaser**
- Imports tenant roster (CSV / Google Sheets)
- Sends personalized WhatsApp + SMS reminders on a schedule (T-7, T-3, T-0, T+3, T+7, T+14)
- Escalates politely; negotiates payment plans using a script you define
- Generates receipts via Paystack/Flutterwave payment links
- Logs promises, broken promises, excuses in a ledger the landlord can see
- **Price:** ₦35k/mo up to 50 units, ₦75k/mo up to 200 units
- **Why it wins:** landlords *hate* chasing rent; this is the #1 pain. Payback < 1 cycle.

#### Agent C: **"Tobi" — The Listing & Document Clerk**
- Paste a property brief → Claude writes polished listing copy (+ variations for Instagram/WhatsApp/NPC format)
- Upload title docs / C of O / survey → Claude flags missing pages, mismatched names, expiry dates (this is *huge* — deals collapse over this)
- Generates letters of offer, tenancy agreements from templates, fills variables
- Translates buyer questions into "next step" checklists
- **Price:** ₦25k/mo solo, ₦60k/mo team of 5

**Bundle:** "Full Agency" at **₦110k/mo** (saves ₦25k vs à la carte). **Annual at 2-months-free = ₦1.1M ARR/client.**

### 🥈 Product 2 — "HR Sidekick" for SMEs (Phase 2, month 4+)
Three agents again:
- **Recruiter Agent:** Post job → Claude screens CVs against JD → ranks top 10 with reasoning → auto-schedules screening calls via Google Calendar → generates interview question packs
- **Onboarding Agent:** New hire → collects docs (BVN, NIN, guarantors) via WhatsApp → generates offer letter → sets up Google Workspace account → adds to payroll provider (integration with SeamlessHR/Bento/Paystack)
- **Leave & Attendance Agent:** WhatsApp-based check-in/out, leave requests routed to approver, auto-updates master roster

**Price:** ₦40k/mo starter (up to 20 staff), ₦90k/mo growth (up to 50)

**Why not lead with HR:** harder to demo the "aha" in 5 minutes, longer sales cycle, B2B HR decisions involve the MD *and* the admin *and* the accountant. Real estate has **one decider** — the agency principal.

### 🥉 Product 3 — "Payroll Autopilot" add-on (Phase 3)
**Do NOT build payroll.** Integrate with SeamlessHR/Bento and be the **workflow layer on top**. Partnership, not competition.

---

## 3. The Recurring Billing Architecture (this is where most Nigerian SaaS dies)

### 3.1 The problem you haven't fully sized
Nigerian naira cards have **~15–30% failure rate** on recurring charges (expired, blocked for FX, insufficient balance, issuer decline). If your MRR is ₦5M and 20% fail monthly, you bleed ₦1M unless you have dunning + fallback rails.

### 3.2 Recommended architecture
```
Primary rail:    Flutterwave Account Charge (direct debit from bank) 
                 → cardless, tokenized bank mandate, survives card expiry
Backup rail:     Paystack card-on-file (tokenized) 
                 → retry ladder on fail: T+1, T+3, T+7
Dunning layer:   WhatsApp + Email + "Your Bisi agent is paused" 
                 → automated grace period, soft lock not hard lock
Manual fallback: Paystack payment link sent via WhatsApp 
                 → 1-tap recovery
```

**Fees reality check:**
- Paystack: 1.5% + ₦100 local (capped at ₦2,000), waived under ₦2,500
- Flutterwave: 1.4% + ₦2,000 local on cards, lower on direct debit
- On a ₦110k/mo bundle: Paystack = ₦1,750, Flutterwave direct debit = ~₦1,540
- **Model 1.8% gross fee drag** in your P&L; don't let anyone hand-wave this

### 3.3 Mandate-first, not card-first onboarding
On signup, prioritize getting the **bank mandate** (direct debit authorization). Card is the backup. Most Nigerian SaaS does this backwards and pays for it in churn.

---

## 4. GTM: The Google-API Lead Machine (your unfair distribution)

### 4.1 Supply — build the lead pipe in week 1
```
Google Places API Text Search 
  "real estate agency [Lekki|Ikeja|Ikoyi|VI|Yaba|Ajah|Gbagada|Surulere|Magodo|Ogba]"
  → paginate 3 pages per query (60 per city × 8 areas = ~480 raw)
  → place_id → Place Details (name, phone, website, address, rating)
  → dedupe on phone number
  → enrich: scrape website for email (Scrape.do / Apify) 
  → enrich: Instagram handle (Apify IG scraper using agency name)
  → Claude pass: classify "solo agent / small agency / developer / scam" from website copy
  → Google Sheet → your CRM
```

**Expected yield per cycle:** 1,500–2,500 unique Lagos agencies, ~70% with phone, ~40% with website, ~25% with scrapable email, ~60% with Instagram. Refresh quarterly — Places Insights shows operational status.

**Cost:** Places API ~$30–60 per 10k queries. Rounding: **~₦30–50k** to build the entire Lagos list. This is nothing. Do it tomorrow.

### 4.2 Demand — the 3-channel sequence
For each lead: **WhatsApp → Phone call → Email**, in that order (reverse of Western playbook).

**WhatsApp opener (Claude-personalized per agency):**
> "Hi [Agency Name] — saw your listings in [Lekki]. I run a tool that replies to every WhatsApp lead for you in under 30 seconds, 24/7, so you stop losing night-time enquiries to faster agents. 7-day free test on your own number, no credit card. Interested in a 5-min demo?"

**Conversion math (pressure-test these):**
- List: 2,000 agencies
- WhatsApp open rate: 70% = 1,400
- Reply rate: 8% = 112
- Demo booked: 35% of repliers = ~40
- Close rate: 25% = **10 paying customers from one sequence**
- At avg ₦70k/mo: **₦700k MRR per 2,000-lead cycle**

Run 2 cycles/month across Lagos + Abuja + PH = ₦2M+ MRR trajectory by month 4. **This is the whole game.**

### 4.3 The referral flywheel (the part everyone forgets)
Real estate agents are in 40+ WhatsApp groups with other agents. When Bisi books a site visit at 2am that closes, they brag. **Build a one-tap referral button inside the product — ₦10k credit for both sides.** In Lagos real estate, referral > ads, always.

---

## 5. Claude as the Brain — what actually needs AI vs what doesn't

| Workflow | Needs Claude? | Why |
|---|---|---|
| WhatsApp lead qualification | ✅ Sonnet 4.5 | Multi-turn, vernacular, context |
| Rent reminder copywriting | ✅ Haiku 4.5 | Cheap, personalized, tonal |
| Listing description generation | ✅ Sonnet 4.5 | Quality matters for brand |
| Title document parsing (C of O, deeds) | ✅ Claude w/ vision | **This is your 10x moat** — very few tools do this |
| CV screening | ✅ Sonnet 4.5 | Reasoning w/ JD match |
| Payment reconciliation | ❌ | Use Paystack webhooks + pandas |
| Calendar scheduling | ❌ | Google Calendar API directly |
| WhatsApp message sending | ❌ | Meta Business API directly |
| SMS fallback | ❌ | Termii / BulkSMSNigeria |

**Cost modeling (do this now, not later):**  
Budget ₦2k–6k/mo per customer for LLM spend. At ₦70k ARPU that's ~6% COGS. Watch Haiku vs Sonnet split — force Haiku for anything under 200-token outputs.

---

## 6. Unit Economics Stress Test

Assume bundled product, ₦110k/mo ARPU.

| Line | ₦/month per customer | Notes |
|---|---|---|
| Revenue | 110,000 | |
| Payment fees (1.8%) | -1,980 | Paystack/Flutterwave blended |
| LLM (Claude) | -5,000 | Sonnet + Haiku mix |
| WhatsApp Business API (Meta) | -2,500 | ~1,500 convos/mo |
| SMS fallback | -1,500 | ₦3.5/SMS × ~400 |
| Google Workspace / infra | -3,000 | |
| Support (fractional) | -8,000 | ~30 min/mo at ₦16k/hr CSM |
| **Gross margin** | **₦88,020 (80%)** | Healthy |
| CAC target | ₦40k–60k | 1-visit demo + WhatsApp outreach cost |
| Payback period | **<1 month** | Beautiful for SaaS |

**Churn scenario modeling:**
- If monthly churn = 8% (plausible year 1, Lagos): LTV ≈ ₦1.1M, LTV/CAC = 20x ✅
- If monthly churn = 15% (worst case, card failures unfixed): LTV ≈ ₦585k, LTV/CAC = 10x ⚠️ still ok but uncomfortable
- **Kill criterion: monthly churn >20% for 3 consecutive months.** Means the product isn't sticky and you're renting attention not solving pain.

---

## 7. 90-Day Execution Plan

### Weeks 1–2: Pipe + Prototype
- [ ] Google Cloud project + Places API + billing (day 1)
- [ ] Pull 500 Lagos agency leads, enrich, load to Airtable
- [ ] Build **Agent A (Bisi) MVP**: WhatsApp Business + Claude + Google Calendar
- [ ] Paystack test integration for recurring (plan creation, webhook, dunning stub)
- [ ] Land 3 free design partners (not friends — real cold outreach)

### Weeks 3–6: Paid Pilots
- [ ] Convert 2 of 3 design partners to paid at ₦30k/mo (intentional under-price)
- [ ] Ship **Agent B (Chike)** — Rent Chaser
- [ ] Flutterwave Account Charge live as primary rail
- [ ] Onboard 10 paying customers total

### Weeks 7–10: Distribution Engine
- [ ] Scale Places API pull to all Lagos + Abuja (3,000+ leads)
- [ ] 2 full outreach cycles, target 20 demos/week
- [ ] Ship **Agent C (Tobi)** — listings + docs
- [ ] Hit **30 paying customers × ₦60k ARPU = ₦1.8M MRR**

### Weeks 11–13: Harden + Prep HR Wedge
- [ ] Churn audit; fix top 3 reasons
- [ ] Launch referral program with credits
- [ ] First **HR Sidekick** prototype w/ 2 friendly SMEs
- [ ] **Target: ₦3M MRR end of day 90**

---

## 8. What Will Kill This (sorted by probability)

| Risk | Probability | Mitigation |
|---|---|---|
| Card failure churn destroys MRR | **HIGH** | Direct debit primary, aggressive dunning, grace period ≥ 10 days |
| WhatsApp Business API restrictions / template approval delays | HIGH | Start application week 1; have SMS + Telegram backup |
| Agencies demand custom work / won't use self-serve | HIGH | Productize onboarding as a 45-min concierge call; charge ₦25k setup |
| Claude API costs blow out with heavy users | MED | Usage caps per plan tier, Haiku-first routing, cache common replies |
| SeamlessHR / Bento pivots down-market | MED | You're nimbler + real-estate-first. Don't directly compete. |
| Data trust / client says "na my file you dey keep?" | MED | Nigerian data residency story, NDPA compliance, clear DPA, audit logs visible in UI |
| Power outages break your WhatsApp agent uptime | LOW (it's cloud) | Host backend on GCP, not local box |
| A bigger fish clones this | LOW year 1 | Distribution moat + agency-specific workflows are hard to copy quickly |
| You run out of cash before PMF | MED | Pre-sell annuals at 2-months-free to get cash upfront; ₦1.1M × 10 = ₦11M runway |

---

## 9. Scale-Later Wedges (don't build yet, but plant flags)

1. **Embedded finance for landlords** — once you sit on rent collection data, offer rent advance / factoring (partner with a licensed MFB). Higher-margin than SaaS.
2. **Marketplace layer** — cross-agency listing sharing with revenue split (you take 5% of successful closes you source between member agencies).
3. **Insurance tie-in** — contents/building insurance distributed inside Agent OS (Hygeia, AXA, Leadway partnerships; 15–20% referral).
4. **Legal-in-a-box** — Claude + template library for tenancy agreements, deed of assignment, PoA. Partner with a law firm for human review SLA.
5. **Facility mgmt upsell** — vendor dispatch (plumbers, electricians) with markup. Natural extension of tenant mgmt.
6. **HR payroll financing** — once you're in SMEs, partner with Lendsqr / Renmoney for on-demand pay. Don't lend yourself.
7. **Pan-African copy** — Nairobi next (similar informal rental market, M-Pesa rail). Accra third.

---

## 10. "Lemons to Lemonade" — Lagos-specific re-framings

| Lemon | Lemonade |
|---|---|
| Agencies distrust software | Position as "AI staff you rent" — culturally they understand staff |
| Cards fail constantly | Flutterwave direct debit from day 1 becomes *your* selling point to other founders later (productize it?) |
| Agents live on WhatsApp, not dashboards | Build WhatsApp-first, web is the admin afterthought — this is 10x easier than you think |
| Documentation is a mess | Claude vision-based title-deed checker is genuinely novel and demo-able in 60 seconds |
| No credit data | Your rent-ledger dataset becomes a credit signal over time — future data moat |
| Power outages | Customers are *extra grateful* for cloud agents that never sleep — lean into this in marketing |
| Market is fragmented | Perfect for a bottoms-up SaaS; no 3-month enterprise sales cycle |

---

## 11. Decision Tree — What to Build This Week

```
IS Agent A (Bisi/WhatsApp Lead Qualifier) technically working 
end-to-end on 1 demo agency by Day 10?
   │
   ├─ YES → start paid pilots, move to plan
   │
   └─ NO  → something is broken in WhatsApp Business API setup
            (this is usually Meta approval, not code)
            → fallback: launch on Telegram + SMS for pilots
              while WhatsApp approval cooks in background
```

**Your single most important milestone:** One paying agency, one month, one renewal. Everything else is noise until that proves the ₦45k/mo WhatsApp qualifier loop.

---

## 12. The Entrepreneur's Honest Self-Check

Ask yourself weekly:
1. Am I selling **outcomes** (leads closed, rent collected) or **features** (AI! automation!)? If features, I'm losing.
2. Is my ARPU trending up or flat? Flat = no upsell path, dead-end SaaS.
3. What's my **gross churn vs. net churn**? If net churn is positive (expansion > churn), I have a real business.
4. Am I shipping faster than my 3 main competitors (SeamlessHR, Bento, international Proptech)? If not, why not?
5. **Have I spoken to 5 customers this week?** Not 5 leads — 5 existing customers. This is where 80% of roadmap insight lives.

---

## Appendix A — Tech Stack Recommendation

| Layer | Pick | Why |
|---|---|---|
| Backend | FastAPI (Python) | Your stack, Claude SDK mature, MongoDB compatible |
| Frontend (admin) | React + Tailwind + shadcn | Fast enough; 90% of customers live on WhatsApp, not the dashboard |
| Messaging | Meta WhatsApp Business Cloud API (official) | Don't use grey-market gateways; Meta will ban |
| SMS | Termii or BulkSMSNigeria | Cheap, reliable, local sender IDs |
| Email | Resend or Brevo | Better deliverability to Nigerian inboxes than SendGrid |
| LLM | Claude Sonnet 4.5 (reasoning) + Haiku 4.5 (bulk) | You have keys. Force Haiku for simple tasks. |
| Vision (docs) | Claude with vision | Better than OCR for structured-title parsing |
| Payments | Flutterwave Account Charge (primary) + Paystack (backup) | Direct debit survives card failure |
| Lead gen | Google Places API + Scrape.do + Apify | Your distribution unfair advantage |
| Calendar | Google Calendar API | You have keys |
| CRM | Airtable at first, Postgres/Mongo later | Don't build CRM in month 1 |
| Analytics | PostHog self-hosted | Cheap, Nigeria-friendly pricing |
| Hosting | GCP Lagos-adjacent region (europe-west1 or Mumbai) | Data residency question handled |

---

## Appendix B — Pricing Card (first public version)

```
🏠 REAL ESTATE

  SOLO AGENT             ₦35,000 / month
  ───────────────────
  • 1 AI agent (pick: Bisi, Chike, or Tobi)
  • Up to 50 units / month
  • WhatsApp + Email
  • Standard support

  AGENCY TEAM            ₦110,000 / month  ⭐ Most Popular
  ───────────────────
  • All 3 AI agents
  • Up to 200 units / month
  • WhatsApp + Email + SMS fallback
  • Priority support + 45-min onboarding
  • 1 hour/mo of custom prompt tuning

  ENTERPRISE             Custom (from ₦300k/mo)
  ───────────────────
  • Everything in Agency Team
  • Multi-branch, role-based access
  • Dedicated success manager
  • Custom integrations (ERP, accounting)
  • SLA 99.5%, data residency documentation

ANNUAL DISCOUNT: 2 months free (pay 10, get 12)
SETUP FEE: ₦25,000 (waived on annual)
```

---

## Final Note

The win condition is **not** being the next SeamlessHR. It's being the thing that **every Lagos real estate agency under 20 people uses by default** within 24 months — because nothing else speaks WhatsApp + Naira + their actual daily rhythm.

**Hungry-entrepreneur move for this week:** spin up the Places API pull, pick 10 agencies in Lekki Phase 1 (you can literally drive past them), call/WhatsApp each one personally, ask them to screen-share their current workflow for 15 minutes. You'll have your MVP spec written by Friday, and 2 design partners by Monday.

Lemons ✔ Lemonade 🍋
