# ReachNG — Products

What we actually sell. Who to. For how much. Status.

Last updated: 2026-04-30

---

## What ReachNG is (lead with this, always)

**ReachNG is an agentic employee for Nigerian SMEs.** The client brings their leads — inbound WhatsApp/IG/web enquiries, BYO CSVs they've already pulled, referrals — and the agent works them: drafts replies, qualifies, follows up, closes. Once a deal is signed, the same agent runs the operational back-office work the founder used to do by hand. Every outbound is human-approved; every message sends from the client's own WhatsApp number, not ours.

The pitch is the agent — what it *does for them*. Not a feature matrix.

**Two things the agent does for paying clients, in order:**
1. **Closes & nurtures** — works leads the client feeds in. Drafts the first-touch, qualifies the replies, handles objections, books the action (viewing, call, quote, payment), runs day-3 / day-7 follow-up sequences automatically.
2. **Operates** — once they're a customer, the same agent runs the operational work: rent chase, payroll, invoice follow-up, KYC, lawyer bundles, attendance, payslips. Suites are *jobs the agent already knows how to do*, not products in their own right.

**What ReachNG does NOT do for clients:** prospect on their behalf. Discovery (Google Maps, Apollo, social signals) is *our* internal customer-acquisition funnel — it's how we find SMEs to pitch ReachNG to. It is not a feature we sell. If a client asks for outbound prospecting, that's an upsell conversation, not the default product.

The internal suite names below (EstateOS, TalentOS, etc.) are **codenames only** — they exist for engineering clarity. Externally, everything is "ReachNG."

**However:** for prospects in a vertical where we already have an operational suite, mention it as an *included extra* after leading with the agent pitch. Examples:
- To a Lagos estate agent: "Because you're in real estate, you also get Rent Roll + chase, KYC vault, and the Lawyer Bundle — included, no extra fee."
- To an HR firm: "Plus full Nigerian payroll (PAYE/CRA/PENCOM/NHF), Leave, Attendance, Probation tracking — included."

The agent is always the headline. The suite is the *and-also*.

---

## Live products (sold externally as "ReachNG")

### 1. ReachNG Closer — Real Estate
**Status:** In build — Phase 1 of 5 (see [PLAN.md](./PLAN.md))

**Who:** Estate agents, property developers, brokers, agencies in Lagos with active listings and inbound inquiry volume (WhatsApp DMs, Instagram messages, website forms, referrals).

**Pain solved:** Leads go cold between first ping and viewing. Agents lose ₦500K–₦5M per leaked lead. Saturdays burnt on unqualified viewings. Awkwardness around PoF chase.

**What we do:** Work the client's inbound leads for them. AI drafts qualifying questions, books viewings, handles PoF requests, nurtures warm-not-ready buyers. Every message approved in our HITL dashboard and sent from the client's own WhatsApp number. Client only shows up for qualified viewings.

**Hero features:**
- Lead-to-Viewing Closer (24/7 WhatsApp response)
- Proof-of-Funds Concierge
- Nurture loop for warm-not-ready leads
- Handover card (budget, timeline, objections)

**Upsells:** KYC vault, Neighborhood Scorecard, Lawyer Handover Bundle, Rent Chase Loop (only for clients who manage tenancies).

**Pricing:** ₦100K setup + ₦150K–₦400K/mo retainer + ₦5K–₦15K per qualified viewing. Optional commission tier (3–5% of deal value) for luxury agents on Banana Island / Ikoyi / Eko Atlantic.

**Internal codename:** EstateOS (use only in code, dashboard, docs — never in client-facing copy)

---

### 2. ReachNG TalentOS — HR Back Office
**Status:** Built — polish and sell

**Who:** Employers with 10+ staff, HR teams, staffing firms managing their own internal ops. Professional services, tech, financial services, oil & gas.

**Pain solved:** HR drowning in manual admin — payroll math every month, leave requests lost in WhatsApp, PENCOM remittance by hand, candidates screened over days of back-and-forth, policy questions asked 50 times a day.

**What we do:** Back-office automation. **We do not contact the client's candidates or staff on their behalf** — this is workload removal, not outreach.

**Hero features:**
- Nigerian-compliant payroll (PAYE/CRA/PENCOM/NHF), printable payslips, PENCOM schedule
- Leave manager (request → approve → balance tracking)
- Attendance dashboard
- Probation tracker with auto-reminders
- AI candidate screener (playbook generator — *they* run the screen)
- Policy Oracle (WhatsApp Q&A from their uploaded handbook)
- Offboarding checklist generator
- Moonlighting + salary-erosion flags (retention risk)

**Pricing:** ₦50K setup + ₦50K–₦200K/mo retainer, tiered by staff count.

**Internal codename:** TalentOS (use only in code, dashboard, docs — never in client-facing copy)

---

## Internal acquisition engine (not sold — it's how we find clients)

### ReachNG SDR
**Status:** Live and running

Google Maps + Apollo + Unipile WhatsApp discovery → cold outreach → HITL draft queue → approved send → reply tracking → conversion.

**Two active campaigns:**
- `real_estate` vertical → pitches ReachNG Closer
- `recruitment` vertical → pitches ReachNG TalentOS

This funnel never stops. It's our only top-of-funnel until referrals kick in.

---

## Deferred — not being built

All other suites from the catalog (BuildOS, LegalOS, LuxuryOS, LendOS, SchoolOS, ClinicOS, BizOS, FleetOS, EventOS, TrustOS, MarketOS, GigOS, TenderOS, UtilityOS, HealthOS, LogisticsOS, HospitalityOS, ImpactOS, MediaOS) and the agri B2B matchmaker idea.

**Unlock condition:** Closer has 3+ paying clients AND TalentOS has 3+ paying clients AND monthly recurring ₦ > operating cost. Until then, mention only when a prospect specifically asks and there's a clear close — otherwise stay on the two live products.

See [PLAN.md](./PLAN.md) for the deferred matrix.

---

## Future modules — vertical-matched operations (deferred, post-first-paying-client)

These are *agent jobs*, not standalone products. ReachNG remains the single face; the agent dispatches to the right module based on the client's vertical. Pitched as **"included extras"** after the agent headline — never as the headline themselves.

**Build order is determined by which vertical we close first.** Same primitives across all four (Unipile WhatsApp inbound, OCR, Mongo, scheduler, HITL) — incremental build cost per module is low once the first one ships.

| Module | Codename | What the agent does | Lead vertical | Cross-sell to | Reuses |
|---|---|---|---|---|---|
| **Locker** | DocVaultOS | Forward any doc on WhatsApp → OCR → tagged + searchable + expiry alerts (CAC, TIN, tenancy, IDs, supplier invoices) | Real estate agencies (already in funnel — drowns in tenancy/CAC docs) | Every vertical | Unipile inbound, OCR, Mongo |
| **Receipt** | BooksOS | Forward POS/transfer alerts/expense voice-notes → AI categorises → daily P&L + monthly statement PDF + FIRS-ready ledger | Restaurants, QSR, pharmacies, mini-marts | Every SME (FIRS digital-record mandate makes it not-optional) | Unipile inbound, OCR/STT, ledger schema |
| **Roll Call** | AttendOS | Staff WhatsApp 📍 ping at clock-in (geofenced) → attendance sheet + payroll deductions auto-computed | Salons, schools, training centres, dispatch/logistics | TalentOS clients (feeds straight into existing payroll) | Unipile inbound, geofence, TalentOS payroll engine |
| **Shelf** | StockOS | End-of-day shelf photo → AI counts SKUs → diffs against POS sales → flags shrinkage | Pharmacies, mini-marts, salons (product-heavy), supermarkets | Restaurants, QSR | Image model, Mongo, scheduler |

### Vertical → module bundle (how to pitch)

When ReachNG SDR lands a prospect in one of these verticals, the agent leads with sales/ops as always, then mentions the matched module as the "and-also":

| Vertical | Headline (what we sell) | Included extras (the and-also) |
|---|---|---|
| Real estate agencies | ReachNG Closer | **Locker** + KYC vault + Lawyer Bundle + Rent Chase |
| Restaurants / QSR | ReachNG agent | **Shelf** + **Receipt** |
| Pharmacies / mini-marts | ReachNG agent | **Shelf** + **Receipt** |
| Salons / spas | ReachNG agent | **Roll Call** + **Shelf** |
| Schools / training centres | ReachNG agent | **Roll Call** + **Locker** |
| Logistics / dispatch | ReachNG agent | **Roll Call** (geofenced) + **Receipt** |
| HR-led firms (10+ staff) | ReachNG TalentOS | **Roll Call** + **Locker** |

### Unlock conditions

- **Locker (#4)** — first to build. Trigger: 1+ paying Closer client. Real-estate cross-sell is immediate; build effort lowest.
- **Receipt (#1)** — second to build. Trigger: 3+ paying clients across Closer + TalentOS combined. Largest TAM, biggest standalone product if it ever spins out.
- **Roll Call (#6)** — third. Trigger: TalentOS has 3+ paying clients (it slots straight into the existing payroll engine).
- **Shelf (#8)** — fourth. Trigger: a paying restaurant/pharmacy/salon prospect asks for it explicitly.

Until those triggers fire, do not start work on these. The current focus remains landing first paying Closer client (see [PLAN.md](./PLAN.md) Phase 1.5).

### Agent-economy modules (post-2027)

The original "agent receipt reconciliation" and "toxic agent flow" ideas — capturing transactions made by clients' AI agents and scoring agent-driven traffic for fraud — are real but premature. Nigerian SMEs do not yet have AI agents transacting on their behalf at meaningful volume. Re-evaluate when:
- 10%+ of ReachNG clients are running their own AI agents that transact, OR
- Stripe MPP / Tempo / x402 see African merchant adoption.

Until then: park.
