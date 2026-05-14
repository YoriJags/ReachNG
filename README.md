# ReachNG

**The AI sales engine for WhatsApp-first businesses.**

ReachNG activates the leads Lagos SMEs already have — old WhatsApp chats, dead spreadsheets, ignored IG DMs, forgotten form submissions — and follows up until they book, buy, or opt out. The same agent recovers unpaid invoices, rent and school fees. One Owner Brief every morning shows the cash about to land and who needs a call.

> **Promise to clients:** "You already have leads. ReachNG makes sure none of them die quietly."

---

## One engine, two modes

| Mode | Audience | Job | Lives at |
|------|----------|-----|----------|
| **ReachNG for clients** | Paying SMEs | AI SDR that activates THEIR leads (CSV, WhatsApp, IG DMs, forms). Owner Brief shows cash about to land. | `/portal/{token}` |
| **ReachNG Prospect OS** | Internal — Yori only | Scrapes evidence about Lagos SMEs (leakage signals), drafts angle-specific cold opens, feeds HITL queue. | `/admin/prospect-os` |

Same `agent/brain.py`. Same HITL queue. Same playbook DB. Different front-ends.

---

## The four cash workflows

1. **Activate Leads** — Lead Resurrection, Missed Opportunity Radar, Sales Copilot, follow-up sequences
2. **Recover Money** — debt collector, invoice chaser, rent chase, school fees
3. **Close Deals** — Closer brain, payment links, owner approval queue
4. **Retain Customers** — birthday/renewal nudges, win-back campaigns, review requests

Verticals stay as **demo language** (Mercury, Sapphire, Lagoon BIS, Adesina, Glow Studio). Internal architecture is workflow-first.

---

## KPIs every feature must move

1. **Booked outcomes** — calls, deposits, payments. Not messages sent.
2. **Onboarding speed** — CSV/WhatsApp chaos → live AI SDR in < 1 hour.
3. **Reply rate per vertical × angle** — playbook quality.
4. **₦ recovered + ₦ in qualified pipeline** — Owner Brief headline.
5. **"Asked price" → paid deposit** conversion (Missed Opportunity Radar moat).

If a feature doesn't move one of these, it doesn't ship.

---

## Stack

- **Runtime**: Python 3.12 · FastAPI · Uvicorn · Jinja2
- **DB**: MongoDB Atlas (pymongo)
- **LLM**: Claude Haiku 4.5 for drafts (`claude-haiku-4-5-20251001`)
- **Messaging**: Unipile (per-client WhatsApp) + Meta Cloud API
- **Payments**: Paystack (NGN, kobo)
- **Scheduler**: APScheduler CronTrigger, `Africa/Lagos`
- **Deployment**: Railway, auto-deploy from `main`

---

## Quick start

```bash
git clone https://github.com/YoriJags/ReachNG.git
cd ReachNG
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # fill in keys
python main.py
```

Open `http://localhost:8000/docs` for the API, `http://localhost:8000/` for the marketing site, `http://localhost:8000/portal/demo` for a live demo.

---

## Environment

Required:

- `ANTHROPIC_API_KEY`
- `MONGODB_URI`
- `UNIPILE_API_KEY`, `UNIPILE_DSN`
- `PAYSTACK_SECRET_KEY`
- `META_APP_SECRET` (webhook signature validation)
- `UNIPILE_WEBHOOK_SECRET`
- `DASHBOARD_USER`, `DASHBOARD_PASS`
- `APP_ENV=production` (enforces webhook signatures)

Optional discovery: `GOOGLE_MAPS_API_KEY`, `APOLLO_API_KEY`.

Never hardcode — always via `config.get_settings()`. Never log PII.

---

## Pricing (Cash Desk)

| Plan | Base | Variable | Best for |
|------|------|----------|----------|
| Cash Desk Starter | ₦80,000/mo | — | Solo operator, 1 channel |
| Cash Desk Growth | ₦150,000/mo | + 2% recovered | 2–5 staff, multi-channel |
| Cash Desk Scale | ₦300,000/mo | + 3% recovered | Priority operator, dedicated playbook tuning |

Annual: 15% off. Self-serve signup at `/signup` with Paystack auto-provisioning.

---

## Key files

| File | Purpose |
|------|---------|
| `agent/brain.py` | Drafting brain — universal across verticals |
| `agent/prompts/_nigerian_context.txt` | Universal Lagos market layer (rails, regulators, seasons, social cues) |
| `agent/prompts/{vertical}.txt` | 16 vertical playbooks |
| `tools/hitl.py` | `queue_draft()` — every outbound message routes through here |
| `services/closer/` | Universal Closer brain |
| `services/debt_collector/` | Money recovery |
| `services/estate/rent_roll.py` | Rent chase |
| `api/invoice_chaser.py` | Invoice follow-up |
| `api/school_fees.py` | School fee chase |
| `api/webhooks.py` | Inbound WhatsApp + holding reply + signature validation |
| `api/marketing.py` | Public marketing site, `/signup`, Paystack webhook |
| `services/brief/` | Business Brief layer |
| `scheduler.py::morning_brief` | Owner Brief (being upgraded to cash-focused) |
| `templates/portal_demo.html` + `services/demo_datasets.py` | 5 vertical demos |

---

## HITL rule (non-negotiable)

All outbound drafts route through `tools/hitl.py::queue_draft()`. The owner approves in the dashboard before anything leaves Unipile. Your number, your voice, zero AI surprises.

---

## Anti-patterns (locked)

- Never promise lead-gen to clients ("we activate yours")
- Never expose Prospect OS as a feature
- Never quote dollars (naira always)
- Never run the cold scraper for clients (only internal)
- No feature ships without moving a KPI
- Never log PII (phone, email, names)

---

## Deployment

Railway auto-deploys from `main`. Production URL: `https://www.reachng.ng`.

Set all env vars under Variables. Webhook signatures are enforced when `APP_ENV=production`.

---

*Built in Lagos · for Lagos SMEs.*
