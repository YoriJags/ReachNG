# ReachNG — Project Context

AI-powered outreach machine for Lagos businesses. Finds leads, writes personalized WhatsApp messages, tracks replies, converts to clients.

---

## Stack

- **Runtime**: Python 3.12, FastAPI, Uvicorn
- **Database**: MongoDB (via pymongo)
- **AI**: Anthropic Claude (claude-sonnet) for message generation
- **Messaging**: Unipile API (WhatsApp delivery, per-client accounts)
- **Scheduler**: APScheduler (campaign runs, follow-ups)
- **Deployment**: Railway (auto-deploy from GitHub `main`)
- **Logging**: structlog

---

## Verticals

`real_estate` | `recruitment` | `events` | `fintech` | `legal` | `logistics`

---

## Discovery Pipeline (Triple Source)

Campaigns fire 3 parallel discovery tasks, results merged and deduplicated:

1. **Google Maps** (`tools/discovery.py`) — Places Text Search API, finds SMEs by vertical + city
2. **Apollo.io** (`tools/apollo_discovery.py`) — B2B org search (free plan uses `/mixed_companies/search`; upgrade to `/mixed_people/search` at $49/mo for decision-maker contacts + emails)
3. **Social** (`tools/social.py`) — social media leads

Deduplication: by phone + email across all three sources before inserting to DB.

---

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, routes, health + debug endpoints |
| `config.py` | Pydantic settings (env vars) |
| `campaigns/base.py` | `BaseCampaign` — discovery → enrich → generate → send loop |
| `tools/discovery.py` | Google Maps Places API discovery |
| `tools/apollo_discovery.py` | Apollo.io org/people discovery |
| `tools/social.py` | Social media lead discovery |
| `tools/messaging.py` | Unipile WhatsApp send |
| `tools/hitl.py` | Human-in-the-loop approval flow |
| `api/portal.py` | Client portal (`/portal/{token}`) + demo portal (`/portal/demo`) |
| `api/dashboard.py` | Master dashboard (Basic Auth protected) |
| `auth.py` | HTTP Basic Auth via `secrets.compare_digest` |
| `scheduler.py` | APScheduler campaign + follow-up jobs |

---

## Environment Variables (Railway)

| Variable | Purpose |
|----------|---------|
| `GOOGLE_MAPS_API_KEY` | Google Places API key |
| `APOLLO_API_KEY` | Apollo.io API key (`IXBRtXYo...`) |
| `ANTHROPIC_API_KEY` | Claude API |
| `UNIPILE_API_KEY` | WhatsApp delivery |
| `MONGODB_URI` | MongoDB connection string |
| `DASHBOARD_USER` | Master dashboard username |
| `DASHBOARD_PASS` | Master dashboard password |

---

## Auth Model

- **Master dashboard** (`/dashboard`): HTTP Basic Auth — `DASHBOARD_USER` / `DASHBOARD_PASS`
- **Client portal** (`/portal/{token}`): token-gated, one token per client
- **Demo portal** (`/portal/demo`): public, no auth — for pitch deck / investor demos
- **API routes** (`/api/v1/*`): Basic Auth required

---

## Multi-Client Architecture

- Each client has their own Unipile WhatsApp account ID → messages sent from their number
- City-aware discovery: client's city replaces default city in all queries
- Client records stored in MongoDB `clients` collection

---

## Google Maps Status

As of 2026-04-04: billing not yet linked to GCP project `reachng-492121`. Nigerian cards rejected by Google. Workaround: use sister's UK card or get added as Billing Account Administrator on a UK GCP account. Apollo org search is active as primary discovery in the interim.

**Debug endpoints** (Basic Auth required):
- `GET /debug/maps` — raw Google Places API response
- `GET /debug/apollo` — raw Apollo API response

---

## Next Build: Deep Personalization Engine

`tools/enrichment.py` — crawl each business's website before Claude writes outreach.

Stack:
- `httpx` to fetch website HTML (or Firecrawl if JS-heavy)
- Extract: about page, services, team names, recent news
- Combine with Google reviews + Apollo data
- Feed into Claude prompt → hyper-personalized message per business

No Instagram scraping (ToS violation). Website crawling is legal.

---

## Pitch & Demo

- Pitch deck: `pitch/pitch-deck.html`
- Demo portal link: `https://reachng-production.up.railway.app/portal/demo`
- Pre-seed ask: $50K–$200K
- City partner model for international expansion (equity + territory rights)

---

## Key Decisions

- **Apollo free plan**: org search only (no emails). Upgrade at $49/mo for people search.
- **No livestream rating** (VIIBE feature — not ReachNG)
- **No Instagram scraping** — brittle + ToS violation
- **Per-client WhatsApp** — each client's messages come from their own number via Unipile
