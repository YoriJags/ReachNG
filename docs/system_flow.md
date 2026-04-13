# ReachNG — Full System Flow

*Last updated: 2026-04-13*

---

## Overview

ReachNG is an AI-powered outreach engine. It finds businesses, writes personalised messages, sends them automatically, and tracks every response — so you spend time closing, not prospecting.

---

## Architecture at a Glance

```
[Dashboard] → [API] → [Campaign] → [Discovery x3] → [Score & Filter] → [Enrich] → [Generate] → [Send / Queue] → [Record] → [Reply Handler] → [Dashboard]
```

---

## 1. Discovery — Three Parallel Sources

Every campaign fires three discovery tasks simultaneously and merges the results.

### 1a. Google Maps (Primary)
- **File**: `tools/discovery.py`
- **How**: Places Text Search API → Place Details API
- **What**: Finds SMEs in Lagos (or selected city) by vertical + keyword queries
- **Returns**: Name, phone, website, address, rating, category, place_id
- **Status**: Active — confirmed working

### 1b. Apollo.io (B2B)
- **File**: `tools/apollo_discovery.py`
- **How**: Apollo `/mixed_companies/search` API
- **What**: B2B organisations — decision maker names, company emails
- **Returns**: Company name, email, domain, industry, city
- **Status**: Active (free plan = org search only; upgrade to $49/mo for people + emails)

### 1c. Social Media (Apify)
- **File**: `tools/social.py`
- **How**: Apify actors for each platform
- **Platforms**:
  - **Instagram** — hashtag scraper (e.g. `#LagosRealEstate`, `#LagosJobs`)
  - **TikTok** — hashtag scraper (Nigerian SME content — high intent)
  - **Twitter/X** — intent keyword search (e.g. "looking for recruitment agency Lagos")
  - **Facebook** — keyword search across pages and groups
  - **Competitor monitor** — people asking about competitors = hottest leads
- **Returns**: Username, display name, post text, profile URL, follower count, bio
- **Platform tag**: each lead tagged `instagram` / `tiktok` / `twitter` / `facebook`
- **Status**: Active — requires `APIFY_API_TOKEN` in Railway env vars

---

## 2. Scoring & Deduplication

After all three sources return results:

1. **Deduplication** — by phone + email across all sources. No business appears twice.
2. **Lead scoring** (`tools/scoring.py`) — each lead gets a score:
   - Google rating ≥ 4.0 → +points
   - Has phone → +points
   - Has website → +points
   - High-value sector (legal, recruitment, real estate, fintech) → +points
3. **Sort order**: Social leads first (warmest signal), then Apollo (B2B verified), then Maps

---

## 3. Filters

Applied per lead before any message is generated:

| Filter | Logic |
|--------|-------|
| **Already contacted** | `has_been_contacted(place_id)` — global dedup, any business ever messaged is skipped |
| **Min rating** | If `min_rating` set in campaign form, skip leads below threshold |
| **Quality gate** | `should_contact()` — rejects irrelevant or low-quality leads |
| **Channel availability** | Skip if no phone AND no email — can't reach them |

---

## 4. Website Enrichment

- **File**: `tools/enrichment.py`
- If the lead has a website, it's crawled before message generation
- Extracts: services offered, team names, about page copy, contact email, recent news
- If email found on website and Maps didn't return one → backfilled onto the contact
- Enrichment context passed into Claude's prompt for deeper personalisation

---

## 5. Message Generation

- **File**: `agent/brain.py` + `agent/prompts/{vertical}.txt`
- Claude (Sonnet) writes a unique message per contact using:
  - Business name, category, rating, address, website
  - Enrichment context (services, team names, etc.)
  - For social leads: the actual post that triggered discovery → post-aware opener
  - For `agency_sales`: rating-tier logic:
    - ≥ 4.2 stars → peer-level pitch ("you're already winning, let's scale")
    - 3.5–4.1 → reliability pitch ("turn potential into a predictable pipeline")
    - < 3.5 / unrated → pain-first pitch ("inconsistent leads, ReachNG fixes this")
- **Channels**: WhatsApp message or Email (subject + body)
- **Rules**: No parentheses, CTA always standalone sentence, never open with "I"

---

## 6. Send or Queue

### HITL Mode (Review before send)
- Drafts queued in `hitl_drafts` collection
- Appear in **Approvals tab** on dashboard
- You read each message, approve or edit before it sends
- Agency sales: queues BOTH WhatsApp + email drafts per contact (multi-channel)
- Owner notified via WhatsApp when drafts are ready

### Live Mode (Direct send)
- WhatsApp → Unipile API (per-client account) or Meta Cloud API
- Email → configured email account via Unipile
- Human-mimicry delay between sends: 45–210 seconds (randomised, weighted toward 60–120s) — prevents WhatsApp spam detection

---

## 7. Contact Recording

Every contacted business is saved to MongoDB `contacts` collection with:

| Field | Value |
|-------|-------|
| `place_id` | Unique identifier (Google place ID or `social_{platform}_{username}`) |
| `name` | Business name |
| `vertical` | Campaign vertical |
| `source` | `maps` / `apollo` / `social` |
| `platform` | `instagram` / `tiktok` / `twitter` / `facebook` (social only) |
| `status` | `not_contacted` → `contacted` → `replied` → `converted` / `opted_out` |
| `phone` | Normalised to +234 format |
| `email` | From Maps, Apollo, or website crawl |
| `rating` | Google Maps rating |
| `lead_score` | Computed score at discovery time |
| `client_name` | Which client this was run for (if agency mode) |
| `outreach_count` | Number of times messaged |

A/B test variant and ROI event are also logged per send.

---

## 8. Reply Handling

- **File**: `tools/reply_router.py`
- Incoming WhatsApp replies are routed through Claude for intent classification:
  - `interested` — hot lead, reply immediately
  - `question` — warm, has a specific ask
  - `referral` — warm, pointing to someone else
  - `not_now` — soft no, could follow up later
  - `opted_out` — hard no, auto-marked as opted out
- Contact status updated automatically on reply
- Hot leads surface at top of Replies tab with "REPLY NOW" flag

---

## 9. Dashboard — What You Can See

### Home Tab
- Total contacted, replied, converted, active clients
- **Source attribution pills**: Google Maps · Apollo · Instagram · TikTok · Twitter/X · Facebook
- Daily send limit progress bar
- ROI summary (value generated vs AI cost)
- Today's Work cards (hot leads, pending approvals, overdue invoices)

### Replies Tab
- All replies grouped by intent tier
- Each card shows: contact name, channel, vertical, reply text
- **Action buttons per reply**:
  - "Became Client" → marks `converted`, excluded from all future campaigns
  - "Mark Replied" → marks `replied`, excluded from re-contact
  - "Not Interested" → marks `opted_out`, never contacted again

### Approvals Tab
- Pending drafts for human review
- Source badge on each draft (Maps / Apollo / Instagram / TikTok / etc.)
- Approve, Edit, or Skip per draft

### Campaigns Tab
- **Run Campaign form**:
  - Vertical selector
  - Client name (optional — agency mode)
  - Max contacts (1–60)
  - City dropdown (Lagos default + 13 Nigerian cities)
  - Min rating filter (Any / 3.0+ / 3.5+ / 4.0+ / 4.2+ / 4.5+)
  - Dry run toggle
  - Review before send toggle
  - Sector picker (agency_sales only — 10 sectors)

### Clients Tab
- Client roster with portal links
- Full onboarding SOP (Step 0 through 5)
- Client record form: vertical, city, brief, Unipile account ID, Meta credentials

---

## 10. Follow-Ups

- **File**: `campaigns/base.py → run_followups()`
- Scheduler finds contacts that were messaged but never replied (after configured interval)
- Generates second-touch message (flagged as follow-up, different tone)
- Sends and records as attempt #2
- Human-mimicry delay applied between follow-up sends

---

## 11. Multi-Client (Agency Mode)

When `client_name` is provided in a campaign:
- Client brief loaded from `clients` collection → replaces generic vertical prompt
- Messages sent from **client's WhatsApp number** (via their Unipile Account ID or Meta credentials)
- City/cities pulled from client config if not overridden
- Portal link scoped to client's data only

---

## Environment Variables (Railway)

| Variable | Purpose | Status |
|----------|---------|--------|
| `GOOGLE_MAPS_API_KEY` | Google Places discovery | Active |
| `APOLLO_API_KEY` | Apollo.io B2B discovery | Active |
| `APIFY_API_TOKEN` | Social media discovery (all platforms) | Active |
| `ANTHROPIC_API_KEY` | Claude message generation | Active |
| `UNIPILE_API_KEY` | WhatsApp + email delivery | Active |
| `MONGODB_URI` | Contact + campaign database | Active |
| `DASHBOARD_USER` | Master dashboard login | Active |
| `DASHBOARD_PASS` | Master dashboard password | Active |
| `META_PHONE_NUMBER_ID` | Your own WhatsApp Business number | Pending setup |
| `META_ACCESS_TOKEN` | Meta Cloud API token | Pending setup |
| `OWNER_WHATSAPP` | Your number for system notifications | Optional |

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, all routes |
| `config.py` | All env var settings |
| `campaigns/base.py` | Core campaign loop |
| `campaigns/agency_sales.py` | ReachNG self-promotion vertical |
| `tools/discovery.py` | Google Maps discovery |
| `tools/apollo_discovery.py` | Apollo.io discovery |
| `tools/social.py` | Social media discovery (Apify) |
| `tools/enrichment.py` | Website crawl + data extraction |
| `tools/memory.py` | Contact upsert + pipeline stats |
| `tools/hitl.py` | Draft queue + approval flow |
| `tools/reply_router.py` | Incoming reply classification |
| `tools/scoring.py` | Lead quality scoring |
| `agent/brain.py` | Claude message generation |
| `agent/prompts/agency_sales.txt` | Agency sales pitch prompt |
| `api/campaigns.py` | Campaign run API endpoints |
| `api/clients.py` | Client management endpoints |
| `templates/dashboard.html` | Master dashboard UI |
| `docs/sales_playbook.md` | Sales playbook — yes to onboarded |
| `docs/system_flow.md` | This file |
