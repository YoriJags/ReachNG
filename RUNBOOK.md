# ReachNG — Operating Runbook

How to **run it like a dev** and how to **operate it day to day**. Written from the
actual code/routes (2026-06-01). If a step here disagrees with the dashboard, the
dashboard wins — open an issue and fix this file.

---

## 0. Run it like a dev (local)

The app **will not finish startup without a reachable MongoDB** — the lifespan
ensures ~33 indexes and blocks until Mongo answers. There is no local `mongod` or
Docker on this machine, so pick one:

**Option A — point at a free Atlas dev cluster (fastest):**
```bash
cp .env.example .env            # then edit:
#   MONGODB_URI=mongodb+srv://<dev-cluster>...    (a SEPARATE dev DB, never prod)
#   ANTHROPIC_API_KEY=sk-ant-...                   (real, for drafting to work)
#   DASHBOARD_USER=admin  DASHBOARD_PASS=admin
#   SCHEDULER_ENABLED=false                        (don't fire cron jobs locally)
#   APP_ENV=development
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
python main.py                                      # serves on :8000 (or $PORT)
```

**Option B — local Mongo:** install MongoDB Community (`mongod`) or run
`docker run -p 27017:27017 mongo`, then `MONGODB_URI=mongodb://localhost:27017/reachng_dev`.

**Smoke it without a browser:**
```bash
curl -s localhost:8000/health                       # {"status": ...}
curl -s -u admin:admin localhost:8000/dashboard | head   # admin (Basic Auth)
open  localhost:8000/portal/demo                     # public demo control room
```
Run the tests (no DB needed — lifespan not fired):
```bash
SCHEDULER_ENABLED=false ANTHROPIC_API_KEY=x MONGODB_URI=mongodb://localhost:27017/t \
  python -m pytest tests/test_smoke.py tests/test_magic_features.py -q
```

**Prod (Railway):** auto-deploys from `main`. Required env in §Environment of README.
Set `SENTRY_DSN` + `RESEND_WEBHOOK_SECRET` there (see README).

---

## 1. What ReachNG actually is (so the flow makes sense)

EYO = one AI WhatsApp employee per client. It **drafts** every reply, **catches**
payment screenshots, **chases** dead conversations, sends a morning **Owner Brief**,
and surfaces **money leaks** / **revenue rescue** — and **nothing sends until the
owner approves** (HITL), unless they've explicitly switched a reply-type to Autopilot.

Two surfaces:
- **Admin / Control Tower** (`/dashboard`, Basic Auth) — you, the operator.
- **Client portal** (`/portal/{token}`, token = the auth) — the paying SME owner.

Live suites: **Outreach** (your acquisition funnel) · **EstateOS** (real estate) ·
**TalentOS** (HR). Everything else is deferred (see PLAN.md) and should be hidden.

---

## 2. One-time operator setup

1. Set env on Railway (README §Environment). Confirm `GET /health` is ok.
2. Connect ReachNG's own Unipile WhatsApp account (for SDR + owner briefs).
3. Confirm Paystack keys (client billing) + Resend (email + webhooks).

## 3. Onboard a paying client (the ordered flow)

1. **Add the client** — Admin → **Clients** → "Add Pilot Client" (skips the brief
   gate, generates a portal token instantly). Copy the portal link.
2. **Send them the portal link** → they run the **7-step onboarding wizard** at
   `/portal/{token}/onboard` (Business basics → Voice & tone → Offer & pricing →
   Lead qualification → Approval rules → Test EYO → Go-live). Concierge option on
   step 1 lets them paste materials and you train EYO for them.
3. **Connect their WhatsApp** — `/portal/{token}/connect-whatsapp` (Unipile QR).
   Until this is green, EYO can't send. The client portal's primary CTA enforces
   this order: Finish setup → Reconnect WhatsApp → Review drafts → Wake money up.
4. **Import their book** (optional) — `/portal/{token}/book` (WhatsApp share / vCard
   / paste / CSV) so EYO can work existing relationships + the Money Leak Report has
   history to scan.

## 4. Daily operating loop

**You (operator), each morning — Admin → Command Center → Needs Attention:**
- Aging approvals (>12h), WhatsApp-disconnected clients, at-risk margin, failed jobs.
  Clear these first.

**Per client (mostly self-serve in their portal):**
- **Approvals** tab — review/edit/approve drafts. Editing teaches EYO ("EYO learned…").
- **Money** tab — Money Leak Report → "Wake this money up" (queues rescue follow-ups
  through HITL) · payments · bookings · hours saved.
- **Today** tab — Owner Brief headline + what needs a response.

**Automatic (scheduler, `Africa/Lagos`):** morning Owner Brief, proactive festival
nudges (06:30), outcome-learning distil (Sun 23:00), scorecard/quality/cohort sweeps,
WhatsApp session-expiry health loop, billing retries.

## 5. The HITL rule (never break it)

Every outbound — rent chase, invoice reminder, SDR message, rescue follow-up — routes
through `tools/hitl.py::queue_draft()`. The human approves before it leaves Unipile.
Autopilot is *earned* per reply-type (≥20 approvals, ≥70% unedited) and opt-in.

---

## 6. Admin dashboard map (current IA)

Sidebar (Outreach product): **Command Center** · **Needs Attention** · **Money Engine**
· **Approvals** · **Clients** · **Growth · Prospect OS** · **System**. Plus suite
switchers for **EstateOS** + **TalentOS**.

> ⚠️ Known cleanup: the template still ships DOM panels for deferred suites that aren't
> in the sidebar (LendOS, FleetOS, SchoolOS, LegalOS, debt-collector, float-optimizer,
> fx-lock, fuel-reprice, market-credit, material-check, product-auth, etc.). They're
> mostly unreachable but bloat the page. See the dead-UI audit / cleanup task.

---

## Pre-launch premium outreach (internal Prospect OS)

Founder-led, early-access outreach for **ReachNG itself** — not client lead-gen.
Discovers premium, owner-led Lagos/Abuja SMEs that live on WhatsApp and drafts a
personal founder email for each. Reuses the existing discovery → score → HITL
pipeline; the campaign vertical is **`b2b_saas`**.

**Positioning guardrails (baked into the drafter):** never claim the product has
launched; never promise leads or guaranteed revenue; no "Dear sir/ma"; no hype;
mention their category/city; never mention Maps/scraping. Position EYO as a
trainable AI employee for WhatsApp that replies faster, catches payment/customer
signals, and briefs the owner daily — every reply waits for the owner's tap.

### 1. Dry-run discovery (safe, nothing sends)
Dashboard → **Growth · Prospect OS → Run Campaign**:
- Vertical: **⭐ ReachNG Pre-launch (Premium SMEs · founder voice)**
- City: Lagos or Abuja · keep **Dry run** ticked · **Review before send** is forced on
- Run. You'll see drafted emails + each lead's variant (A/B/C), rating, review count, verdict.

Or via API (admin Basic Auth):
```
POST /api/v1/campaigns/run
{ "vertical":"b2b_saas", "cities":["Lagos"], "max_contacts":15,
  "dry_run":true, "hitl_mode":true }
```
`min_rating` defaults to **4.3** and `min_reviews` to **30** for `b2b_saas` (override either in the body).

### 2. Queue real drafts for review (still no auto-send)
Same control, untick **Dry run** but leave **Review before send** on (forced for this
vertical). Drafts land in **Approvals** — nothing leaves until you approve. Each
contact is recorded with its A/B/C angle at queue time.

### 3. Review + send approved messages
**Approvals** tab → read each draft → Approve (sends) / Edit / Skip. Edits feed the
learning loop. Sending is capped by `DAILY_SEND_LIMIT` (default 50/day).

### 4. Check results
- **Growth → Outreach Analytics** — opens / clicks / waitlist conversions (Resend + `/hi/{slug}`).
- A/B/C reply rates: `GET /api/v1/ab/stats?vertical=b2b_saas` (winner across the 3 angles).

### Variants (A/B/C, auto-assigned per contact)
- **A · Founder/direct** — early-access invitation from the founder.
- **B · Money-leak** — money dying in WhatsApp chats (missed enquiries, unpaid follow-ups).
- **C · Owner-relief** — EYO watches WhatsApp, drafts in your voice, daily brief.

### Lead scoring (who gets contacted)
`tools/lead_scorer.py` ranks Hot/Warm/Cold. Premium signals: rating ≥ 4.3, reviews
≥ 30, WhatsApp-heavy category (restaurants/hotels/lounges/clinics/gyms/real-estate/
auto/schools/logistics/etc.), premium keyword in name, premium neighbourhood. Cold
leads are dropped from the campaign automatically.

### Env vars
- `GOOGLE_MAPS_API_KEY` — discovery (missing → discovery returns nothing + logs `maps_discovery_skipped_no_key`; the rest of the run still works).
- `ANTHROPIC_API_KEY` — founder-voice drafts (Haiku, ~₦4 each).
- `RESEND_API_KEY` — email send from `hello@reachng.ng`.
- `MONGODB_URI` — contacts / dedup / A/B store.
- Optional: `DAILY_SEND_LIMIT` (default 50), `DEFAULT_CITY` (default Lagos).

### Safety defaults
Dry-run + HITL on by default; **WhatsApp is not used** for ReachNG's own prospecting
(email only — no Unipile cost/spam risk); cross-run dedup via `place_id` (90-day
refresh); per-business one contact; daily send cap. Never auto-send the first campaign.
