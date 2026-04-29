# Architecture

[[Home]] | [[Campaign Flow]] | [[Integrations]] | [[API Reference]]

---

## Stack

| Layer | Tech |
|-------|------|
| Runtime | Python 3.12, FastAPI, Uvicorn |
| Database | MongoDB (pymongo) |
| AI — Outreach | Anthropic Claude Sonnet |
| AI — Extraction | Gemini Flash (cheap), Claude Haiku (fallback) |
| Messaging | Unipile API (WhatsApp) |
| Scheduler | APScheduler |
| Deployment | Railway (auto-deploy from GitHub `main`) |
| Logging | structlog |

---

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, all routes wired, lifespan startup |
| `config.py` | Pydantic settings — all env vars live here |
| `campaigns/base.py` | `BaseCampaign` — the core discover→enrich→generate→send loop |
| `tools/discovery.py` | Google Maps Places API discovery |
| `tools/apollo_discovery.py` | Apollo.io org/people discovery |
| `tools/outreach.py` | `send_whatsapp()` via Unipile |
| `tools/hitl.py` | Human-in-the-loop approval queue |
| `tools/enrichment.py` | Website crawl before Claude writes (next build) |
| `agent/brain.py` | All Claude + Gemini calls — message gen, extraction |
| `api/portal.py` | Client portal + demo portal |
| `api/dashboard.py` | Master dashboard (Basic Auth) |
| `api/invoice_chaser.py` | PDF parse → WhatsApp payment reminders |
| `auth.py` | HTTP Basic Auth (`secrets.compare_digest`) |
| `scheduler.py` | APScheduler jobs — campaigns + follow-ups |

---

## Data Flow

```
Campaign trigger (manual or scheduler)
    │
    ├─► Google Maps discovery ──┐
    ├─► Apollo.io discovery ────┼─► Deduplicate (phone + email) → MongoDB contacts
    └─► Social discovery ───────┘
                │
                ▼
        Enrich (score + categorise)
                │
                ▼
        Claude writes personalised WhatsApp per lead
                │
           ┌────┴────┐
           │ HITL ON │ → Approvals queue → human approves → send
           │ HITL OFF│ → Send immediately via Unipile
           └────┬────┘
                │
                ▼
        Track: replied / converted / opted-out
```

---

## Auth Model

| Layer | Method |
|-------|--------|
| Master dashboard `/dashboard` | HTTP Basic Auth — `DASHBOARD_USER` / `DASHBOARD_PASS` |
| Client portal `/portal/{token}` | Token-gated, one token per client |
| Demo portal `/portal/demo` | Public, no auth |
| API routes `/api/v1/*` | Basic Auth required |

---

## Multi-Client Model

- Each client has their own Unipile WhatsApp account ID
- Messages sent from client's own number
- City-aware discovery: client's city replaces default in all queries
- Client records in MongoDB `clients` collection
