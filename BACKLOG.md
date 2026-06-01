# ReachNG — Backlog

**Queue of work not yet in PLAN.md / SPRINT.md.** When a sprint or phase finishes, pull the next P0 item from here into the active board.

PLAN.md = active phases. SPRINT.md = active sprints. BACKLOG.md = queued. Promote items, don't duplicate them.

Last updated: 2026-06-01 (reconciled after magic-potion + alignment pass)

---

## ✅ Shipped since last sweep (2026-06-01 — magic-potion + alignment pass)

Commits `301c369` (pricing/channel alignment), `8261422` (features), `49c26db` (UI wiring + polish).

**New "cash control room" surfaces — the wedge:**
- **Money Leak Report** — `services/money_leak.py` + `/portal/{token}/money-leak`. Composes confirmed-owed + asked-price-no-quote + ghosted "I'll pay" promises + silent inbound into one ₦ figure. Reframes EYO from "AI replies" → "cash recovery / control room."
- **Revenue Rescue Mode** — `/portal/{token}/revenue-rescue` + portal card; "wake this money up" reuses the HITL-forced `/run-resurrection`.
- **Competitor Speed Watch** — `services/speed_watch.py` + `/portal/{token}/speed-watch` + portal card. Real median first-response time vs category benchmark (percentile labelled estimate).

**Enhancements to already-shipped engines:**
- **Instant Learning Card** — edit-approve returns "EYO learned: …"; toasts in the dashboard (`services/learning_card.py`).
- **Autopilot Readiness breakdown** — 4 dimensions (tone / price / escalation / payment) in the portal readiness card; "still learning" when sample thin.
- **Vault next-best-action** — per-customer NBA line in the dossier.
- **Owner Voice `rescue_followup`** — "follow up everyone who asked price" surfaces targets + links to Revenue Rescue (no auto-send; HITL preserved).
- **"What you'd have missed" brief** — counterfactual section in the morning Owner Brief.
- **First-24h-Win** — onboarding go-live reward panel (`/onboard/first-win`).
- **Concierge intake** — paste-materials box on onboarding step 1 (`/concierge` → KB).

**Repo hygiene:** one canonical pricing ladder (Solo/Team/Empire ₦60/120/250) across README/OPERATIONS/PRODUCTS/PRICING/signup; Unipile-primary channel decision; INVESTOR.md re-run at live pricing; `GOOGLE_MAPS_API_KEY` made optional; Resend webhook fail-closed in prod; og:url forced https; `tests/test_magic_features.py` added (bad-token isolation, empty-data, composition math, rescue dedup, resurrection-stays-HITL). Full suite: 18 passed.

---

## P0 — Actionable now (top of queue)

> Re-ranked 2026-06-01: the Money Leak wedge now ships, so the next moves are (a) cheap close-outs, then (b) the proactive moat. The single biggest structural moat remains **A6 Open Banking** (P1) — gated on first paid client + Mono/Okra approval.

Pull these into PLAN.md or SPRINT.md one at a time. Ordered by ship-value.

- [x] ~~**T0.4 close-out — Admin per-client wins/misses dashboard**~~ — confirmed already shipped 2026-06-01 (backlog was stale). `templates/dashboard.html` has the full "Agent Learning — outcomes engine" section: `loadAgentLearning()` renders the cross-client wins/misses table, `openAgentLearning()` shows the active `prompt_addendum` + last-15 outcomes per client. Lazy-loads on dashboard render. Endpoints: `/api/v1/admin/agent-learning` (summary) + `/{client_id}` (detail).
- [x] ~~**Sentry error tracking + webhook-failure tail**~~ — wired 2026-06-01 (`tools/observability.py` + `init_sentry()` in `main.py` + `sentry-sdk[fastapi]` in requirements). PII-scrubbed (phone/email) via `before_send`; `send_default_pii=False`; request body/cookies/auth headers dropped. No-op until `SENTRY_DSN` set. `capture_message()` helper wired into the Resend webhook failure paths (the "tail"). **Only remaining: Yori sets `SENTRY_DSN` in Railway** + (dashboard-side, not code) Sentry→Slack alert rule + BetterStack uptime monitors per integration. Adopt the `_tail()` pattern in `api/webhooks.py` (Meta/Unipile) when desired.
- [ ] **T0.5 Proactive Intelligence — remaining behaviours** *(~2 days)* — The "agent acts without being asked" moat. **Shipped 2026-06-01:** festival timing (`services/proactive/festivals.py` + `__init__.run_proactive_sweep` + daily 06:30 scheduler job — festive-window re-engagement of dormant customers, capped + deduped via `proactive_log`, routed through HITL). **Stale-lead revival** already ships via Revenue Rescue. **Remaining:** birthday nudges (reads `client_memory` date facts), capacity nudges (hospitality quiet-night fill), booking/appointment reminders. Add each as a behaviour in `services/proactive/` + fold into the existing sweep.
- [x] ~~**T0.2.6 Custom-named Engine**~~ — confirmed already shipped during sweep (api/clients.py + api/portal.py POST /agent-name + portal Settings UI with live preview + agent/brain.py::_agent_identity_block prompt injection + services/closer/brain.py wired). Marked done 2026-05-25.
- [x] ~~**HITL bulk-approve + draft regeneration**~~ — shipped 2026-05-25. `POST /api/v1/approvals/approve-all` and `/skip-all` now accept `client` + `confidence` query params (filter to a single tenant or only high-confidence drafts). New `POST /api/v1/approvals/{id}/regenerate?style=shorter|warmer|firmer|more_specific` does a single Haiku rewrite in-place (~₦2/call, recomputes risk against new text). Dashboard renders per-draft `↺ shorter / ↺ warmer / ↺ firmer` buttons + "✓ Approve safe only" bulk button on the approve-all bar.
- [x] ~~**HITL draft confidence score**~~ — shipped 2026-05-25. Deterministic rule-based scorer in `services/draft_risk.py::score_draft()` — no LLM call, ~0ms latency, ₦0 cost. Persists `{confidence: high|medium|low, score: 0-100, tags: [str]}` on each `pending_approvals` doc via `tools/hitl.queue_draft`. Dashboard renders color-coded badge (green/amber/red) above each approval card with score + top 3 tags. Tags include `placeholder_leak`, `escalated`, `angry_on_fire`, `refund_topic`, `legal_mentioned`, `money_quoted`, `over_apologetic`, etc.

---

## P0 — Process items (not buildable — execute live)

- [ ] **First paid client → public case study** *(~1 week post-pilot)* — One screenshot, one pull-quote, one number. Lives at `/case-studies/[client]`. Becomes the social-proof anchor.
- [ ] **Founder authority cadence** *(ongoing, 20 min/day)* — Yori posts 3×/week on Twitter + LinkedIn. Theme: "what the agent did this week" with screenshots. Reply-guy on Iyin@Paystack, Tunde@Bumpa, Olu@Flutterwave threads.
- [ ] **Live test with 5 Lagos prospects** — Send one-line WhatsApp asking "what is this and who is it for?" to 2 luxury RE + 2 legal + 1 hospo. Track 5-second-test pass rate + waitlist conversion.

---

## P1 — Pre-pilot operational gaps

Things that aren't features but matter when first 5 pilots want to go live.

- [x] ~~**Auto-enforce WhatsApp warmup ramp at code level**~~ — shipped 2026-05-25. `tools/account_guard.WARMUP_SCHEDULE` tightened to the conservative Meta-recommended 10/25/50 over weeks 1/2/3 (was 50/100). `api/clients.py` now seeds `outreach_started_at` at client creation in `$setOnInsert` so the ramp ticks from pairing day, not first send.
- [x] ~~**Onboarding wizard**~~ — shipped (`api/onboarding.py` + `templates/portal/onboard.html`): 7 steps Business Basics → Voice & Tone → Offer & Pricing → Lead Qualification → Approval Rules → Test EYO → Go-Live, at `/portal/{token}/onboard`. 2026-06-01 additions: First-24h-Win reward panel on go-live (`/onboard/first-win`) + concierge paste-materials box on step 1 (`/onboard`/`/concierge`).
- [ ] **Pass-2 guided demo: per-vertical** *(~3 hrs, build when demand signal arrives)* — `/portal/demo/real_estate` (Victoria Island PoF storyline) + `/portal/demo/professional_services` (Greenview Fri-6pm storyline). Education + clinics + small_business deferred until signups arrive.
- [ ] **Portal token rotation** *(½ day)* — `client.portal_token_rotated_at` + "regenerate token" button. Use case: client leaves a partner who had the URL.
- [ ] **Audit log for client_doc edits** *(½ day)* — Every `clients` collection update writes to `client_audit_log` with who/what/when.
- [ ] **Empty-state copy on every dashboard tab** *(½ day)* — Helpful next-step copy when a client has 0 leads / 0 invoices / etc.

---

## P1 — Cost & cadence levers

- [ ] **Landing page nurture drip** *(~1 day, defer until 5 pilot applications arrive)* — 3-email warm sequence after waitlist signup (Day 0 confirm done · Day 2 vertical-specific deep-dive · Day 5 case study + soft CTA). `services/nurture/landing_drip.py`. Resend confirmed working.
- [ ] **Anthropic + Mongo + Railway budget alerts** *(½ day)* — Monthly spend monitoring in `tools/system_sweep.py`. Flag in 7am brief if Anthropic > $20/mo, Mongo connections > 400, Railway memory > 400MB sustained.
- [ ] **Referral mechanic** *(1 day)* — ₦25k credit per referred sign-up. Schema: `referral_code` per client + Paystack discount logic.
- [ ] **TaxNudge** *(~3 days, HIGH commercial pull)* — PDF bank statement → Haiku categorisation → VAT/CIT estimate per 2024 Nigerian Tax Reform Acts. `pdfplumber` already in stack.
- [ ] **PayNudge** *(1 day)* — Google Sheets source + Paystack pay-link on existing `services/debt_collector/`.

---

## P1 — Trigger-gated infra (do NOT build before signal fires)

| Item | Trigger | Effort |
|---|---|---|
| Redis caching (Upstash) — vertical prompts, memory reads, account status | Haiku spend > ₦50k/mo OR 10+ paid clients | ~1 day |
| Background queue (RQ + Redis) — move OCR/voice off APScheduler | 25+ active clients OR rate-limit hits | ~3 days |
| Mongo M0 → M10 migration | 10–12 paid clients | ~half day |
| Materialised dashboard snapshots — nightly aggregates | 25+ active clients | ~1 day |
| HITL audit trail surfaced in portal | First legal/clinic client signs | ~1 day |
| API-key rotation pool (Anthropic + Whisper + Vision) | ~250 active clients OR first 429 burst | ~2 days |
| Graduated Autopilot trust | Any client crosses 200+ drafts/wk | ~3 days |
| Resend inbound webhook (replaces IMAP polling) | Reply volume > 50/day | ~2 hrs |
| Self-host Whisper | Voice transcription cost > ₦20k/mo | ~1 day |

---

## P1 — Year-1 product surfaces (build after first paid client validates the core)

Each gated by demand signal, not calendar.

- [ ] **`/api/v1/draft-and-queue` — Infrastructure API tier** *(2 days)* — Sell WhatsApp rail to businesses with their own AI (Lagos fintechs running Gemini etc). New flat-volume pricing tier. **Trigger:** 3+ paying retainer clients.
- [ ] **EYO Across (Instagram DM + Email channels)** *(~3 weeks)* — Same brain, IG DM via Unipile, Gmail via Google API. +₦40k/mo per channel. Doubles ARPU on Growth.
- [ ] **EYO Voice Operator** *(~3-5 days alpha, Premium add-on)* — ElevenLabs voice clone + LiveKit pipeline + 5-second HITL veto window before bookings confirm. **Trigger:** 3+ Premium clients live.
- [ ] **Diaspora outbound landing** *(~1 week)* — UK/US/Canada Nigerians use EYO for Lagos comms. £50/mo Stripe Checkout. USD-paying customer mix.
- [ ] **Outreach dashboard redesign** *(~2 days, sequence carefully)* — Already partially done via Recover/Activate/Clients/System tabs. Close-out includes Control Tower per-client KPI strip + `/admin/prospect-os` surfacing. Do AFTER Owner Brief upgrade + Lead Resurrection are battle-tested.

---

## P1 — Tech/AI engine batch (do these after first paid client lives 30 days)

Survivors of the Emergent 22-idea triage. See `memory/project_reachng_emergent_tech_review.md` for the 8 dumped + 4 already-covered.

- [ ] **A1. Agentic Actions framework** *(~2 weeks)* — Extend HITL queue to support stateful actions, not just outbound drafts. V1: send Paystack payment link sized to booking · hold a slot for 10 min · schedule follow-up · approve refund flow. **The moat that locks switching cost.**
- [ ] **A6. Open Banking integration (Mono / Okra)** *(~3 weeks)* — **THE BIGGEST SINGLE MOAT IN THE PLAYBOOK.** Listen for inbound transfers in real-time → owner gets "💰 ₦450k confirmed from Bola O." *before* the customer sends the screenshot. Receipt Catcher becomes the fallback path. **Trigger:** Mono/Okra account approved + first paid client lives 30 days.
- [ ] **A2. Voice-clone owner brief** *(~4 days, Premium-only)* — 90-second audio brief in the owner's cloned voice (ElevenLabs Multilingual v2). ~₦100/day/client cost, pass-through to Empire tier.
- [ ] **A5. NDPR / regulatory compliance dashboard** *(~4 weeks)* — Auto PII redaction in logs · "right to be forgotten" export · NDPR breach detection · per-approval audit trail in portal. Unlocks legal/clinic/fintech verticals.
- [ ] **A4. Synthetic customer testing suite** *(~3 weeks)* — Weekly synthetic Lagos personas DM every active EYO; probe for tone drift, price accuracy, fake-receipt recognition, language safe-switch breaks. First production CI/CD for an AI sales agent in Africa.
- [ ] **A3. Multi-agent reply orchestration** *(~3 weeks, Empire-only)* — Drafter writes → Critic scores → Fraud-checker scans receipts → Vertical-expert verifies playbook. ~3.5× current draft cost. Justifies the ₦250k Empire tier.
- [ ] **A8. Visual generation per vertical** *(~3 weeks per vertical)* — RE floor plans, hospitality menu cards, clinic before/after, legal case summaries. Gemini Nano Banana ~₦40/image. **Trigger:** vertical has 3+ paying clients.
- [ ] **A9. Fraud detection model (Lagos-specific receipts)** *(~6 weeks)* — Train on accumulated receipt dataset to detect Photoshopped GTB/Opay/Kuda screenshots. Productize as standalone API for Lagos fintechs (₦2/check). **Trigger:** monthly receipt volume > 5,000.
- [ ] **A7. EYO Mesh — federated cross-client insights** *(~4 weeks)* — Privacy-safe aggregates: "Restaurants like yours see 38% more bookings when X". Differential privacy + k-anonymity. **Trigger:** ≥20 paying clients.

---

## P1 — Pricing structure decision (postponed, gather data first)

- [ ] **T0.2.5 Usage Quota & Tiered Billing System** *(~3 days)* — Per-plan monthly caps, real-time anti-runaway rate limits, owner-opt-in overage billing, 80% warning WhatsApp, admin Billing dashboard with per-client margin %. Required before any meaningful scaling. Defer until 5 pilots produce real cost data.
- [ ] **T0.2.7 Feature Menu / A La Carte Pricing** *(~4-5 days)* — Modular menu instead of fixed tiers. Configurator at `/pricing`. Per-client `enabled_features` flags gating each cost-incurring call. Final pricing schedule needs T0.2.5 cost data first.
- [x] ~~**T0.3 Predictive co-pilot — chat with your agent**~~ — shipped (`services/copilot.py` + `api/copilot.py` + dashboard floating bubble/chat panel with 5 tools). Owner asks "Who hasn't replied in 5 days?" / "Summarise this week" → Haiku planner → deterministic Mongo queries → narrate.

---

## P2 — Polish / hardening (after first paid client)

- [ ] **Split `agent/brain.py`** — File is 770+ lines. Extract into `agent/drafters/` package: outreach, b2c, social, invoice, auto_reply, classifier.
- [ ] **Mobile-first review of client portal** — Verify portal.html renders cleanly at 375px. Most Lagos clients view on phone.
- [x] ~~**"Almost lost" widget on client portal**~~ — endpoint shipped 2026-05-25 (`GET /portal/almost-lost/{token}`). Portal surface now live too (2026-06-01): the Money Leak Report's "silent inbound" category surfaces messaged-but-never-replied conversations on `/portal/{token}/money-leak`.
- [x] ~~**ROI screenshot generator**~~ — shipped 2026-05-25. `services/roi_card.py::render_roi_card()` returns 1200×630 PNG; `GET /portal/share-card/{token}` serves it inline. Pulls live numbers from `services/scorecard.compute_scorecard`. Pillow-only, no new deps.
- [ ] **Integration test suite expansion** — At first paying client, expand beyond `tests/test_smoke.py`: HITL gate, webhook routes, holding reply dedupe, autopilot toggle, portal token auth.
- [ ] **Lead-signal-injection rules** — Each vertical prompt mandates referencing concrete signals from enrichment payload (Maps rating, decision_maker, place categories, IG handle).
- [ ] **Marketing site visual overhaul** *(~half day)* — Reference 11x.ai / Artisan.co / Landbase.com. Token-driven CSS so dashboard + portal can adopt incrementally.

---

## P3 — Pressure-tested feature ideas (build after first paying client)

From `project_reachng_feature_ideas_may26.md`. Each pressure-tested against the stack.

- [ ] **Ghost-Worker Attendance Auditor** (TalentOS + Government) — selfie + live location → Claude Vision face match + geofence check. Strong public-sector payroll-fraud fit.
- [ ] **Site-Pulse** (EstateOS) — foreman sends photo → Claude Vision analyses construction milestone → ReportLab Progress Certificate PDF.
- [ ] **VibeReview** (hospitality upsell) — APScheduler 2h after checkout → feedback request → sentiment → alert manager if negative + high-spender.
- [ ] **Title Ledger** (EstateOS) — WhatsApp agent for land title verification (C of O, Governor's Consent, Excision). Vault-first summary.

---

## P4 — Infra monitoring (wire into `tools/system_sweep.py`)

So the 7am brief flags scaling issues before they bite.

- [ ] MongoDB connection count — flag at >400
- [ ] Atlas storage estimate — flag at >400MB
- [ ] Railway memory (process RSS) — flag at >400MB sustained
- [ ] DDG error rate in last 24h
- [ ] Unipile delivery fail rate per client — flag at >5%

---

## P5 — Deferred / locked

- **LendOS** — full scope in `project_reachng_lendos_scope.md`. Don't touch until user explicitly says start.
- **Locker / Receipt / Roll Call / Shelf modules** — `project_reachng_future_modules.md`. Build only after unlock triggers fire.
- **LeanScrape Cloud + Enrich premium** — `leanscrape/` OSS shipped. Cloud + Enrich gated until OSS hits ~100 GitHub stars OR people ask for hosted version.
- **End-to-end opaque mode (browser-side WebLLM drafting)** — 12-month horizon, do NOT build now.
- **Self-hosted "Your Mongo, your keys" deployment** — Tier-1 firms pay ₦2-5M setup for data sovereignty. **Trigger:** one inbound asks for it.
- **EYO Concierge (B2C white-label)** — Year 2 only. Two-sided market.
- **Receipt-as-API for fintechs** — productize OCR as standalone API. **Trigger:** monthly receipt volume > 5,000.
- **`/api/v1/draft-and-queue` Infrastructure API tier** — see P1 above; gated until 3+ paying retainer clients.
- **ReachNG Scout v1** — substantially absorbed into existing tooling (`tools/discovery.py`, `tools/apify_enrich.py`, `services/lean_scraper.py`). Page extractor remaining piece tracked under P2.
- **Prospect OS internal SDR engine** — partly built via existing campaigns/base.py + lean_scraper.py + discovery.py. The 8-stage architectural rewrite is deferred until current funnel proves insufficient.

---

## How items get promoted

1. Active phase in PLAN.md or sprint completes → mark `[x]` and commit
2. Pull next P0 item from this file → write a new phase block in PLAN.md / SPRINT.md
3. Mark the line here as done with brief done-date + commit ref, OR delete

Don't let this file rot. If an item sits in P0 for 3+ weeks unreviewed, either commit to it or move it to P3 / P5.
