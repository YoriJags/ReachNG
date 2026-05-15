# ReachNG — Active Plan

**Single source of truth for what's being built right now.** If it's not on this page, it doesn't exist.

Queued work waiting to be promoted into a phase: see [BACKLOG.md](./BACKLOG.md).

Last updated: 2026-05-15

---

## North Star

Land first paying Lagos client on **ReachNG Closer (Real Estate)** within 30 days. Everything on this page either serves that goal or keeps the acquisition funnel running.

---

## Current state — what's live

- [x] Public SDR funnel (Google Maps + Apollo + Unipile WhatsApp discovery) — feeds our own pipeline
- [x] HITL draft queue — every outbound message human-approved before send
- [x] Admin Control Tower dashboard at `/admin` (session auth)
- [x] Client portal at `/portal/{token}` (token auth, one client = one token, two sub-portals)
- [x] Demo Sandbox — one-click seed for EstateOS + TalentOS demo data
- [x] SDR prompts pivoted: real estate leads with Closer, recruitment pitches back-office
- [x] External branding rule — outreach says "ReachNG", never TalentOS/EstateOS
- [x] Placeholder leak fixed — no more `[Partner Name]` in sent emails
- [x] Recruitment-agency hard rule — never pitch sourcing to staffing firms
- [x] Overview stat cards clickable (Pipeline / Replies / Clients)
- [x] TalentOS back-office built: payroll, PAYE/CRA/PENCOM/NHF, leave, attendance, probation, policy oracle, candidate screener, offboarding
- [x] EstateOS built (now demoted to Closer upsells): KYC vault, PoF screener, scorecard, lawyer bundle, rent chase

## Now — Phase 1: Closer Lead Intake *(1–2 days)*

Real estate clients only. Everything below scoped to `vertical=real_estate` clients.

- [x] Extend `clients` schema with `closer_brief` object (product, ICP, qualifying questions, red flags, closing action, tone, pricing rules, never-say list)
- [x] Create `closer_leads` collection (client_id, source, contact, vertical, stage, thread, handover timestamp)
- [x] Intake channel A (STUB): `POST /api/v1/closer/leads/email` parser ready — real MX forwarder blocked on SPF/DKIM for `reachng.ng`
- [x] Intake channel B: shared WhatsApp line per client via Unipile → auto-create lead on new inbound (gated by `closer_enabled=True`)
- [x] Intake channel C: webhook `POST /api/v1/closer/leads/{token}` for CRM/form integration
- [x] Client portal — "Closer Inbox" tab: list of leads + stage + thread view
- [x] Admin dashboard — per-client Closer tab: brief editor + lead inbox

## Now — Phase 1.4: Apify Enrichment Layer *(1 day, blocks outreach quality)*

Lifts every lead from "name + phone" to "decision-maker + signal" before it hits the HITL queue. Used by our own SDR funnel now, inherited by BYO Leads in 1.5.
Apollo is inactive/expensive — Apify replaces it entirely. `tools/apollo_discovery.py` kept for reference; scheduler disabled.

- [x] `tools/apify_enrich.py` — `enrich_lead(domain, linkedin_company_url) -> {decision_maker, title, linkedin_url, email, phone, recent_signal, enriched_at}`; exponential backoff; structlog without PII
- [x] `tools/apify_discovery.py` — Google Search → domain → enrich pipeline; replaces Apollo in campaign runner
- [x] `campaigns/base.py` — swapped `discover_apollo_leads` → `discover_apify_leads`; all variable/log references updated
- [x] `tools/__init__.py` — exports `discover_apify_leads`; Apollo kept but noted deprecated
- [x] `APIFY_API_TOKEN` reactivated in Railway env (2026-05-10)
- [x] Admin Control Tower — `enrichment.decision_maker` + `enrichment.title` surfaced (operations_flow + dashboard lead detail)
- [x] HITL drafter reads `enrichment.decision_maker` for personalization (2026-05-10)

## Shipped — Phase 1.5: Business Brief + BYO Leads *(complete)*

Module 0 (`services/brief/*` + `api/brief.py` + portal "Business Brief" tab + admin sub-tab + drafters routed through `assemble_context()`) and Module 1 (NDPR gate + `lead_imports` audit + portal "Lead Lists" tab + per-client guardrails + sequences via `services/sequences/engine.py`) all shipped. Wired across `api/portal.py`, `campaigns/b2c.py`, `portal_estate.html`.

## Now — Tier-0 Engine: T0.4 Outcome Learning Loop *(foundation shipped 2026-05-15)*

Source of truth: BACKLOG.md → "P0 — Tier-0 Engine sprint" → T0.4. Every approved draft tagged with `outcome_id`; positive customer reply → `win`, silence >7d or explicit no → `miss`. Weekly Sunday 23:00 Lagos job: Claude reviews wins vs misses per client and emits a `prompt_addendum` auto-merged into the client's BusinessBrief override. Agent improves per-client every week without manual tuning.

- [x] `outcomes` Mongo collection — indexed by `(client_id, status, created_at)`, unique sparse on `approval_id` for idempotency
- [x] `services/outcome_learning.py` — `open_outcome_from_approval()` / `tag_from_inbound()` / `sweep_silence_to_miss()` / `distil_for_client()` / `distil_all_clients()` / `get_addendum_for_client()`
- [x] Hook `tools/hitl.py::approve_draft` + `edit_draft` to open the outcome doc (best-effort, never blocks send)
- [x] Webhook inbound: T0.2 classifier intent → `tag_from_inbound()` resolves open outcomes to win/miss
- [x] Scheduler: nightly 02:00 Lagos `outcome_silence_sweep` — auto-miss after 7d silence
- [x] Scheduler: weekly Sun 23:00 Lagos `outcome_weekly_distil` — Haiku per-client → `clients.prompt_addendum`
- [x] `agent/brain.py` + `services/closer/brain.py` — inject `prompt_addendum` as "WEEKLY COACHING" block in system prompt
- [ ] Portal: "Agent Learning" card — last addendum summary + last refresh timestamp *(tomorrow)*
- [ ] Admin: per-client view of recent wins/misses + addendum history *(tomorrow)*

## Next — Tier-0 Engine: T0.5 Proactive Intelligence *(~4 days)*

5 starter behaviours per BACKLOG.md (stale revival, festival timing, birthday nudges, capacity nudges, booking reminders). Each = scheduler job → HITL drafts.

## Later — Phase 2: Closer Brain *(2–3 days)*

- [ ] New prompt tree: `agent/prompts/closer/real_estate.txt` — loads client's `closer_brief` + real estate vertical primer
- [ ] Functions in `agent/brain.py`: `draft_qualifier()`, `draft_objection_handler()`, `draft_booking()`, `draft_followup()`, `classify_stage()`
- [ ] Stage machine: new → qualifying → ready → booked → lost (+ stalled)
- [ ] Auto-trigger: every inbound reply on closer_leads → AI drafts next move → queues to HITL
- [ ] Client dashboard: "Drafts to approve" view — approve/edit/reject → send via client's Unipile number
- [ ] Handover card generator — summary (budget, timeline, contact, objections handled, next step) pushed to client's phone when stage = ready

## Next — Phase 3: Legal Pack *(1 day to draft, lawyer review required)*

Two tiers — Closer clients get full stack, TalentOS clients get lighter SaaS terms.

- [ ] Draft **MSA** (Master Service Agreement) — scope, fees, SLA, term, termination, liability cap (12 months fees paid)
- [ ] Draft **DPA** (Data Processing Agreement) — NDPR-aligned, sub-processor list, breach notice (72h), delete-on-termination
- [ ] Draft **Mutual NDA** — their leads + pricing + strategy confidential
- [ ] Draft **Closer Addendum** — lead ownership, lawful-basis attestation, no cross-client data use, HITL responsibility shift
- [ ] In-app signup consent checkboxes enforcing the above
- [ ] `source_consent` field on every lead record
- [ ] Audit log CSV export per client
- [ ] Self-serve "revoke + hard-delete" button (30-day purge job)
- [ ] **Send all four docs to Lagos lawyer for review** — blocker before first real client signs

## Next — Phase 4: Handover UI polish *(0.5 day)*

- [ ] One-tap "Hand Over" button on qualified leads in client portal
- [ ] WhatsApp + dashboard notification when handover triggered
- [ ] Lead timeline view — every message, every approval, every state change

## Later — Phase 5: Voice Operator *(3–5 days, after first paying Closer client)*

- [ ] Pick stack: Vapi vs. Retell AI vs. LiveKit + Twilio
- [ ] ElevenLabs Nigerian-English voice preset
- [ ] Inbound call forwarding → our agent answers, qualifies, books
- [ ] Outbound click-to-call from dashboard
- [ ] Every call recorded + transcribed + summarised into lead thread
- [ ] AI identifies as AI in opening (regulatory), opt-out honored mid-call

## Running forever (never turned off)

- [ ] SDR funnel — our own client acquisition, two campaigns (real_estate → Closer pitch, recruitment → back-office pitch)
- [ ] HITL draft queue — non-negotiable for every outbound
- [ ] Client portal + Control Tower dashboard
- [ ] Unipile WhatsApp integration per client
- [ ] Google Maps + Apollo discovery pipelines

## Deferred — do not touch until triggered

| Item | Trigger to unlock |
|---|---|
| **AgriOS** — B2B match (farms ↔ buyers) | After Closer has 3+ paying clients |
| **BuildOS**, **LegalOS**, **LuxuryOS**, **LendOS**, **SchoolOS**, **ClinicOS**, other suites | After Closer + TalentOS each have 3+ paying clients |
| Float Optimizer UI | Archive — hide from dashboard |
| Livestream / rating features | Belongs to Viibe project, not ReachNG |
| Custom builds per client | Only when client asks and pays setup fee |

## Pricing (proposed — finalise with first pilot)

- **ReachNG Closer (Real Estate)**: ₦100K setup + ₦150K–₦400K/mo retainer + ₦5K–₦15K per qualified viewing (or 3–5% commission on closed deals for luxury tier)
- **ReachNG TalentOS (HR)**: ₦50K setup + ₦50K–₦200K/mo retainer (tiered by staff count)

## Blockers / open questions

- [ ] Lawyer review of the legal pack — who? budget?
- [ ] Dedicated WhatsApp numbers via Unipile — cost per client?
- [ ] `leads-{token}@reachng.ng` catch-all — SPF/DKIM on reachng.ng domain needed

## Rules (copied here so you see them every time)

1. Do what's on this plan. Nothing more.
2. Every outbound message routes through `tools/hitl.py::queue_draft()` — no exceptions.
3. We never hold client funds.
4. External brand = ReachNG. Suite names (EstateOS/TalentOS) are internal only.
5. No PII in structlog output.
6. Root-cause every bug. No `--no-verify`, no temp fixes.
