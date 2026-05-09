# ReachNG — Backlog

**Queue of work not yet in PLAN.md.** When a phase completes in PLAN.md, pull the next P0 item here into a new phase.

PLAN.md = active. BACKLOG.md = queued. Promote items, don't duplicate them.

Last updated: 2026-05-09 (after pressure test + SEO audit)

---

## P0 — "BURST HEAD" Launch Path (do this in order, total ~5 days)

The five things that turn ReachNG from "this works" into "bro, you have to see this." Sequenced. Do them in order — each unlocks the next.

- [ ] **1. Buy domain + build public marketing site** (2 days) — `reachng.ng` (or `.co` if `.ng` taken). Pages: `/`, `/how-it-works`, `/pricing`, `/about` (with Yori's face), `/contact`, plus 5 vertical landers (`/for-restaurants`, `/for-real-estate`, `/for-schools`, `/for-legal`, `/for-small-business`). Each vertical lander links to its demo portal. Build on existing FastAPI + Jinja stack — `templates/marketing/` + `api/marketing.py`. Reuse demo portal CSS variables for visual consistency. Add `robots.txt`, `sitemap.xml`, schema.org Organization + SoftwareApplication + FAQPage, OG cards per vertical, Twitter Card meta. **Without this, every other lever is set to zero — `/` currently 401s for prospects.**
- [ ] **2. Concrete 3-tier pricing** (1 day) — Starter ₦80K, Growth ₦150K, Scale ₦300K + annual = 15% off. Build pricing page with feature-delta matrix. Anchor each price against pain ("a single missed Saturday booking is ₦50K — Starter pays for itself in 2 weeks"). Replace the vague ₦80K-400K range in PRODUCTS.md with the concrete tiers.
- [ ] **3. Self-serve `/signup` flow + Paystack first-month** (2 days, was P2 → P0) — `/signup` form: business name, vertical, WhatsApp number, plan tier. Paystack Checkout for first month → webhook on success → auto-create client doc + send Unipile pairing link + email portal token. **Removes Yori as the bottleneck on hot demos.** Required: Paystack API integration, Unipile pairing automation, welcome email template.
- [ ] **4. First paid client → public case study** (process, ~1 week after first paid client) — One screenshot, one pull-quote, one number ("18% → 3% no-shows in 30 days"). Lives at `/case-studies/[client]`. Becomes the social-proof anchor. Post the screenshot on Twitter/LinkedIn the day it goes live.
- [ ] **5. Founder-public authority cadence** (process, ongoing 20 mins/day) — Yori posts 3×/week on Twitter + LinkedIn. Theme: "what the agent did this week" with screenshots. Reply-guy on threads from Iyin@Paystack, Tunde@Bumpa, Olu@Flutterwave. The Lagos AI-for-SME conversation is wide open; whoever talks loudest about it owns the category.

**Total: ~5 days of build + ongoing process. Once these five are real, ReachNG is "ready to burst head".**

---

## P0 — Pull these into PLAN.md when quota resets

These are next up after current Phase 1.5 (Business Brief + BYO Leads) finishes.

- [x] ~~**Holding Reply**~~ — shipped 2026-05-09. Schema + PATCH endpoint, webhook wire (Closer intake), Control Tower button, real portal textarea, demo portal textarea. Always-on (no off-hours guard), verbatim, 24h dedupe per contact via `holding_replies_sent` collection.
- [ ] **Outreach dashboard redesign** — collapse 11 buttons → 5 tabs (Today / Clients / Sources / Conversations / System). Hard Brief gate on campaign launch. 2 days.
- [x] ~~**Per-vertical demo portals**~~ — shipped 2026-05-09. 5 verticals live: `/portal/demo`, `/portal/demo/{hospitality,real_estate,education,professional_services,small_business}` plus aliases (mercury/estate/school/legal/smb). Same product, vertical-tailored sample data, same engine. `services/demo_datasets.py`.
- [x] ~~**Generalise Closer (drop vertical=real_estate filter)**~~ — shipped 2026-05-09. Closer intake now fires for any client with `closer_enabled` regardless of vertical. Lead vertical inherited from client's vertical, not hard-coded.
- [x] ~~**Vertical tag enforcement on client upsert**~~ — shipped 2026-05-09. `vertical` required + validated against `SUPPORTED_VERTICALS` whitelist. Lowercased and normalised on save.
- [ ] **HITL drafter reads `enrichment.decision_maker`** — replaces `[Partner Name]` fallback. Works once Lean Discovery Stack populates the field. (Phase 1.4 close-out)
- [ ] **Control Tower shows `enrichment.decision_maker` + `title`** on lead detail + "Re-enrich" button. (Phase 1.4 close-out)
- [ ] ~~**APIFY_API_TOKEN to Railway env**~~ — DEFERRED until 3 paying clients land. Lean Discovery Stack replaces Apify until then. Re-enable via `USE_APIFY=true` flag once revenue covers it.

## P0 — Nigerian Market Fluency Layer (1 day, ship before/with Business Brief)

The SDR engine (Yori's own outreach to Lagos SMEs) needs deeper Nigerian-market context. Audit revealed: only `real_estate.txt` (146 lines) is at gold-standard depth. Most others are 40–70 lines and weak on specific cultural/regulatory/seasonal cues.

- [ ] **Create `agent/prompts/_nigerian_context.txt`** — shared base layer injected under `system.txt`. Covers: payment rails (Paystack/Flutterwave/OPay/Moniepoint/Palmpay/GTB), regulators by relevance (FIRS/CBN/CAC/NIMC/NDIC/NAFDAC/SON/LASRRA/LIRS), seasonal triggers (Detty December, school resumption Jan+Sept, owambe season, NYSC postings, FIRS deadlines), social cues (Aso-ebi, honorifics Mr/Mrs/Aunty/Engineer/Chief, "well done", "epp"), city tier tonality (Lagos > Abuja > PH > Ibadan/Kano), pain-language register ("light off", "fuel finished", "MoMo", "POD").
- [ ] **Wire into `agent/brain.py::generate_outreach_message()`** — load + concatenate after self_brief, before vertical prompt.
- [ ] **Add 4 missing vertical prompts** at gold-standard depth (~120+ lines): `hospitality.txt`, `education.txt`, `professional_services.txt`, `clinics.txt`. Each must include: who they are, real Nigerian pain quantified in ₦, ReachNG's specific solution, channel strategy (email vs WhatsApp), email + WhatsApp templates, message rules, named signals to reference (e.g. "DM for price" tell for hospitality).
- [ ] **Bring ALL existing verticals to gold standard** (~120+ lines each) — same depth as `real_estate.txt`. Includes the 6 thin ones (events, agriculture, auto, cooperatives, fitness, insurance) AND the medium ones (legal, fintech, recruitment, small_business, logistics, agency_sales) — every single vertical prompt gets the full treatment. No prompt left as a thin sketch.
- [ ] **Lead-signal-injection rules** — each vertical prompt mandates referencing concrete signals from enrichment payload (Maps rating, decision_maker, place categories, IG handle).

## P0 — Lean Discovery Stack (Apify rival, 2.5 days)

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
