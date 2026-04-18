# ReachNG — Project Context

Nigerian SME SaaS. **Current focus: land first Lagos paying client.** Product has been narrowed to two active suites:

- **EstateOS** — Real Estate (Rent Roll, KYC, PoF, Lawyer Bundle, chase sequences)
- **TalentOS** — HR (Payroll, Policy Bot, Leave, Attendance)

7 other suites exist in code but are hidden from UI. Do not work on them unless explicitly asked.

The original SDR/outreach product (Google Maps + Apollo + Unipile WhatsApp discovery) still exists and still runs — it's the acquisition funnel feeding EstateOS/TalentOS demos. Don't rip it out.

---

## Stack

- **Runtime**: Python 3.12, FastAPI, Uvicorn, Jinja2
- **DB**: MongoDB Atlas (pymongo). Collection families: `estate_*`, `hr_*`, `clients`, `leads`, `campaigns`, `drafts`
- **LLM**: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) for drafts; Sonnet/Opus only for complex reasoning
- **Messaging**: Unipile (WhatsApp, per-client account IDs)
- **Scheduler**: APScheduler CronTrigger, timezone `Africa/Lagos`
- **Deployment**: Railway (auto-deploy from GitHub `main`)
- **Logging**: structlog — NEVER log PII (phone, email, names)

Do not suggest Node/TypeScript/pnpm/Next.js — wrong stack.

---

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, route registration, lifespan (index ensures), health + debug |
| `config.py` | Pydantic settings |
| `auth.py` | HTTP Basic Auth + portal-token auth |
| `scheduler.py` | APScheduler jobs (rent period open, rent chase, payroll reminders, invoice chaser, fleet escalation) |
| `templates/dashboard.html` | Master admin SPA (all suites as tabs) |
| `templates/portal.html` | Client portal SPA |
| `api/rent_roll.py` | EstateOS rent roll + chase routes |
| `api/payroll.py` | TalentOS payroll + payslip routes |
| `api/hr_suite.py` | HR leave, attendance, policy bot |
| `api/dashboard.py` | Admin dashboard backend |
| `api/portal.py` | Client portal backend |
| `services/estate/rent_roll.py` | Unit/tenant/ledger logic, chase staging |
| `services/hr_suite/payroll.py` | PAYE, CRA, payslip compute + HTML render |
| `tools/hitl.py` | `queue_draft()` — ALL outbound messages route through here |
| `tools/discovery.py` | Google Maps Places discovery (SDR funnel) |
| `tools/apollo_discovery.py` | Apollo.io discovery (SDR funnel) |
| `tools/messaging.py` | Unipile WhatsApp send |

---

## Domain Rules (Don't Get These Wrong)

### Nigerian Payroll
- PAYE bands: 7 / 11 / 15 / 19 / 21 / 24 %
- CRA = max(₦200,000, 1% × gross) + 20% × gross (annual)
- PENCOM = 8% employee, 10% employer, on (basic + housing + transport)
- NHF = 2.5% × basic, only if `nhf_enrolled == True`

### Rent Chase Escalation
- **friendly** 1-6 days — warm, assumes oversight
- **firm** 7-13 days — direct, references amount + date
- **serious** 14-29 days — consequences, mention quit notice possibility
- **warning** 30-59 days — formal, explicit quit notice threat, **Lagos Tenancy Law**
- **final** 60+ days — formal quit notice, 7-day ultimatum

Period opening must be idempotent — unique compound index on `(unit_id, period)`.

### Multi-Tenant Isolation (P0)
Every `/estate/*` and `/hr/*` route must scope by tenant (`landlord_company` or portal token). Leakage between landlords/companies is a P0 bug.

---

## HITL Rule (Non-Negotiable)

All outbound drafts (rent chase, invoice reminder, SDR message, anything) route through `tools/hitl.py::queue_draft()`. Never send directly from a service or route. The human approves in the dashboard before anything leaves Unipile.

---

## Auth Model

- **Admin dashboard** `/admin/*` — session-based, Basic Auth wrapper
- **Client portal** `/portal/{token}` — token-gated per client
- **Demo portal** `/portal/demo` — public, no auth (pitch deck / investor demos only)
- **API** `/api/v1/*` — Basic Auth

---

## Environment Variables (Railway)

`ANTHROPIC_API_KEY`, `MONGODB_URI`, `UNIPILE_API_KEY`, `GOOGLE_MAPS_API_KEY`, `APOLLO_API_KEY`, `DASHBOARD_USER`, `DASHBOARD_PASS`

Never hardcode — always via `config.get_settings()`.

---

## Code Standards

- Keep files under ~500 lines
- Type-hint all public APIs; Pydantic models on routes
- Validate input at boundaries
- Async on I/O paths; exponential backoff on external calls (Unipile, Google, Apollo)
- No `.then()` chains — use `await`
- No PII in structlog output

---

## Workflow

1. Plan first for 3+ step tasks
2. Verify before done — curl the route, open the tab, inspect Mongo
3. Root-cause, don't patch — no `--no-verify`, no temp fixes
4. Update `PLAN.md` checkboxes if present

---

## Memory Entries to Check First

- `project_reachng_suite_catalog.md` — 12 suites / 89 features master list
- `project_reachng_delivery_plan.md` — current delivery roadmap
- `project_reachng_control_tower_plan.md` — 5-phase build plan
- `project_reachng_onboarding_sop.md` — 8-step client onboarding
- `project_reachng_build_sequence.md` — admin backend UI → client portal UI
- `project_reachng_stack_obtainability.md` — green/yellow/red per new stack
- `project_gemini_ideas_source.md` — full Gemini idea funnel, read before adding features

---

## Key Decisions

- Apollo free plan = org search only; $49/mo unlocks people search + emails
- No Instagram scraping (brittle + ToS)
- Per-client WhatsApp via Unipile — messages come from the client's own number
- EstateOS + TalentOS are the only two suites shown in UI right now
- Livestream rating belongs to Viibe, not ReachNG
