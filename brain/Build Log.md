# Build Log

[[Home]] | [[Decisions]] | [[Ideas Pipeline]]

---

## Built & Live

### Core Platform
- [x] FastAPI app with lifespan startup
- [x] MongoDB connection + indexes on all collections
- [x] HTTP Basic Auth (`secrets.compare_digest`)
- [x] APScheduler — campaign runs + follow-ups
- [x] Pydantic settings with startup validation (`_validate_env`)
- [x] structlog throughout
- [x] CORS configured (wildcard dev, restrict in prod via `ALLOWED_ORIGINS`)

### Discovery
- [x] Google Maps Places API discovery (`tools/discovery.py`)
- [x] Apollo.io org search (`tools/apollo_discovery.py`)
- [x] Social discovery — TikTok/Twitter/Instagram signals (`tools/social.py`)
- [x] Triple-source parallel discovery + deduplication

### Campaign Engine
- [x] `BaseCampaign` — full discover→enrich→generate→send loop
- [x] 7 verticals: real_estate, recruitment, events, fintech, legal, logistics, agriculture
- [x] Claude Sonnet outreach generation per lead
- [x] HITL approval queue with expiry
- [x] Follow-up scheduling (48h delay, max 2 attempts)
- [x] Daily send limit enforcement

### Security (hardened 2026-04-10)
- [x] SSRF prevention — `_is_safe_host()` on all URL fetches
- [x] MongoDB regex injection — `re.escape()` on all user-supplied regex
- [x] CSV formula injection — `_sanitize_text_field()`
- [x] Path traversal — `pathlib.Path().name` on all uploads
- [x] Unbounded fields — Pydantic `Field(max_length=...)` everywhere
- [x] Portal cross-client data leak — tenant scoping enforced
- [x] HITL draft expiry — `expires_at` on all approval records
- [x] WhatsApp fingerprint jitter — 45–210s weighted random delay
- [x] Startup env validation — `_validate_env()` fails fast

### Products
- [x] **Invoice Chaser** (`/api/v1/invoice-chaser`)
  - PDF upload → pymupdf text extraction → Gemini Flash field extraction
  - WhatsApp reminder with tone escalation (polite→firm→payment_plan→final)
  - History endpoint per client
- [x] **Gemini Flash** extraction layer (`agent/brain.py` → `extract_with_gemini()`)
- [x] **Client Portal** (`/portal/{token}`) — token-gated per client
- [x] **Demo Portal** (`/portal/demo`) — public, for pitches
- [x] **ROI tracking** (`tools/roi.py`, `/api/v1/roi`)
- [x] **A/B testing** (`tools/ab_testing.py`, `/api/v1/ab`)
- [x] **Referrals** (`tools/referral.py`, `/api/v1/referrals`)
- [x] **Competitor intel** (`tools/competitor.py`, `/api/v1/competitors`)
- [x] **Invoices** (`tools/invoices.py`, `/api/v1/invoices`)
- [x] **B2C CSV import** (`tools/csv_import.py`, `/api/v1/b2c`)
- [x] **Webhooks/Hooks** (`tools/hooks.py`, `/api/v1/hooks`)
- [x] **Social hooks** (`tools/social.py`, `/api/v1/social`)
- [x] **MCP server** (`/mcp`) — exposes tools to Claude

### Dashboard
- [x] Overview tab — Today's Work panel + pipeline stats
- [x] Campaigns tab — run/dry-run with HITL toggle
- [x] Clients tab — add clients, generate portal links
- [x] Approvals tab — review + approve/edit queued messages
- [x] Replies tab — inbound sorted by urgency
- [x] Invoices tab — generate + send to clients
- [x] Tools tab — CSV export, hooks config

---

## Not Done / Pending

| Item | Priority | Notes |
|------|----------|-------|
| First live campaign run | 🔴 CRITICAL | Only dry runs done. No real data until this happens |
| Google Maps billing | ✅ DONE | Active — confirmed working 2026-04-12 |
| WhatsApp inbound webhook | 🟡 HIGH | Unipile → reply handler. Unlocks Commerce Assistant |
| Deep personalization engine | 🟡 HIGH | `tools/enrichment.py` — crawl website before Claude writes |
| PLUGng artist vertical | 🟡 HIGH | See [[Ideas Pipeline]] — David Avante is warm lead |
| Paystack payment flow | 🟠 MEDIUM | Client billing via Paystack |
| WhatsApp Commerce Assistant | 🟠 MEDIUM | Product CSV → inbound bot (needs inbound webhook first) |
| POS Reconciliation Agent | 🟠 MEDIUM | Bank alert parser + matching (needs inbound webhook first) |
