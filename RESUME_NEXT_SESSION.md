# ReachNG — Resume Memo (read this first in a fresh chat)

**Last audit: 2026-05-17. Domain live at www.reachng.ng (Railway healthy).**

This is the canonical state file. Before claiming anything is "to build," verify against the audit table below — the backlog has been chronically out of date.

---

## ✅ State of Railway

**Healthy.** All 33 `ensure_*_indexes` calls log `startup_ok` at boot. `GET /health → 200`. Scheduler running 21 jobs. The defensive `_safe()` wrap in `main.py` lifespan is the fix that held — even if a single index call fails, the server still boots.

---

## ✅ Fully shipped + wired in production code

These are done. Do not rebuild. Cross-referenced against actual files / line numbers.

| Item | Location | Wiring |
|---|---|---|
| Voice Notes (Whisper) | `tools/voice_whisper.py` | webhook audio branch |
| Receipt Catcher | `tools/receipt_vision.py` + `services/receipt_match.py` | webhook image branch (`_handle_image_attachment`) |
| Inbound Media downloader | `tools/inbound_media.py` | Meta + Unipile audio/image |
| Emotional Intelligence classifier | `services/inbound_classifier.py` | injected before every draft via `agent/brain.py` + closer brain |
| Predictive Co-pilot | `services/copilot.py` + `api/copilot.py` + dashboard widget at `templates/dashboard.html:10517` | floating bubble + chat panel + 5 tools |
| Outcome Learning Loop | `services/outcome_learning.py` | `tools/hitl.py:271` + scheduler `sweep_silence_to_miss` + `distil_all_clients` + `tag_from_inbound` in webhooks |
| Client Memory + Isolation | `services/client_memory.py` | scope-locked reads/writes, nightly isolation test |
| Knowledge Base | `services/knowledge_base.py` | retrieved at draft time |
| Client Rules Engine | `services/client_rules.py` | rule-match injected into drafter prompt |
| Outcomes Engine — Scorecard | `services/scorecard.py` + `api/scorecard.py` | portal widget + admin endpoints + PDF export |
| Outcomes Engine — Quality Metrics | `services/quality_metrics.py` | nightly drift audit + alert collection |
| Outcomes Engine — Cohort Stats | `services/cohort_stats.py` | `/api/v1/cohort-stats` public endpoint + landing-page counter |
| Outcomes Engine — Weekly Digest | `services/weekly_digest.py` | Monday 7am Lagos scheduled |
| Outcomes Engine — Milestone Engine | `services/milestone_engine.py` | daily milestone sweep + auto-tweet drafter |
| Sales Alerter | `services/sales_alerter.py` | fired from `tools/hitl.py:164` on hot/escalated drafts |
| Waitlist + WhatsApp confirm | `services/waitlist.py` + `api/waitlist.py` | `/waitlist` page + confirmation via Unipile |
| EYO Custom Agent Name | `_agent_identity_block()` in `agent/brain.py` | injected at both drafter entry points |
| Pricing Settings Panel | `services/platform_settings.py` + `api/platform_settings.py` | Control Tower → Pricing inline editor |
| Bank account fields | `api/clients.py` (lines 69-72 with NUBAN validation) | injected into drafter via `_payment_details_block` |
| Closer dashboard tab | `templates/dashboard.html:2811` | lead list + thread view + approve/edit/skip |
| Lean Scraper (in-house) | `services/lean_scraper.py` | replaces Apify spend in ReachNG pipelines |
| Landing page rewrite | `templates/marketing/landing.html` | 8 sections, HBR + WhatsApp Nigeria stats, premium positioning |
| LeanScrape OSS package | `c:/VIIBE/leanscrape/` (separate dir) | local commit done; awaiting `gh repo create` + push |

---

## ⚠️ Partially shipped — finish next

### T0.2.5 — Usage Quota system (cost-control safety net)

**Backend:** `services/usage_meter.py` exists (305 lines) with `check_rate()`, `record()`, `usage_for_client()`, `billing_table()`, `meter()` decorator.

**API:** `api/billing.py` exists (48 lines) with admin endpoints.

**Already wired:** `check_rate()` is called inside `services/inbound_classifier.py` and `services/client_memory.py`.

**NOT YET WIRED — this is what's left:**
1. `@meter` decorator (or inline `check_rate` + `record`) on `tools/voice_whisper.py::transcribe_voice_note` — Whisper costs add up fastest
2. Same on `tools/receipt_vision.py::extract_receipt` — vision costs are higher per call
3. Same on `agent/brain.py` drafter calls — every Haiku message-generation call
4. Admin Billing dashboard tab in `templates/dashboard.html` showing per-client cost + margin + usage trendline

**Est: ~1 day to finish.**

---

## ❌ Genuinely not built

| Item | Effort | Files to create |
|---|---|---|
| **T0.5 Proactive Intelligence** | ~4 days | `services/proactive/{stale,festivals,birthdays,capacity,reminders}.py` + scheduler jobs |
| **Lead Quality Scorer** | ~1 day | `tools/lead_scorer.py` + hook into `campaigns/base.py` queue sort + dashboard column |
| **Nurture Sequences trigger** | ~1 day | scheduler job in `scheduler.py` + draft-quiet-leads logic in services/closer |
| **T0.2.7 A La Carte Pricing** | ~4-5 days | `clients.enabled_features` array + `/pricing` configurator UI + feature gating |
| **Marketing visual overhaul (full re-skin)** | ~half day | re-skin remaining marketing templates beyond landing |
| **GitHub push for leanscrape** | 5 min | `cd c:/VIIBE/leanscrape && gh repo create leanscrape --public --source=. --push` |

---

## Next priority

**1. Finish T0.2.5 wire-up + Admin Billing dashboard.** This is the cost-control safety net before any paying client signs up off the waitlist.

After that, the priority order:
2. Push leanscrape to GitHub (5 min — start the discovery clock)
3. Lead Quality Scorer (1 day — saves Apify-like spend on cold leads)
4. Nurture Sequences trigger (1 day — re-closes dead leads)
5. T0.5 Proactive Intelligence (4 days — the agent-acts-without-being-asked moat)
6. T0.2.7 A La Carte Pricing (4-5 days — defer until usage data exists)

---

## Reading rules for the next chat

- **Always grep before building.** The backlog has been wrong. Trust the code.
- **The CLAUDE.md and BACKLOG.md are NOT canonical state.** This file is.
- **If you're about to start an item:** grep first to confirm it's not already shipped.
