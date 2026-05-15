# ReachNG — Resume Memo (read this first in a fresh chat)

**Last session: 2026-05-15 EOD. Domain live at www.reachng.ng.**

This memo is the single source of truth for: what's shipped, what's broken, what to build next. Open BACKLOG.md afterward for the full queue.

---

## 🚨 URGENT — Railway is failing health-check on the latest deploy

**Symptom:** Build succeeds, image pushes, but `/health` never responds. Replica never becomes healthy. Latest deploy attempts:
- `2026-05-15T15:59 UTC` — 1/1 replicas never became healthy

**Most likely cause:** a Python ImportError at startup. Build log only shows pip output; the actual traceback is in **Railway → Service → "Deploy Logs"** tab (not "Build Logs").

**Steps to fix on resume:**
1. Open Railway → ReachNG service → **Deploy Logs** (or `railway logs --service reachng` from CLI)
2. Look for the most recent Python traceback — it'll name the failing import/symbol
3. Fix the import or remove the offending router registration in `main.py` lines 268-274
4. The recent additions that are most suspicious:
   - `from api.copilot import router as copilot_router` (line 273)
   - `from api.billing import router as billing_router` (line 274)
   - All files exist locally — issue is probably an import *inside* one of them, or a missing `ensure_*_indexes` call in the lifespan
5. As a last resort, comment out lines 273-274 (and the matching `app.include_router` calls) — the rest of the system is independent

**Until this is fixed, no further code work should ship — every push will fail the same way.**

---

## ✅ What's live and working (before the broken deploy)

The previous successful deploy is still serving traffic via Railway's last-good replica or via DNS cache. Confirmed live behaviour:

- **Public landing site** at `www.reachng.ng` — full marketing pages, premium cream/serif design
- **`/waitlist`** — public form, persists to `waitlist` collection, position number returned, WhatsApp confirmation auto-fires via platform Unipile line
- **`/portal/{token}`** — client portal with Outcomes Scorecard widget at top + AI Settings (EYO agent name input)
- **`/dashboard`** — operator Control Tower with Pricing editor, emotion badges on approval queue, HITL approve/edit/skip
- **`/portal/demo`** + 5 vertical demos — Altitude Lagos, Sapphire Estates, Lagoon British, Adesina & Co, Glow Studio

---

## 🏗️ What's been built this run

### Outcomes Engine — fully shipped (5 layers)
- Per-client Scorecard (₦ closed, hours saved, response time, approval rate, cost/booking)
- Quality Metrics + drift alarm (approval rate drop >15pt fires)
- Cohort Stats endpoint (`/api/v1/cohort-stats`) for landing-page social proof
- Weekly Owner Digest (Mon 7am Lagos, Haiku-composed, HITL-gated)
- Milestone Engine (13 milestone types, branded HTML cards, auto-tweet drafter)

### T0.1 Voice Notes (Whisper)
- `tools/voice_whisper.py` + audio extractors in `tools/inbound_media.py`
- Webhook audio branch in `api/webhooks.py` — transcript flows into existing drafter
- `OPENAI_API_KEY` set on Railway

### T0.2 Emotional Intelligence
- `services/inbound_classifier.py` — sentiment/stage/urgency on every inbound
- Injected into `agent/brain.py::handle_payment_reply` + `services/closer/brain.py::draft_next_move`
- Auto-escalation on angry/complaint/on_fire
- Dashboard HITL queue renders emotion badges + red banner

### T0.2.5 Usage Quota (partial)
- `services/usage_meter.py` exists with `meter()` decorator, `check_rate()`, `record()`, `usage_for_client()`, `billing_table()`
- `api/billing.py` exists with admin endpoints
- **NOT YET WIRED** into Whisper / Receipt / Classifier / Drafter / Memory call sites
- Admin Billing dashboard tab not built

### T0.2.6 EYO Custom-named Engine
- `clients.agent_name` field, default "EYO"
- `_agent_identity_block()` in `agent/brain.py` — every draft signs off as the named agent
- Wired into `agent/brain.py` + `services/closer/brain.py`
- Portal Settings UI for client to rename — shipped in commit `6d02cfa`
- `/portal/{token}/agent-name` endpoint accepts rename

### T0.3 Predictive Co-pilot (partial)
- `services/copilot.py` — Haiku planner + 5 tools (quiet_leads / pending_approvals / hot_leads / summarise_week / find_contact) + narrator
- `api/copilot.py` — `POST /api/v1/copilot/ask` (Basic Auth)
- **Dashboard chat widget NOT built** — backend exists but no operator UI

### Waitlist System
- `services/waitlist.py` — add + list + position calc + auto WhatsApp confirmation
- `api/waitlist.py` — public POST + counter endpoint + admin list/invite
- `/waitlist` page renders cleanly, form persists, success card shows position
- Hero CTA + nav CTA all swapped to "Join the waitlist"
- Live social-proof counter on hero (hidden until >0 signups)

### Pricing Settings Panel
- `services/platform_settings.py` — generic settings with audit trail
- `api/platform_settings.py` — GET/POST `/api/v1/admin/pricing`
- Dashboard Control Tower has live-edit pricing card (no deploy needed)

### Sales Alerter (shipped earlier)
- Real-time WhatsApp ping to owner when classifier flags a hot/escalated draft
- Throttled (max 1 alert per contact/client per hour)

### Bank Account Details (shipped earlier)
- Client doc now has `bank_name`, `bank_account_number`, `bank_account_name`, `payment_pref`, `paystack_link`
- `_payment_details_block()` in `agent/brain.py` injects payment rail into drafter prompts
- Drafter quotes bank transfer first (Lagos default), Paystack as secondary option

### Landing Page (story complete)
- Hero: *"Your customer messaged at 11:47pm. EYO already drafted the reply."*
- Crystal-clear problem statement section
- 4-objection killer section (DIY / VA / chatbot / WhatsApp transcription)
- Three pillars (Instant ack / 19 vertical playbooks / chase-the-money)
- "Anatomy of a deal closed at 11:47pm" — 6-step Close Engine narrative
- Pain stories per vertical
- Appetizer section (Receipt Catcher, Voice Note Listener, Closer, Nurture, Lead Quality Scorer, Owner Brief, HITL)
- Vertical demo cards
- Trust pillars
- Final CTA → waitlist
- **Design system**: premium cream + burnt-sienna + Instrument Serif + paper-grain bg

---

## 🎯 Next sprint priorities (in order)

1. **🔥 FIX RAILWAY DEPLOY** (urgent — see top of memo)
2. **T0.2.5 wire-up** (~1 day) — actually decorate Whisper/Receipt/Classifier/Drafter/Memory with `@meter()` so the existing usage_meter.py records events. Build the Admin Billing dashboard tab so per-client cost/margin is visible.
3. **T0.3 Co-pilot dashboard widget** (~half day) — backend works, just needs a sidebar chatbox in `templates/dashboard.html` that POSTs to `/api/v1/copilot/ask`.
4. **T0.4 Outcome Learning Loop** (~3 days) — the moat that compounds. Tag every approved draft, weekly review wins vs misses, auto-tune client prompt.
5. **T0.5 Proactive Intelligence** (~4 days) — stale-lead revival / festival timing / birthday nudges / capacity nudges / booking reminders.
6. **T0.2.7 A La Carte Pricing** (~4-5 days) — defer until you have real usage data from #2 above.

---

## 📁 Where things live

| What | Where |
|---|---|
| Active backlog | `BACKLOG.md` |
| Last deploy commit | `git log -1` |
| Dashboard | `templates/dashboard.html` |
| Portal | `templates/portal.html` |
| Landing site | `templates/marketing/*.html` |
| Agent prompts | `agent/prompts/*.txt` |
| Tier-0 services | `services/{scorecard,quality_metrics,cohort_stats,milestone_engine,weekly_digest,client_memory,inbound_classifier,copilot,usage_meter,waitlist,platform_settings,sales_alerter}.py` |

---

## 🧠 Strategic frames to remember

- **EYO is the default agent name.** Clients can rename in portal. Customer-facing replies never say "ReachNG."
- **Waitlist is the funnel.** No self-serve signup yet. Hand-onboard first batch for wow-quality.
- **Bank transfer is the default Lagos payment rail.** Paystack is the secondary option, not primary.
- **HITL is architectural.** Every outbound draft routes through `tools/hitl.py::queue_draft()`. No bypass.
- **Mongo, not Supabase.** Migration would cost weeks for zero functional gain right now.

Pick up from #1 (fix Railway) when you resume.
