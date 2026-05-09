# ReachNG — Backlog

**Queue of work not yet in PLAN.md.** When a phase completes in PLAN.md, pull the next P0 item here into a new phase.

PLAN.md = active. BACKLOG.md = queued. Promote items, don't duplicate them.

Last updated: 2026-05-09

---

## P0 — Pull these into PLAN.md when quota resets

These are next up after current Phase 1.5 (Business Brief + BYO Leads) finishes.

- [x] ~~**Holding Reply**~~ — shipped 2026-05-09. Schema + PATCH endpoint, webhook wire (Closer intake), Control Tower button, real portal textarea, demo portal textarea. Always-on (no off-hours guard), verbatim, 24h dedupe per contact via `holding_replies_sent` collection.
- [ ] **Outreach dashboard redesign** — collapse 11 buttons → 5 tabs (Today / Clients / Sources / Conversations / System). Hard Brief gate on campaign launch. 2 days.
- [x] ~~**Per-vertical demo portals**~~ — shipped 2026-05-09. 5 verticals live: `/portal/demo`, `/portal/demo/{hospitality,real_estate,education,professional_services,small_business}` plus aliases (mercury/estate/school/legal/smb). Same product, vertical-tailored sample data, same engine. `services/demo_datasets.py`.
- [x] ~~**Generalise Closer (drop vertical=real_estate filter)**~~ — shipped 2026-05-09. Closer intake now fires for any client with `closer_enabled` regardless of vertical. Lead vertical inherited from client's vertical, not hard-coded.
- [x] ~~**Vertical tag enforcement on client upsert**~~ — shipped 2026-05-09. `vertical` required + validated against `SUPPORTED_VERTICALS` whitelist. Lowercased and normalised on save.
- [ ] **APIFY_API_TOKEN added to Railway env** — 5-minute user action, blocks lead enrichment quality
- [ ] **HITL drafter reads `enrichment.decision_maker`** — replaces `[Partner Name]` fallback (last open item from Phase 1.4)
- [ ] **Control Tower shows `enrichment.decision_maker` + `title`** on lead detail; add "Re-enrich" button (Phase 1.4 close-out)

## P0 — Nigerian Market Fluency Layer (1 day, ship before/with Business Brief)

The SDR engine (Yori's own outreach to Lagos SMEs) needs deeper Nigerian-market context. Audit revealed: only `real_estate.txt` (146 lines) is at gold-standard depth. Most others are 40–70 lines and weak on specific cultural/regulatory/seasonal cues.

- [ ] **Create `agent/prompts/_nigerian_context.txt`** — shared base layer injected under `system.txt`. Covers: payment rails (Paystack/Flutterwave/OPay/Moniepoint/Palmpay/GTB), regulators by relevance (FIRS/CBN/CAC/NIMC/NDIC/NAFDAC/SON/LASRRA/LIRS), seasonal triggers (Detty December, school resumption Jan+Sept, owambe season, NYSC postings, FIRS deadlines), social cues (Aso-ebi, honorifics Mr/Mrs/Aunty/Engineer/Chief, "well done", "epp"), city tier tonality (Lagos > Abuja > PH > Ibadan/Kano), pain-language register ("light off", "fuel finished", "MoMo", "POD").
- [ ] **Wire into `agent/brain.py::generate_outreach_message()`** — load + concatenate after self_brief, before vertical prompt.
- [ ] **Add 4 missing vertical prompts** at gold-standard depth (~120+ lines): `hospitality.txt`, `education.txt`, `professional_services.txt`, `clinics.txt`. Each must include: who they are, real Nigerian pain quantified in ₦, ReachNG's specific solution, channel strategy (email vs WhatsApp), email + WhatsApp templates, message rules, named signals to reference (e.g. "DM for price" tell for hospitality).
- [ ] **Bring ALL existing verticals to gold standard** (~120+ lines each) — same depth as `real_estate.txt`. Includes the 6 thin ones (events, agriculture, auto, cooperatives, fitness, insurance) AND the medium ones (legal, fintech, recruitment, small_business, logistics, agency_sales) — every single vertical prompt gets the full treatment. No prompt left as a thin sketch.
- [ ] **Lead-signal-injection rules** — each vertical prompt mandates referencing concrete signals from enrichment payload (Maps rating, decision_maker, place categories, IG handle).

## P0 — Cross-project SEO audit (~1 hour, blocks SEO campaign decision)

User wants to run an SEO campaign across ReachNG, VIIBE, and Roomly in prep for prelaunch. Each project is at very different SEO maturity — need a per-project audit before committing budget or scope.

- [ ] **ReachNG audit** — does `/` serve a public marketing page? Currently the codebase is all admin/portal/demo. Needs: landing page, vertical sub-pages (one per demo vertical), blog stack, schema.org Organization + SoftwareApplication, robots.txt, sitemap.xml, OG/Twitter cards. Likely scope: build landing site BEFORE running SEO.
- [ ] **VIIBE audit** — mobile-first (Expo/React Native) so primary play is **ASO** (App Store Optimization) not SEO. Audit App Store listing readiness + need for one web landing page (vibe.ng?) for press/share-link previews.
- [ ] **Roomly audit** — repo lives at `C:\Users\OAJAGUN\Documents\roomly`, separate from this workspace. Inspect first to know if web (SEO) or mobile (ASO).
- [ ] **Cross-project assets** — Schema.org Person entity for Yori (E-E-A-T builder), shared blog stack, footer cross-links between domains as internal-network signal.
- [ ] **Output:** `SEO_AUDIT.md` per project with: current state, 5 highest-impact fixes, target keywords (Lagos-specific where relevant), estimated effort, recommended order. Then user picks which project to ship first.

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
