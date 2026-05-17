# ReachNG — Backlog

**Queue of work not yet in PLAN.md.** When a phase completes in PLAN.md, pull the next P0 item here into a new phase.

PLAN.md = active. BACKLOG.md = queued. Promote items, don't duplicate them.

Last updated: 2026-05-09 (after pressure test + SEO audit)

---

## P0 — "BURST HEAD" Launch Path (do this in order, total ~5 days)

The five things that turn ReachNG from "this works" into "bro, you have to see this." Sequenced. Do them in order — each unlocks the next.

- [x] ~~**1. Build public marketing site**~~ — shipped 2026-05-09 (build) + 2026-05-10 (north-star copy alignment). `templates/marketing/` (_base, landing, pricing, about, how_it_works, contact, vertical, signup, signup_success) + `api/marketing.py` (router, robots, sitemap, signup, Paystack webhook). 5 vertical landers via `services/marketing_content.py`. Schema.org, OG, Twitter cards, FAQ schema. **Domain still pending** — buy `reachng.ng` (or `.co`) and update canonical hosts.
- [x] ~~**2. Concrete 3-tier pricing**~~ — shipped 2026-05-09. Cash Desk Starter ₦80K / Growth ₦150K (+ 2% recovered) / Scale ₦300K (+ 3% recovered) + annual = 15% off. Pricing page has feature-delta matrix and pain-anchored cost-of-leakage table.
- [x] ~~**3. Self-serve `/signup` flow + Paystack first-month**~~ — shipped 2026-05-09. `/signup` page with plan picker + annual toggle, `POST /api/v1/signup` initialise, `POST /webhooks/paystack` HMAC-SHA512 verified, auto-creates client doc + portal token on `charge.success`. Pairing automation + welcome email template still TODO before first paid client.
- [ ] **4. First paid client → public case study** (process, ~1 week after first paid client) — One screenshot, one pull-quote, one number ("18% → 3% no-shows in 30 days"). Lives at `/case-studies/[client]`. Becomes the social-proof anchor. Post the screenshot on Twitter/LinkedIn the day it goes live.
- [ ] **5. Founder-public authority cadence** (process, ongoing 20 mins/day) — Yori posts 3×/week on Twitter + LinkedIn. Theme: "what the agent did this week" with screenshots. Reply-guy on threads from Iyin@Paystack, Tunde@Bumpa, Olu@Flutterwave. The Lagos AI-for-SME conversation is wide open; whoever talks loudest about it owns the category.

**Total: ~5 days of build + ongoing process. Once these five are real, ReachNG is "ready to burst head".**

---

## P0 — Next sprint (queued 2026-05-14, after landing rewrite ship)

Locked sequence — build in this order. Total ~17 days.

**User-locked priority (2026-05-14 EOD):** Receipt Catcher ships first per user direction. Order below is final.

- [x] ~~**1. Receipt Catcher**~~ — shipped 2026-05-14. `tools/inbound_media.py` (Meta + Unipile image download), `tools/receipt_vision.py` (Claude Haiku 4.5 vision → ReceiptData), `services/receipt_match.py` (cascade matcher → rent / invoice / fees / closer / unmatched + acknowledgement drafter + HITL queue). Image branch wired into `api/webhooks.py` with `skip_autodraft` so no duplicate Closer draft.

- [x] ~~**2. Client Memory Layer + Isolation Hardening**~~ — shipped 2026-05-14. `services/client_memory.py` (scope-locked store/fetch/extract + audit log + isolation self-test); auto-extraction wired in webhook inbound (`learn_from_inbound` after Closer intake); retrieval injected into `agent/brain.py::generate_b2c_message` and `services/closer/brain.py::draft_next_move`; `tests/test_isolation.py` (contract guards + synthetic cross-client probe + db self-test); nightly `_isolation_audit` job at 03:00 Lagos in `scheduler.py`, persists to `isolation_audits` collection. P0 rule: every memory op requires `(client_id, contact_phone)` — `MemoryScopeViolationError` on violation. **No UI yet** — admin/portal panel deferred (~1-2h polish add after #3).

- [x] ~~**3. Client AI Configurability — KB + Rules Engine**~~ — shipped 2026-05-15. `services/knowledge_base.py` (chunk + token-overlap retrieval, scope-locked) + `client_kb_docs` / `client_kb_chunks`; `services/client_rules.py` (CRUD + keyword/intent match + prompt-compile, scope-locked) + `client_rules`; `services/scenario_library.py` (prebuilt bundles for hospitality / real_estate / education / professional_services / small_business); `api/knowledge_base.py` + `api/client_rules.py` (admin + portal routes); auto-injection of memory + KB + rules into `agent/brain.py::generate_b2c_message` and `services/closer/brain.py::draft_next_move`; rule-triggered escalation stamps `escalation_flag` on the closer lead. **Portal UI**: new `/portal/{token}/configure` page with 4 tabs (KB / Rules / Scenarios / Sandbox), surfaced via "⚙ Configure agent" link on the main portal topbar. KBScopeViolationError / RulesScopeViolationError enforce client_id on every op.

- [x] ~~**4. Outcomes Engine**~~ — shipped 2026-05-15 across two commits. All 5 layers live: scorecard widget on portal, quality metrics + drift alarm, cohort stats endpoint, weekly digest scheduler (Mon 7am Lagos), milestone engine (13 milestones, branded HTML cards, auto-tweet drafter). Nightly snapshots at 03:30 / 04:00 / 04:15 / 04:30 Lagos.
  - **Layer A: Per-client Scorecard widget** (~1.5 days) — Live, real-time numbers in client portal + Control Tower: ₦ closed via ReachNG-handled conversations (Paystack-confirmed only, not just touched), ₦ recovered from chase ladders, bookings confirmed, **median response time before vs after** (the killer chart — usually hours → seconds), reply rate before vs after, hours saved (drafts × avg manual-typing time), cost per booking, cost per ₦ recovered. One-tap branded PDF export. Files: new `services/scorecard.py`, new `api/scorecard.py` (`GET /api/v1/scorecard/{client_id}` + `GET /api/v1/scorecard/{client_id}/pdf`), widget on `templates/portal.html` and `templates/dashboard.html`. Materialised nightly via scheduler from raw events (drafts, approvals, paystack_events, chased_invoices, estate_rent_ledger, sf_students, contacts).
  - **Layer B: Quality Metrics dashboard** (~0.5 day) — Approval rate (% drafts approved unedited — measures voice match), edit distance (avg chars changed before send — draft fidelity), skip rate (relevance), time-to-approve (owner trust), customer reply rate to drafts (conversion power). Per-client + per-vertical breakdown. **Drift alarm**: approval rate dropping >15% triggers operator alert. Surfaces on Control Tower.
  - **Layer C: Cohort Rollups + landing-page social proof** (~0.5 day) — Anonymised platform-wide aggregates refreshed nightly. New `/api/v1/cohort-stats` endpoint. Render live tiles on landing page (replaces static "Why it works" copy with rolling numbers): *"₦XM closed via ReachNG this week / N businesses on the platform / X seconds median response / N hours of typing saved this month"*. Becomes auto-updating social proof and investor-deck content.
  - **Layer D: Weekly Owner digest** (~1 day) — Every Monday 7am Lagos time, WhatsApp + email digest to each client owner: last-7-days numbers, top wins, slowest chase, "your agent saved you N hours this week." Auto-drafted, hits HITL when content needs tuning. Builds the share-worthy moment.
  - **Layer E: Milestone Engine + auto-tweet drafter** (~0.5 day) — Scheduler watches per-client KPIs for milestones (first ₦1M closed, 100th booking, 30-day anniversary, first 1000 drafts approved, etc.). On hit: generate a milestone card (screenshot-ready) + draft a celebratory tweet/LinkedIn post the owner can one-tap share, tagging @reachng. Most clients won't post. The 20% who do compound your reputation faster than any paid acquisition.

- [ ] **5. Lead Quality Scorer** (~1 day) — Combine enrichment signals (business size, Maps rating + review count, decision_maker presence, vertical fit, recent IG/Twitter pain signals, website freshness) into Hot/Warm/Cold verdict with reason. Reorder outreach queue. Saves Apify/Apollo spend on cold leads. Already shown on landing page. Files: new `tools/lead_scorer.py`, hook into `campaigns/base.py` queue sort, surface in dashboard contacts table.

- [ ] **6. Closer UI** (~1-2 days) — Backend + API exist (`services/closer/`); no operator dashboard. Add Closer tab to `templates/dashboard.html`: lead list w/ status (new/replied/qualifying/hot/closed), thread view, draft preview, approve/edit/skip, manual move-to-stage. Already implied on landing page.

- [ ] **7. Nurture Sequences trigger** (~1 day) — Code exists but never triggers. Add scheduler job to detect leads quiet for N days (configurable per stage), draft contextual revival message referencing last conversation, queue to HITL. Per-vertical timing. Already shown on landing page.

- [ ] **8. Pricing Settings panel** (~1.5 hours) — Mongo `platform_settings.pricing` doc with three plan amounts. Read from doc in `api/marketing.py::PLAN_PRICING` (fallback to defaults). Edit inline from dashboard Control Tower → Settings tab. Audit log on each change. Killer for testing price points without a deploy.

## ✅ Railway deploy — green (2026-05-16)

The defensive `_safe()` wrap in the lifespan fixed it. All 33 ensure_*_indexes calls log `startup_ok` on boot. Application startup complete. `GET /health → 200 OK`. www.reachng.ng is live with all latest work (HBR + WhatsApp Nigeria research anchors, trimmed 8-section landing, premium positioning, lean_scraper internal engine).

---

## P0 — LeanScrape product family (queued 2026-05-17)

**Three-product ladder. ReachNG is the internal customer of every layer at cost.**

- [x] ~~**1. leanscrape OSS library**~~ — shipped 2026-05-17 at `c:/VIIBE/leanscrape/`. MIT-licensed Python package. 3-tier fetcher (httpx → curl_cffi → Playwright), multi-LLM (Claude/GPT-4o-mini/Gemini), SqliteCache, ProxyPool, schema-driven extraction. 1,394 lines. Not yet pushed to GitHub — user does the `git init` + `gh repo create`. PyPI publish blocked until first paid client (focus on ReachNG revenue first).

- [ ] **2. leanscrape Cloud (hosted SaaS, private repo)** (~1 week) — When OSS hits ~100 GitHub stars OR people start opening issues asking for hosted version. FastAPI service at `api.leanscrape.com`. API key auth, Paystack/Stripe metered billing, managed Playwright cluster + residential proxy pool + shared cache. Tiers: Starter $29/mo (1K scrapes), Pro $99/mo (10K scrapes). ReachNG uses internally at API-cost only (no markup).

- [ ] **3. Enrich premium add-on** (~3-4 days after Cloud ships) — Multi-source aggregation API. Input: domain or business name. Output: structured profile (decision-maker names, direct emails, phone numbers, social handles, tech stack, employee band, news mentions). Chained pipeline = website scrape + DDG search + LinkedIn-style lookup + email-pattern guessing + SMTP probe + tech-stack fingerprinting. Pricing: $0.05/enrich pay-as-you-go OR $499/mo for 15K. ReachNG uses internally for `tools/apify_enrich.py` replacement (kill remaining Apify spend).

**Strategic sequence: OSS drives adoption → traction signals when to build Cloud → Cloud customers signal which Enrich fields to ship first.** Don't build Cloud or Enrich before OSS has 100+ stars / 500+ PyPI installs — that's the YC playbook (Stripe / Supabase / Vercel all did this).

**ReachNG benefits regardless of external adoption**: lean_scraper engine already lives at `services/lean_scraper.py` and saves ~₦40K/month in Apify spend per active campaign.

---

## P0 — Tier-0 Engine sprint (queued 2026-05-15 — push ReachNG to world-class SDR)

Total ~12 days. Goal: move from "great Lagos SDR" → "addictive, impossible-to-leave." Each item compounds on the foundations already shipped (HITL, vertical playbooks, Memory, KB+Rules, Outcomes Engine).

- [x] ~~**T0.1 Voice-note inbound (Whisper)**~~ — shipped 2026-05-15. `tools/voice_whisper.py` + audio extractors in `tools/inbound_media.py` + audio branch in `api/webhooks.py`. Transcript flows into the existing drafter as if it were text. Operators see "🎤 Voice note transcript (Ns):" framing in HITL queue. STUB BELOW — Unipile + Meta webhooks deliver audio attachments → download via `tools/inbound_media.py` (already built) → POST to OpenAI Whisper API → transcript flows into existing draft pipeline as if it were text. Drafts cite "voice note transcript:" in the queue UI so the operator knows the source. Falls back gracefully if Whisper unavailable. Files: extend `tools/inbound_media.py` with `transcribe_audio()`, new `tools/voice_whisper.py`, webhook image-branch sibling for audio in `api/webhooks.py`. **Add OPENAI_API_KEY to Railway env + `config.py` settings field.**

- [x] ~~**T0.2 Emotional intelligence — tone-aware drafting**~~ — shipped 2026-05-15. `services/inbound_classifier.py` + injected into `agent/brain.py::handle_payment_reply` + `services/closer/brain.py::draft_next_move`. Classification persists on approval doc, escalation flag auto-set on angry/complaint/on_fire. Dashboard HITL queue renders emotion badge per draft. STUB BELOW —
  - sentiment ∈ {happy, neutral, frustrated, angry}
  - stage ∈ {first_touch, qualifying, negotiating, closing, post_sale, complaint}
  - urgency ∈ {idle, interested, hot, on_fire}

  Classifier is a single Haiku call (~200ms, ~₦2/call). Output injected into prompt as a `TONE GUIDANCE` block. Angry → auto-escalate, draft includes apology framing. Hot → brisk + confident, propose deposit. Drafts surface badges in HITL queue so owner sees the read at a glance. Files: new `services/inbound_classifier.py`, wire into `agent/brain.py` and `services/closer/brain.py` before draft generation.

- [ ] **T0.2.5 Usage Quota & Tiered Billing System** (~3 days) — Critical economics safeguard raised 2026-05-15.
  - **Layer 1 — per-plan monthly soft caps**: `clients.usage_limits` doc per feature (drafts, voice, receipts, classifier, memory_extract, sends). Plan defaults: Starter (1500 drafts / 200 voice / 200 receipts) → Growth (5000 / 800 / 1000) → Scale (unlimited / 3000 / unlimited). Overridable per client.
  - **Layer 2 — real-time rate limits (anti-runaway)**: ungated hard ceilings. Max 20 voice/10min, 50 vision/hr, 100 drafts/hr per client. Trip = log + alert + 30-min auto-pause.
  - **Layer 3 — owner-opt-in overage billing**: at-cap clients can toggle pay-as-you-go in portal (₦12/voice, ₦15/receipt, ₦6/draft) with a monthly ceiling cap. Overage billed via Paystack at month-end.
  - **Graceful degradation when over cap + no overage**: voice → "voice note received, please listen"; receipt → "screenshot received, match manually"; drafts → owner can send manually, no AI.
  - **80% warning WhatsApp**: owner gets a heads-up when any feature hits 80% of monthly cap, with one-tap upgrade and one-tap enable-overage.
  - **Collections**: `usage_events` (per-call, indexed by client_id+feature+ts), `usage_quotas` (current-month totals, hourly materialised), `usage_overage_consent`.
  - **Service**: `services/usage_meter.py` with `@meter(feature)` decorator. Pre-call: check quota + rate. Post-call: record event with actual cost. Single decorator wraps every cost-incurring call.
  - **Wire-up**: Whisper, Receipt vision, Inbound Classifier, Drafter, Memory extractor.
  - **Owner-facing UI**: usage bar chart per feature in portal, "enable overage" toggle with ceiling input, real-time ₦ spent this month.
  - **Admin Billing Dashboard** (added 2026-05-15): new dashboard tab `Billing` with per-client rows: client name · plan · ₦ revenue · ₦ API cost MTD · margin % · top feature by spend · "you're at risk" flag if margin<70%. Sort by margin asc. Drill-in shows per-feature breakdown + last 7 days trend. This is the operator's single-pane view to prevent any runaway client surprising us at month-end.
  - **ToS draft**: published rates per overage feature (₦12 voice / ₦15 receipt / ₦6 draft), monthly ceiling mechanism, soft-cap → graceful-degrade → overage path explained in plain English. Linked from signup flow + portal.
  - **Files**: new `services/usage_meter.py`, new `api/usage.py`, hooks in `tools/voice_whisper.py` + `tools/receipt_vision.py` + `services/inbound_classifier.py` + `agent/brain.py` + `services/client_memory.py`, portal usage tab, dashboard `Billing` tab, ToS markdown at `templates/marketing/terms.html`.

- [ ] **T0.2.7 Feature Menu / A La Carte Pricing** (~4-5 days) — Raised 2026-05-15. Move from fixed Starter/Growth/Scale tiers to a modular menu: customers compose their own plan from feature modules. Less decision fatigue → higher conversion + clearer perceived value.
  - **Pricing model** (proposed; tune via T0.2.5 cost data once live):
    - **Core Agent + HITL** (mandatory): ₦40K/mo — drafting, your-number sending, approval queue, vertical playbook, memory layer
    - **Voice Notes**: +₦20K/mo (includes 200 transcriptions, then overage)
    - **Receipt Catcher**: +₦15K/mo (includes 200 receipts, then overage)
    - **Closer Pipeline + Nurture**: +₦25K/mo
    - **KB + Rules Engine**: +₦20K/mo
    - **Cash Recovery suite** (rent/invoice/fees chase): +₦30K/mo
    - **Emotional Intelligence + Predictive Co-pilot**: +₦20K/mo
    - **Outcomes Engine + Branded PDF**: included
    - **Owner Brief + Weekly Digest**: included
    - **Multi-location coordination**: +₦40K/mo
    Worked example: Lagos restaurant ticks Core + Voice + Receipt + Closer = ₦100K/mo. Real-estate agency ticks Core + Receipt + Closer + KB + Cash Recovery = ₦130K/mo.
  - **Pricing page rewrite**: configurator at `/pricing` — checkbox each module, live total in naira, save quote, signup with chosen modules.
  - **Per-client feature flags**: `clients.enabled_features` array. Each cost-incurring call checks the flag before running (drafter, whisper, receipt, classifier, copilot). Feature off → graceful fallback ("voice transcription not enabled — voice note received").
  - **Module purchase / upgrade UI**: in portal, owner sees the menu, can enable a module mid-cycle (pro-rated billing via Paystack).
  - **Tiered "starter bundles"** kept as preset shortcuts ("Starter Bundle: Core + Voice + Closer = ₦85K — save ₦20K") so we don't lose the simplicity of presets entirely.
  - **Trade-off note**: full a la carte adds decision fatigue; bundle presets soften that. Final pricing schedule needs cost data from T0.2.5 (run 30 days first, tune from real usage).
  - **Files**: `api/marketing.py` PLAN_PRICING → module catalog, `templates/marketing/pricing.html` configurator, `api/clients.py` enabled_features on signup, gating decorator in `services/usage_meter.py`, portal module-purchase UI.

- [ ] **T0.2.6 Custom-named Engine ("you bought an employee — name them")** (~2 hours) — Raised 2026-05-15. If we're selling an agentic employee, owners should be able to name them. Like Artisan's "Ava," like Lindy. Make ReachNG personal. **Default agent name: `EYO`** (Yoruba — the Eyo Festival of Lagos. Uniquely Lagos, 3 letters, distinctive, easy to say globally.) Clients can rename in their portal.
  - **Schema**: `clients.agent_name` field, default `"EYO"`. Validated: 1-20 chars, alphanumeric + space.
  - **Prompt injection**: every drafter call adds `Your name is {agent_name}. When introducing yourself or signing off, use this name.` to the system prompt. Inject in `agent/brain.py` + `services/closer/brain.py` after the brief block.
  - **Surfaces**: HITL queue header (*"{agent_name} drafted this for {customer}"*), Owner Brief WhatsApp ("Morning, here's what {agent_name} did overnight"), Weekly Digest, Milestone messages, portal nav badge, scorecard PDF.
  - **Portal Settings UI**: one input field, save → persists, takes effect on next draft.
  - **Brand-safe defaults**: until owner sets a name, signs off generically ("the team at {business_name}"). Never says "ReachNG" in customer-facing messages.
  - **Files**: `clients` schema, `agent/brain.py` + `services/closer/brain.py` (prompt prefix), portal Settings tab, `services/weekly_digest.py` + `services/milestone_engine.py` (use agent_name in copy).

- [ ] **T0.3 Predictive co-pilot — chat with your agent** (~2 days) — Conversational owner→agent interface. Owner types into a chatbox in the dashboard:
  - "Who hasn't replied to me in 5 days?" → ranked list
  - "Show me leads I should call today" → 3 names + reasons
  - "Summarise this week" → plain English
  - "Draft a follow-up to that Banana Island buyer from last month" → ready draft

  Built on top of memory + scorecard + Mongo aggregations. Claude Haiku as the planner; the actual lookups are deterministic Mongo queries the agent assembles. Files: new `services/copilot.py` (intent → query plan → execute → narrate), new `api/copilot.py` with `POST /api/v1/copilot/ask`, dashboard sidebar widget.

- [ ] **T0.4 Outcome-learning loop** (~3 days) — The moat that compounds. Every approved draft tagged with unique outcome_id. When a positive customer reply lands (book / pay / yes), tag conversation as `win`. When silence > 7 days or explicit `no`, tag `miss`. Weekly job: per client, Claude reviews wins vs misses and emits a `prompt_addendum` — auto-merged into that client's BusinessBrief override. Effect: the agent writes better drafts every week per client without anyone tuning manually. Files: new `services/outcome_learning.py`, `outcomes` collection (one per draft), `prompt_addendum` field on `clients` doc, weekly cron Sunday 23:00 Lagos.

- [ ] **T0.5 Proactive intelligence engine** (~4 days, 5 starter behaviours) — The agent acts without being asked:
  1. **Stale-lead revival** — leads quiet 14+ days, top 5 surfaced daily with draft each
  2. **Festival timing** — Detty December, Sallah, Easter, Owambe season → vertical-specific campaign drafts a week before
  3. **Birthday / anniversary nudges** — agent reads memory for date facts, queues warm check-in on the day
  4. **Capacity nudges** — restaurant <40% on a Tuesday → flash promo draft to warmest leads
  5. **Booking reminders** — 24h before a booked appointment, agent drafts a "still on?" reminder

  Each behaviour is a scheduler job that produces draft suggestions for HITL — owner approves or skips. Files: new `services/proactive/` package (`stale.py`, `festivals.py`, `birthdays.py`, `capacity.py`, `reminders.py`), new `api/proactive.py` for dashboard surfacing.

---

- [ ] **9. Marketing site visual overhaul** (~half day, ~4-5 hrs) — Current orange/black palette is wrong for the audience. Re-skin all marketing pages (`templates/marketing/*`). **References**: 11x.ai (dark glass + glow + premium AI energy), Artisan.co (warm editorial cream + serif headlines + sophistication), Landbase.com (clean grid + Linear-esque minimal). **Direction to synthesise**: premium AI-era feel — likely a hybrid of Artisan's editorial typography (large serif headline + clean sans body) with 11x's depth and glow accents in section breaks. Apply across landing, pricing, about, contact, vertical landers, signup, signup_success. Token-driven CSS so dashboard + portal can adopt incrementally.

---

## P0 — Pull these into PLAN.md when quota resets

These are next up after current Phase 1.5 (Business Brief + BYO Leads) finishes.

- [x] ~~**Holding Reply**~~ — shipped 2026-05-09. Schema + PATCH endpoint, webhook wire (Closer intake), Control Tower button, real portal textarea, demo portal textarea. Always-on (no off-hours guard), verbatim, 24h dedupe per contact via `holding_replies_sent` collection.
- [ ] **Outreach dashboard redesign** — collapse 11 buttons → 5 tabs, **now anchored on the locked north-star structure**: **Today** (operator Owner Brief — ₦ collectible, hot replies, actions) / **Activate** (Lead Resurrection + Missed Opp Radar + Sales Copilot) / **Recover** (debt collector + invoice + rent + school fees, unified) / **Clients** (Setup + Briefs + Control Tower) / **System** (Prospect OS + tools + flow viewer). Plus new Control Tower per-client KPI strip (booked calls, ₦ collected, reply rate, brief health %). Plus `/admin/prospect-os` and `/admin/playbooks` new sections. **Sequence: do AFTER Owner Brief upgrade + Lead Resurrection + Missed Opp Radar are built — those provide the content the new tabs host.** 2 days.
- [x] ~~**Per-vertical demo portals**~~ — shipped 2026-05-09. 5 verticals live: `/portal/demo`, `/portal/demo/{hospitality,real_estate,education,professional_services,small_business}` plus aliases (mercury/estate/school/legal/smb). Same product, vertical-tailored sample data, same engine. `services/demo_datasets.py`.
- [x] ~~**Generalise Closer (drop vertical=real_estate filter)**~~ — shipped 2026-05-09. Closer intake now fires for any client with `closer_enabled` regardless of vertical. Lead vertical inherited from client's vertical, not hard-coded.
- [x] ~~**Vertical tag enforcement on client upsert**~~ — shipped 2026-05-09. `vertical` required + validated against `SUPPORTED_VERTICALS` whitelist. Lowercased and normalised on save.
- [x] ~~**HITL drafter reads `enrichment.decision_maker`**~~ — shipped 2026-05-10. `tools/apify_discovery.py` now also propagates `enrichment.title` → `contact_title`. `campaigns/base.py` backfills `biz["contact_name"]` from `enrich_business().team_names[0]` when missing, persists `contact_name`/`contact_title` via `upsert_contact`, passes them into both drafter branches plus follow-ups. `generate_outreach_message_for_client` now accepts + injects `contact_name`/`contact_title`/`enrichment_context` (same `[Partner Name]` placeholder guardrail as the generic drafter).
- [ ] **Control Tower shows `enrichment.decision_maker` + `title`** on lead detail + "Re-enrich" button. (Phase 1.4 close-out)
- [x] ~~**APIFY_API_TOKEN to Railway env**~~ — **REACTIVATED 2026-05-10**. User has credits, Lean Discovery Stack not yet built. Code already gates on `settings.apify_api_token` per call site (hooks.py, social.py, signal_intelligence.py, main.py TikTok actor, api/contacts.py). Setting the env var makes all 5 paths go live with no code change.

## P0 — Nigerian Market Fluency Layer (1 day, ship before/with Business Brief)

The SDR engine (Yori's own outreach to Lagos SMEs) needs deeper Nigerian-market context. Audit revealed: only `real_estate.txt` (146 lines) is at gold-standard depth. Most others are 40–70 lines and weak on specific cultural/regulatory/seasonal cues.

- [x] ~~**Create `agent/prompts/_nigerian_context.txt`**~~ — shipped (127-line shared base layer). Covers payment rails, regulators, seasonal triggers, social cues, city tier tonality, pain-language register.
- [x] ~~**Wire into `agent/brain.py::generate_outreach_message()`**~~ — wired in `generate_outreach_message`, `generate_b2c_message`, `generate_invoice_reminder`, and (2026-05-10) `generate_outreach_message_for_client`. Layered after `self_brief` / `system`, before vertical prompt.
- [x] ~~**Add 4 missing vertical prompts**~~ — `hospitality.txt` (149 lines, prior), `education.txt`, `professional_services.txt`, `clinics.txt` shipped 2026-05-10 at gold-standard depth (≥150 lines each). Includes pain quantified in ₦, channel strategy, WhatsApp + email templates, message rules, signals to reference, anti-signals, custom-build hooks, reply-pattern playbook, final-check guardrail. `clinics` added to `SUPPORTED_VERTICALS`.
- [x] ~~**Bring ALL existing verticals to gold standard**~~ — shipped 2026-05-10. All 16 prompts (real_estate, hospitality, education, professional_services, clinics, legal, small_business, fitness, logistics, fintech, recruitment, events, auto, insurance, agency_sales, agriculture, cooperatives) at gold-standard depth. Total: 1195 → 2391 lines. Each carries the standard structure: Hard Truth, Who you're reaching, Pain in ₦, Specific signals, Anti-signals, ReachNG product fit, Channel strategy, WhatsApp + email templates, Message rules, Custom build hook, Reply-pattern playbook, Final check guardrail.
- [ ] **Lead-signal-injection rules** — each vertical prompt mandates referencing concrete signals from enrichment payload (Maps rating, decision_maker, place categories, IG handle).

## Two parallel discovery tools, different audiences (clarified 2026-05-09 EOD)

The third strategic review's "don't promise lead-gen" applies to **clients**. We still need internal SDR tooling to find Lagos SMEs to pitch ReachNG to ourselves. Both tools build, distinct routing + visibility:

| Tool | Audience | Input | Behaviour |
|------|----------|-------|-----------|
| **Scout v1** (below) | Client-facing | Client's own site + uploaded CSVs + competitor URLs they specify | Enriches existing leads, never finds cold ones. Promised in pricing tiers. |
| **ReachNG Prospect OS** (further below) | Internal — Yori only | Maps + DDG + VConnect + BusinessList + FinelibNG + IG bios | Scrapes EVIDENCE (not just leads) — businesses + leakage signals — to feed our own SDR pipeline. NEVER exposed to clients. NEVER mentioned as a feature. Full spec in `project_reachng_prospect_os.md`. |

Reaffirms `feedback_reachng_agent_scope.md`: discovery is OUR internal funnel only.

## P0 — ReachNG Scout v1 (owned-data research layer, 2 days)

Internal research that enriches and activates leads the client ALREADY HAS. Does NOT scrape the internet for cold leads.

**Capabilities:**
- Crawl the client's own website (their services, prices, locations) → feeds Business Brief auto-fill
- Enrich uploaded CSV/contact lists (look up domains they provided, extract decision-maker from each company's site)
- Monitor specific competitor pages the client asks us to watch
- Detect new competitor offers / vacancies / events / listings (alerts the client)
- Summarise "who this business should target" from their existing customer data

**What Scout does NOT do (intentional):**
- Scrape LinkedIn / IG / FB / Twitter / TikTok
- Crawl protected platforms
- Generate cold contact lists from the internet

**Build plan:**
- [ ] `tools/page_extractor.py` — httpx async + BS4 + Haiku structured extract per URL → `{name, phone, email, address, description, social_links, decision_maker, confidence}` (was already scoped, now scoped to OWNED URLs only)
- [ ] `tools/scout.py` orchestrator — accepts a list of URLs + extraction intent, returns merged structured data
- [ ] Wire into BYO Leads CSV ingest — when user uploads `[name, domain]`, Scout enriches each row before drafts get queued
- [ ] Wire into Business Brief AI intake — already partly done; deepen with Scout's site crawl
- [ ] Competitor watch — `clients.competitor_urls` field + scheduled diff job, alerts to Owner Brief

## P0 — Lead Activation features (genius wedge, 3-4 days)

The killer features per `project_reachng_lead_activation_pivot.md`:

- [x] ~~**Lead Resurrection flow**~~ — shipped 2026-05-09. `/portal/upload-leads/{token}` CSV upload + NDPR attestation + `/portal/run-resurrection/{token}` HITL-forced campaign run. Entry button lives on the Owner Brief card.
- [x] ~~**Missed Opportunity Radar**~~ — shipped 2026-05-09. Detects price-asking replies with no follow-up via reply → contact → outreach_log join. Portal endpoint: `/portal/missed-opportunities/{token}`. Portal widget has one-tap WhatsApp deeplink.
- [x] ~~**WhatsApp Sales Copilot view**~~ — shipped 2026-05-10. Portal: `/portal/sales-copilot/{token}` + per-thread cards on client portal (hot/warm/watch/closed priority, suggested next action, draft approve/skip, WhatsApp deeplink). Operator: `/dashboard/copilot` cross-client surface backed by `tools/sales_copilot.operator_copilot()` + `/api/v1/copilot/operator` JSON, roll-up KPI strip (hot/warm/drafts/total), buckets per client sorted by noise, same approve/skip wired to `/api/v1/approvals`. Header link from main dashboard. Remaining tuning (vertical-specific qualifying prompts, Control Tower deep-linking) folds into the dashboard redesign below.
- [x] ~~**Owner Brief upgrade**~~ — shipped 2026-05-09. `tools/morning_brief_client.py` is cash-focused: collectible amount, hot replies, actions today, cash landed overnight. Portal card renders same signal pack.

## P0 — ReachNG Prospect OS (internal SDR engine, ~3 days MVP)

**Renamed + sharpened 2026-05-09 EOD** per strategic review #4. Full architecture spec in `project_reachng_prospect_os.md`.

**Core framing shift: scrape EVIDENCE, not leads.** Each prospect record carries the leakage signal that will become the cold-message opening line ("I noticed your IG comments are full of unanswered price questions...").

**Hard rule: internal only.** Never client-facing. Never in pricing. Never on marketing. Lives at `/admin/prospect-os`. Per `feedback_reachng_agent_scope.md`.

**Architecture — 8-stage pipeline (`services/prospect_os/`):**

1. **Query Planner** — vertical × city × neighborhood × buying-pain seeds
2. **Source Adapters** — `tools/sources/{maps,ddg,vconnect,businesslist,finelib,instagram}.py` — plugin pattern, normalized output
3. **Crawler** — httpx + BS4 by default (Playwright deferred — too heavy for Railway today)
4. **Extractor** — Haiku + rules → structured biz data + evidence flags
5. **Verifier** — phone normalize (E.164), dedup, junk reject
6. **Scorer** — `likely_to_need_reachng_score` + `likely_reachable_score` (rule-based v1, ML in v2)
7. **Outreach Brain** — angle-specific drafts tied to scraped evidence (uses existing `agent/brain.py`)
8. **Feedback Loop** — every reply/no-reply updates Scorer weights. **THE MOAT.**

**MVP day-1 sequence (ship these first):**
- [ ] `services/prospect_os/__init__.py` + module skeleton
- [ ] `services/prospect_os/query_planner.py` — vertical × city seeds, simple round-robin
- [ ] `tools/sources/maps.py` (refactor existing `tools/discovery.py`)
- [ ] `tools/sources/ddg.py` (already partly in `client_signal_listener.py`)
- [ ] `tools/sources/vconnect.py`
- [ ] `tools/sources/businesslist.py`
- [ ] `tools/page_extractor.py` (shared with Scout v1) — httpx + BS4 + Haiku → `{name, phone, whatsapp, email, location, socials, website, evidence_flags}`
- [ ] `services/prospect_os/scorer.py` — rule-based v1 (has_whatsapp + has_ig + active_30d + high_ticket_category + visible_owner)
- [ ] Admin route `/admin/prospect-os` — query manager + scored prospect list + evidence viewer

**Day 2-3:**
- [ ] `services/prospect_os/verifier.py` — phone normalize + dedup
- [ ] `services/prospect_os/outreach_brain.py` — angle-specific draft templates per evidence pattern (e.g. "comments_with_price_questions" → "I noticed your IG comments are full of price questions — bet that's eating your time...")
- [ ] Wire Prospect OS leads into existing HITL queue with `source="prospect_os"`
- [ ] Feature flag: `USE_APIFY=false` (re-enable when revenue covers it)

**Deferred to v2 (build after first reply data):**
- [ ] Stage 8 Feedback Loop — train Scorer on reply outcomes
- [ ] `tools/sources/instagram.py` — public bio extraction (more fragile)
- [ ] `tools/decision_maker.py` — LinkedIn-via-Google decision-maker resolution
- [ ] `tools/email_finder.py` — pattern-guess + MX SMTP verify
- [ ] Playwright crawler (only if a specific source forces it)

**Cost vs Apify:** ~$50/mo+ → ₦0 infra + ~₦1.50 Haiku per prospect (~₦1500 / 1000 prospects).

Replace paid Apify with a self-hosted free stack until we land 3+ paying clients. Apify gets re-enabled via feature flag once revenue covers it.

**Sources to stitch (all free / public):**
- DuckDuckGo HTML (already in stack via signal listener) — web search
- Google Maps Places API (already in `tools/discovery.py`) — name, phone, address, rating
- VConnect (vconnect.com) — Lagos/Nigeria business directory
- BusinessList.com.ng + FinelibNG + Nigeria Business Directory — backup directories
- Instagram public bios — website + WhatsApp from profile
- Company website "About/Team/Contact" pages — decision-maker via Haiku extraction
- LinkedIn public company pages — decision-maker via `site:linkedin.com/in {{biz}} CEO` Google search
- Email pattern-guess (firstname@domain) + free MX SMTP verify

**Build plan:**
- **Day 1 (foundation):**
  - [ ] `tools/page_extractor.py` — httpx async + BS4 + Haiku structured extract per URL → `{name, phone, email, address, description, social_links, decision_maker, confidence}` (was deferred at P2 — promoted to P0)
  - [ ] `tools/lean_discovery.py` orchestrator — parallel multi-source fan-out, dedupe, merge
  - [ ] `tools/sources/ddg.py` + `tools/sources/google_maps.py` (refactor from existing discovery.py)
- **Day 2 (Nigerian directories + decision-maker):**
  - [ ] `tools/sources/vconnect.py` — scrape Lagos by category
  - [ ] `tools/sources/businesslist.py` + `finelib.py`
  - [ ] `tools/sources/instagram.py` — public bio + website link
  - [ ] `tools/decision_maker.py` — Google → LinkedIn → BS4 → name + title
- **Day 3 (half-day) — email finder + integration:**
  - [ ] `tools/email_finder.py` — pattern-guess + free MX SMTP HELO verify
  - [ ] Wire `discover_lean_leads()` into `campaigns/base.py` parallel to Apify
  - [ ] Feature flags: `LEAN_DISCOVERY_ONLY=true` (default), `USE_APIFY=false`
  - [ ] Smoke-test on 3 verticals × 50 leads each → spot-check quality

**Cost vs Apify:** ~$50/mo+ → ₦0 + ~₦150 per 100 leads in Haiku tokens.
**Trade-off accepted:** medium reliability (scraping breaks occasionally; fallback chain handles), pattern-guessed emails (good enough for cold), ~30 mins/month maintenance when a source breaks.

## P0 — Cross-project SEO audit (~1 hour, blocks SEO campaign decision)

User wants to run an SEO campaign across ReachNG, VIIBE, and Roomly in prep for prelaunch. Each project is at very different SEO maturity — need a per-project audit before committing budget or scope.

- [ ] **ReachNG audit** — does `/` serve a public marketing page? Currently the codebase is all admin/portal/demo. Needs: landing page, vertical sub-pages (one per demo vertical), blog stack, schema.org Organization + SoftwareApplication, robots.txt, sitemap.xml, OG/Twitter cards. Likely scope: build landing site BEFORE running SEO.
- [ ] **VIIBE audit** — mobile-first (Expo/React Native) so primary play is **ASO** (App Store Optimization) not SEO. Audit App Store listing readiness + need for one web landing page (vibe.ng?) for press/share-link previews.
- [ ] **Roomly audit** — repo lives at `C:\Users\OAJAGUN\Documents\roomly`, separate from this workspace. Inspect first to know if web (SEO) or mobile (ASO).
- [ ] **Cross-project assets** — Schema.org Person entity for Yori (E-E-A-T builder), shared blog stack, footer cross-links between domains as internal-network signal.
- [ ] **Output:** `SEO_AUDIT.md` per project with: current state, 5 highest-impact fixes, target keywords (Lagos-specific where relevant), estimated effort, recommended order. Then user picks which project to ship first.

## P0.5 — Pressure test follow-ups (do alongside P0 Burst Head path)

Risks and gaps surfaced by the 2026-05-09 pressure test. Each is small but compounds.

- [ ] **Auto-enforce WhatsApp warmup ramp at code level** — today the 10/25/50 ramp is documented in OPS_GUIDE but operator-trusted. Add `client.daily_send_limit` auto-set on creation: 10 for week 1, 25 for week 2, 50+ thereafter. Stops a fresh number from getting banned by accident. ½ day.
- [ ] **Anthropic + Mongo + Railway budget alerts** — add monthly spend monitoring to `tools/system_sweep.py`. Flag in 7am brief if Anthropic spend > $20/mo, Mongo connections > 400, Railway memory > 400MB sustained. ½ day.
- [ ] **Portal token rotation** — today every portal URL is permanent forever. Add `client.portal_token_rotated_at` and a "regenerate token" button. Use case: client leaves a partner who had the URL. ½ day.
- [ ] **Audit log for client_doc edits** — every `clients` collection update writes to `client_audit_log` with who/what/when. Trust + debugging signal at scale. ½ day.
- [ ] **HITL bulk-approve + draft regeneration** — "approve all 5 from this client" button + per-draft "regenerate shorter" / "regenerate warmer" actions. Reduces operator load by ~70%. 1 day.
- [ ] **Empty-state copy on every dashboard tab** — when a client has 0 leads, 0 invoices, etc, show a helpful next-step copy not blank tables. ½ day.
- [ ] **Mobile-first review of client portal** — verify portal.html renders cleanly at 375px viewport. Most Lagos clients view on phone. ½ day.
- [ ] **Split `agent/brain.py`** — file is 770+ lines and growing. Extract into `agent/drafters/` package: `outreach.py`, `b2c.py`, `social.py`, `invoice.py`, `auto_reply.py`, `classifier.py`. ½ day, code hygiene.
- [ ] **Referral mechanic** — ₦25K credit per referred sign-up that pays for 1 month. Each happy client becomes 3. Schema: `referral_code` per client + Paystack discount logic. 1 day.
- [ ] **Integration test suite** — at first paying client, write 5 integration tests: HITL gate (draft never auto-sends), webhook routes (inbound creates Closer lead correctly), holding reply dedupes 24h, autopilot toggle works, portal token auth. 1 day.

## P1 — Quick wins (≤1 day each, high leverage)

- [ ] **PayNudge** — Google Sheets source + Paystack pay-link on existing `services/debt_collector/`. 1 day.
- [ ] **HITL draft confidence score** — 1-line Haiku call on each draft → `confidence: high/medium/low` + risk tag. Operator approves 30 in 90s instead of 6 mins. ~$0.0001/draft.
- [ ] **"Almost lost" widget on client portal** — surfaces expired drafts + after-hours unanswered enquiries. Pure DB query, no new infra. Sells autopilot internally.
- [ ] **ROI screenshot generator** — auto-PNG "Mercury saved 47h, ₦2.4M tracked this month" client posts to IG/X. Uses existing ReportLab + Pillow.

## P2 — Larger builds (2–5 days)

- [ ] **TaxNudge** — PDF bank statement → Haiku categorisation → VAT/CIT estimate per 2024 Nigerian Tax Reform Acts. `pdfplumber` already in stack. **HIGH commercial pull** — Lagos SMEs panicking about new laws. ~3 days.
- [ ] **Self-serve `/signup`** — Paystack first-month payment + auto-create client + email portal token. Removes Yori-as-bottleneck on hot demos. ~2 days.
- [ ] **Page extractor (`tools/page_extractor.py`)** — DDG snippet → full-page extraction via `httpx + BS4 + Haiku`. Wire into `tools/social.py`, `client_signal_listener.py`, `discovery.py`. Fallback: silently use snippet if fetch fails. ~2 days. **Fallback if quality disappoints:** swap in `crawl4ai` (Playwright-based, heavier RAM but JS-aware).

## P3 — Pressure-tested feature ideas (build after first paying client)

From `project_reachng_feature_ideas_may26.md`. Each pressure-tested against the stack.

- [ ] **Ghost-Worker Attendance Auditor** (TalentOS + Government) — selfie + live location → Claude Vision face match + geofence check. Strong public-sector payroll-fraud fit.
- [ ] **Site-Pulse** (EstateOS) — foreman sends photo → Claude Vision analyses construction milestone (DPC, lintels, roofing) + Lagos building law compliance → ReportLab Progress Certificate PDF. **No blockers, fully buildable.**
- [ ] **VibeReview** (hospitality upsell) — APScheduler 2h after checkout → Unipile feedback request → Claude sentiment → alert manager if negative + high-spender.
- [ ] **Title Ledger** (EstateOS) — WhatsApp agent for land title verification (C of O, Governor's Consent, Excision). Vault-first summary. Constraint: client manually populates `property_vault`.
- [ ] **Voice-Vibe Interviewing** (TalentOS) — async WhatsApp voice-note interviews, Whisper transcription, Claude eval. **Blocker: needs Whisper API.**
- [ ] **WhatsApp voice-note inbound** — Whisper on inbound voice → existing pipeline. Lagos sends voice; we currently drop it. ~30% inbound uplift.

## P4 — Infra monitoring (wire into `tools/system_sweep.py`)

So the 7am WhatsApp brief flags scaling issues before they bite. From `project_reachng_scaling_reference.md`.

- [ ] MongoDB connection count — `db.command("serverStatus")["connections"]["current"]`; flag at >400
- [ ] Atlas storage estimate from collection sizes — flag at >400MB
- [ ] Railway memory (process RSS) — flag at >400MB sustained
- [ ] DDG error rate in last 24h — query structlog buffer
- [ ] Unipile delivery fail rate per client — query `outreach_log` — flag at >5% per client

## P5 — Deferred / blocked / not-yet-triggered

- **LendOS** — full scope in `project_reachng_lendos_scope.md`. Don't touch until user explicitly says start.
- **Locker / Receipt / Roll Call / Shelf modules** — `project_reachng_future_modules.md`. Build only after unlock triggers fire (see PRODUCTS.md).
- **Voice Operator** (Phase 5 in PLAN.md) — already queued there.

---

## How items get promoted

1. Active phase in PLAN.md completes → mark `[x]` and commit
2. Pull next P0 item from this file → write a new phase block in PLAN.md with checkbox tasks
3. Delete the line here (or move to "shipped" archive section)

Don't let this file rot. If an item sits in P0 for 3+ weeks unreviewed, either commit to it or move it to P3.
