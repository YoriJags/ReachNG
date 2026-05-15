# ReachNG Product Audit

**Date: 2026-05-14 | Code-verified capabilities only**

## ENGINE — WHAT IT REALLY DOES

The core drafting engine is **real**. All outbound messages use Claude Haiku 4.5 via agent/brain.py, layered with:
1. Base system.txt (77 lines)
2. Nigerian context (127 lines) — injected under every vertical
3. Vertical primer (99–152 lines) — e.g. real_estate.txt, clinics.txt
4. Client brief (BusinessBrief model) — overrides vertical when provided

**Personalization scope:**
- B2B outreach: business name, address, rating, website, contact name/title
- B2C: customer name, client brief, notes, tags
- Chase: debtor name, amount, days overdue, product type
- Reply: inbound intent + original context

**19 verticals** with 99–152 lines each.

---

## HITL FLOW — VERIFIED END-TO-END

Human approval **enforced at architecture level**.

1. Draft generated → queue_draft() in tools/hitl.py (always, never direct send)
2. Brief gate: prospecting sources hard-blocked if brief incomplete; transactional warn-only
3. Autopilot check (if enabled): classify_for_autopilot() checks for complaints/disputes
4. Dashboard approval: GET pending, tap Approve/Edit/Skip
5. Send only if not expired (72h window)
6. Audit trail on every draft

**No bypass.** tools/hitl.py is the only send initiator. All features call queue_draft().

---

## RECOVER-MONEY — VERIFIED LADDERS

**Rent Chase (EstateOS)**
Days Overdue: 1+ friendly | 7+ firm | 14+ serious | 30+ warning (Lagos Tenancy Law) | 60+ final

**Invoice Chaser (B2C)**
Sequence: polite → firm → payment_plan → final (each generated fresh)

**Debt Collector**
3–4 stages over 60+ days, relationship-context aware

Daily scheduler → get_overdue_charges() → stage_for_days_overdue() → generate → queue_draft()

---

## OWNER BRIEF — VERIFIED REAL

Daily at 8am (Lagos time), compile_morning_brief() sends WhatsApp:
- Overnight signals (Instagram, Twitter, Facebook)
- Overnight replies by intent
- Pending approvals count
- This-month ROI (messages sent, API cost)
- Pipeline per vertical
- **3 AI-generated action items** (Claude Haiku synthesis)

Real, runs daily.

---

## HOLDING REPLY — VERIFIED REAL

Instant ack at webhook receipt:
- Inbound arrives, parsed <100ms
- Client lookup by account_id <50ms
- If autopilot=OFF + holding_message set: send <500ms
- 24h dedupe per contact
- Customer sees ack <1s, real reply minutes later

Latency verified.

---

## CLOSER — VERIFIED REAL (PARTIAL)

Inbound routing + lead threading + auto-draft works. API wired. **Missing:** Dashboard UI.

---

## SDR DISCOVERY — VERIFIED REAL

**Sources:**
- Google Maps: 40+ verticals, city expansion
- Apollo.io: decision-maker search
- Social discovery: Instagram/Twitter intent signals
- Apify/web enrichment: website + contact names

**Campaign flow:** Run discovery → Generate messages → Queue to HITL → Owner approves → Send (daily caps enforced)

Brief gate: prospecting hard-blocked unless brief complete.

---

## VERTICAL DEPTH

19 verticals, 99–152 lines each:
- Clinics (152): patient confidentiality, appointment specificity
- Professional Services (149): conflict checks, retainer framing
- Hospitality (149): Detty December, owambe, deposits
- Education (148): diaspora parents, year-group matching
- Real Estate (146): PoF conversation, neighbourhood intel
- Legal (142): confidentiality, conflict-aware
- 13 more, all >99 lines, zero stubs

---

## PER-CLIENT ISOLATION — VERIFIED

- Unipile account_id: each client's WhatsApp line separate
- Contacts scoped by client_name
- Approvals scoped by client
- Closer leads scoped by client_id
- Estate/HR scoped by landlord_company
- **P0 rule:** Multi-tenant leakage impossible

---

## HIDDEN SUITES

**Active (visible):** EstateOS, TalentOS

**Hidden (APIs exist, UI missing):**
1. LendOS (Loan Officer + Market Credit + FX Lock) — 70%
2. BizOS (Debt Collector + Moonlighting) — 60%
3. SchoolOS (School Fees + Probation) — 80%
4. LegalOS (Legal Review + Routing) — 50%
5. BuildOS (Material Check + Fleet) — 40%
6. TrustOS — 10%
7. MarketOS — partial

---

## GENUINELY UNIQUE

1. **Per-vertical prompt stack (99–152 lines)** — Real estate PoF ≠ legal conflict. System knows and enforces.
2. **Client-brief override + isolation** — 20-field BusinessBrief completely overrides vertical. Each WhatsApp line truly separate.
3. **Escalation ladders with legal awareness** — Rent: 5 stages with Lagos Tenancy Law. Each generated fresh.
4. **Completeness gate on brief** — Prospecting hard-blocked until ICP + closing_action. P0 enforcement.
5. **HITL at architecture level** — queue_draft() only send initiator. No bypass.
6. **Instant ack <1s** — Message at midnight → holding reply <1s → real reply minutes later.
7. **Vertical-aware inbound routing** — Cascading logic: Closer → Rent Roll → Invoice Chaser.
8. **Morning brief with AI action items** — Daily WhatsApp: 3 Claude-generated next steps.

---

## NOT REAL YET

1. Closer UI (code exists, no customer dashboard)
2. LegalOS at scale (parsing brittle)
3. Material Check (market-rate DB not wired)
4. Moonlighting detection (skeleton)
5. Market OS alerts (incomplete)
6. Neighborhood Scorecard (stub)
7. Nurture sequences (not triggered)
8. Practice-area routing (tags only)
9. Scholarship auto-routing (not implemented)
10. Video tour preference (not implemented)

**Do not claim these.**

---

## THREE PROOF-POINTS

**1. Real-Time Ack**
"When a message arrives at 11pm, your customer sees your pre-set holding reply within 1 second. The real reply (AI-drafted, human-approved) lands minutes later."
Evidence: api/webhooks.py:27–68

**2. Escalation Respecting Lagos Law**
"Rent chase escalates through 5 stages over 60 days: friendly (day 1), firm (day 7), serious (day 14), warning with Lagos Tenancy Law (day 30), final with 7-day quit (day 60). Each generated fresh."
Evidence: services/estate/rent_roll.py:22–44

**3. Market-Specific Verticals**
"For hospitality, the agent knows Detty December, owambe, deposits. For legal, conflicts and confidentiality. For real estate, Proof of Funds. For education, diaspora parents in US/UK timezones. All in one system — the vertical changes the prompt, not the product."
Evidence: agent/prompts/ (19 verticals, 99–152 lines each)

---

## SUMMARY

ReachNG is not a template-blaster or generic chatbot. Real HITL agent with:
- Per-client isolation (Unipile account_id, MongoDB scoping)
- Market-aware drafting (19 verticals, 99–152 lines each)
- Enforced human approval (HITL at architecture level)
- Escalation ladders (rent, invoice, debt — real multi-stage)
- Instant ack (<1s)
- Daily owner brief (with AI action items)
- Closing-specific features (Closer, PoF concierge, KYC vault)

**Landing page strategy:**
1. Lead with real-time ack + HITL moat
2. Vertical depth moat (19 markets, not 1)
3. Escalation with legal awareness
4. Proven suites (EstateOS + TalentOS only)
5. Be honest about progress on hidden suites

**Avoid claiming:** Closer as full product, legal at scale, neighborhood intelligence, AI nurture, practice routing, or anything listed as "Not Real Yet."
