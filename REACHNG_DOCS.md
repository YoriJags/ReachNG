# ReachNG — Full System Documentation

> AI-powered outreach machine for Lagos businesses.
> Last updated: April 2026

---

## Table of Contents

1. [What ReachNG Does](#1-what-reachng-does)
2. [Tech Stack](#2-tech-stack)
3. [External APIs & Costs](#3-external-apis--costs)
4. [Verticals](#4-verticals)
5. [How a Campaign Works](#5-how-a-campaign-works)
6. [Lead Discovery Pipeline](#6-lead-discovery-pipeline)
7. [Social Media Tracking](#7-social-media-tracking)
8. [Client Architecture](#8-client-architecture)
9. [Unipile WhatsApp Setup](#9-unipile-whatsapp-setup)
10. [Client Pricing Tiers](#10-client-pricing-tiers)
11. [Dashboard & Portal](#11-dashboard--portal)
12. [Key Files](#12-key-files)
13. [Environment Variables](#13-environment-variables)
14. [Deployment](#14-deployment)
15. [Daily Limits & Safety](#15-daily-limits--safety)
16. [HITL — Human in the Loop](#16-hitl--human-in-the-loop)
17. [Invoice Collection](#17-invoice-collection)
18. [Reply Routing](#18-reply-routing)
19. [Morning Brief](#19-morning-brief)
20. [Scaling Roadmap](#20-scaling-roadmap)

---

## 1. What ReachNG Does

ReachNG finds businesses in Lagos (and any Nigerian city), writes personalised WhatsApp or email outreach messages using AI, sends them automatically, tracks replies, and classifies intent — all without human intervention.

It operates in two modes:
- **Own outreach** — you use it to grow your own client base
- **Agency mode** — you run it on behalf of paying clients, each with their own WhatsApp number, brief, and reporting portal

The core loop:
```
Find businesses → Score leads → Write personalised message →
Send via WhatsApp → Track replies → Classify intent → Follow up
```

---

## 2. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.12 + FastAPI | REST API, campaign runner, scheduler |
| **Database** | MongoDB Atlas | Contacts, replies, campaigns, invoices |
| **AI** | Anthropic Claude (claude-sonnet-4-6) | Message generation, reply classification |
| **Messaging** | Unipile API | WhatsApp delivery (per-client accounts) |
| **Scheduler** | APScheduler | Nightly campaigns, follow-ups, morning brief |
| **Deployment** | Railway | Cloud hosting, auto-deploy from GitHub |
| **Logging** | structlog | Structured JSON logs |
| **Lead Discovery** | Google Maps Places API | Business discovery |
| **B2B Data** | Apollo.io | Decision-maker contacts |
| **Social Scraping** | Apify | Instagram, TikTok, Twitter, Facebook |
| **Web Crawling** | httpx | Website enrichment for personalisation |
| **MCP Server** | FastMCP | Exposes tools to Claude for AI orchestration |

---

## 3. External APIs & Costs

### Google Maps Places API
- **What it does:** Finds real businesses by search query — returns name, phone, address, rating, website, category
- **Cost:** $5 per 1,000 requests (Text Search). A full campaign run uses ~8–10 requests per vertical
- **Estimated monthly cost:** $2–10 depending on run frequency
- **Account:** Sister's UK GCP account (Nigerian cards rejected by Google Billing)
- **Status:** ✅ Active — returns 20 results per query confirmed
- **Key env var:** `GOOGLE_MAPS_API_KEY`

### Anthropic Claude API
- **What it does:** Writes every outreach message, classifies reply intent, decides whether to contact a business
- **Model:** claude-sonnet-4-6 (fast, cheap, high quality)
- **Cost:** ~$0.003 per message generated (input + output tokens)
- **Estimated monthly cost:** $5–30 depending on volume
- **Key env var:** `ANTHROPIC_API_KEY`

### Unipile API
- **What it does:** Connects to WhatsApp accounts and sends messages on behalf of connected numbers
- **Cost:** ~$49–99/month base plan + per-account fees (~$10–20/account/month)
- **How it works:** Each WhatsApp number is connected via QR code scan. Unipile gives an `account_id` per connection
- **Key env var:** `UNIPILE_API_KEY`, `UNIPILE_DSN`

### Apollo.io
- **What it does:** B2B company database — finds businesses by industry + location
- **Current plan:** Free (organisation search only — no individual contacts or emails)
- **Upgrade:** $49/month for people search (decision-maker names + emails)
- **Key env var:** `APOLLO_API_KEY`

### Apify
- **What it does:** Scrapes Instagram, TikTok, Twitter, Facebook for warm leads
- **Actors used:**
  - `apify/instagram-scraper` — hashtag posts
  - `clockworks/tiktok-scraper` — hashtag videos
  - `apidojo/tweet-scraper` — Twitter/X search
  - `apify/facebook-posts-scraper` — Facebook page posts
- **Cost:** Free tier available. Paid plans from $5/month
- **Key env var:** `APIFY_API_TOKEN`

### MongoDB Atlas
- **What it does:** Stores all contacts, outreach logs, replies, clients, invoices, social signals
- **Cost:** Free tier (512MB) sufficient for ~50,000 contacts. M10 cluster (~$57/month) for scale
- **Key env var:** `MONGODB_URI`

### Railway
- **What it does:** Hosts the FastAPI server. Auto-deploys from GitHub main branch
- **Cost:** ~$5–20/month depending on usage
- **URL:** `https://reachng-production.up.railway.app`

---

## 4. Verticals

ReachNG targets 7 business verticals in Nigeria:

| Vertical | Key | Description |
|----------|-----|-------------|
| Real Estate | `real_estate` | Property agencies, developers, estate managers |
| Recruitment | `recruitment` | HR firms, staffing agencies, talent consultants |
| Events | `events` | Event planners, venues, corporate event organisers |
| Fintech | `fintech` | Microfinance banks, digital lenders, payment companies |
| Legal | `legal` | Law firms, corporate counsel, solicitors |
| Logistics | `logistics` | Haulage, freight, last-mile delivery companies |
| Agriculture | `agriculture` | Agribusiness, food processing, poultry, fish farms |

Each vertical has its own:
- Google Maps search queries (8 per vertical)
- Apollo.io keyword + title mappings
- Social media hashtags (Instagram, TikTok, Twitter, Facebook)
- Lead scoring categories
- Hook generator hashtags

---

## 5. How a Campaign Works

### Step-by-step flow

```
1. DISCOVER
   ├── Google Maps → finds SMEs by search query
   ├── Apollo.io → finds B2B orgs by industry/location
   └── Apify Social → finds warm leads from IG/TikTok/Twitter/FB

2. MERGE & DEDUPLICATE
   └── Deduplicate by phone + email across all 3 sources
       Social leads first (warmest), then Apollo, then Maps

3. SCORE & FILTER
   ├── Lead scoring (0–100): rating, has phone, has website, category match
   ├── Skip if already contacted (checked in MongoDB)
   └── Quality filter: Claude decides if worth contacting

4. ENRICH (optional)
   └── Crawl business website → extract about text, services, team names
       → feeds into Claude for hyper-personalised messages

5. GENERATE MESSAGE
   └── Claude writes personalised WhatsApp/email per business
       using: business name, category, rating, website, client brief, enrichment data

6. SEND OR QUEUE
   ├── HITL mode ON → message queued for human approval in dashboard
   └── HITL mode OFF → message sent immediately via Unipile

7. RECORD
   ├── Contact saved to MongoDB
   ├── Outreach logged with message text + timestamp
   ├── ROI event logged
   └── A/B test variant recorded

8. JITTER DELAY
   └── Random 45–210 second wait between messages (mimics human pace, avoids spam detection)
```

### Campaign settings

| Setting | Default | Description |
|---------|---------|-------------|
| `max_contacts` | 30 | How many businesses to contact per run |
| `dry_run` | true | Preview only — nothing sent, nothing saved |
| `hitl_mode` | false | Queue for approval instead of sending directly |
| `client_name` | null | Scopes campaign to a specific client's brief + WhatsApp |
| `query_override` | null | Custom Maps search query instead of defaults |

---

## 6. Lead Discovery Pipeline

### Google Maps (Primary)
- Uses Google Places Text Search API
- 8 search queries per vertical (e.g. "real estate agent Victoria Island Lagos")
- Returns: business name, phone, address, rating, website, place_id, category
- Max 20 results per query
- `place_id` used as unique identifier to prevent re-contacting

### Apollo.io (B2B Layer)
- Free plan: organisation search (`/mixed_companies/search`)
- Returns: company name, domain, industry, city
- No individual contacts or emails on free plan
- Upgrade to $49/month for decision-maker names + direct emails

### Apify Social (Warm Leads)
- Scrapes businesses already posting about their services
- These leads are self-identified — much higher open/reply rate
- Extracts phone/email/website from bios and captions via regex

---

## 7. Social Media Tracking

### How it works

Every social scrape saves a **signal** to MongoDB `social_signals` collection:
- `signal_id` — unique per post/profile (prevents duplicates)
- `platform` — instagram / tiktok / twitter / facebook
- `vertical` — which campaign found it
- `found_at` — timestamp
- `converted` — boolean (true when they become a paying contact)

### Platforms

| Platform | Actor | What we scrape | Status |
|----------|-------|----------------|--------|
| Instagram | `apify/instagram-scraper` | Hashtag posts → business accounts | Active with Apify token |
| TikTok | `clockworks/tiktok-scraper` | Hashtag videos → business creators | Active with Apify token |
| Twitter/X | `apidojo/tweet-scraper` | Intent-signalling tweets | Active with Apify token |
| Twitter/X | Twitter API v2 direct | Same, richer data | Requires $100/mo Twitter plan |
| Facebook | `apify/facebook-posts-scraper` | Business page posts | Active with Apify token |
| Competitor monitoring | `apidojo/tweet-scraper` | People asking about competitors | Active with Apify token |

### Deduplication
Two layers:
1. `signal_id` unique index in MongoDB — same post never processed twice
2. `place_id` dedup when merging with Maps + Apollo results

---

## 8. Client Architecture

ReachNG is built as a **multi-tenant agency platform**. You are the operator. Each client is isolated.

### Per-client isolation

| Feature | Your default | Per-client |
|---------|-------------|------------|
| WhatsApp number | Your number | Their own number (via Unipile) |
| Email account | Your email | Their email (via Unipile) |
| Campaign city | Lagos | Their city |
| AI message tone | Generic | Based on their brief |
| Reporting | Your dashboard | Their own portal link |
| Message attribution | Your name | Their business name |

### Client record fields

```
name                  — client business name
vertical              — which market they're in
brief                 — who they are, what they sell, target customer, tone
preferred_channel     — whatsapp or email
plan                  — starter / growth / agency
city                  — their target city (overrides Lagos default)
whatsapp_account_id   — Unipile account ID for their WhatsApp number
email_account_id      — Unipile account ID for their email
portal_token          — unique token for their reporting portal URL
active                — boolean
```

---

## 9. Unipile WhatsApp Setup

**CRITICAL — read this before running any live client campaign.**

Without a client-specific Unipile account ID, all messages send from YOUR personal WhatsApp number. This will get your number banned and damages your brand.

### Setup steps for each client

**Step 1 — Client needs a WhatsApp Business number**
- Can be their existing business phone
- Or a new SIM card dedicated to outreach
- WhatsApp Business app recommended (shows business name, description, hours)

**Step 2 — Connect to Unipile**
- Go to [app.unipile.com](https://app.unipile.com)
- Accounts → Add Account → Select WhatsApp
- Client scans QR code with their phone (takes 30 seconds)
- Their WhatsApp is now connected

**Step 3 — Get the Account ID**
- After connection, Unipile shows the account
- Copy the Account ID (format: `acc_xxxxxxxxxxxxxxxx`)

**Step 4 — Add to ReachNG**
- Go to ReachNG dashboard → Clients tab
- Find their client record or create new
- Paste Account ID into **Unipile WhatsApp Account ID** field
- Save

**Step 5 — Test**
- Run a dry run campaign with their client name
- Then run a live campaign with max_contacts = 1
- Confirm message arrives from their number, not yours

### Cost
- Unipile charges per connected account (~$10–20/month)
- Include this in their monthly plan fee
- At scale: client pays, you manage the connection

---

## 10. Client Pricing Tiers

| Plan | Setup Fee | Monthly Fee | Messages | Verticals |
|------|-----------|-------------|----------|-----------|
| **Starter** | ₦50,000 | ₦50,000/mo | 300 msgs | 1 vertical |
| **Growth** | ₦120,000 | ₦120,000/mo | 1,000 msgs | 3 verticals |
| **Agency** | ₦250,000 | ₦250,000/mo | Unlimited | All verticals |

### What's included in every plan
- AI-written personalised messages
- WhatsApp + email delivery
- Reply tracking and intent classification
- Client reporting portal
- Monthly lead export (CSV)
- Follow-up sequences

### Your cost per client (approximate)
- Claude API: ~$3–15/month depending on message volume
- Unipile per account: ~$10–20/month
- Google Maps: ~$1–5/month
- **Total platform cost per client: ~$15–40/month**
- **Margin on Starter plan: ~₦25,000–35,000/month**

---

## 11. Dashboard & Portal

### Operator Dashboard (`/dashboard`)
- Protected by HTTP Basic Auth (`DASHBOARD_USER` / `DASHBOARD_PASS`)
- **Overview tab** — Today's Work action cards, pipeline stats, ROI, social signals
- **Campaigns tab** — Run campaigns, dry run toggle, SOP guide
- **Clients tab** — Roster, onboarding flow, Unipile setup guide
- **Approvals tab** — Review and approve/edit/skip queued messages
- **Replies tab** — Priority-sorted inbox (hot leads at top), intent badges
- **Invoices tab** — AI payment reminder system
- **Tools tab** — CSV export, hook generator
- Auto-refreshes every 30 seconds

### Client Portal (`/portal/{token}`)
- No login required — token is the auth
- Shows: contacts reached, replies, conversions, ROI, activity feed, lead table
- Animated counters, luxury dark UI
- Each client gets a unique token via the dashboard

### Demo Portal (`/portal/demo`)
- Public — no auth
- Hardcoded sample data (Mercury Real Estate: 47 contacted, 12 replied, 3 converted)
- Use for pitch decks and investor demos

---

## 12. Key Files

```
ReachNG/
├── main.py                    — FastAPI app, routes, debug endpoints
├── config.py                  — Pydantic settings (all env vars)
├── auth.py                    — HTTP Basic Auth
├── scheduler.py               — APScheduler jobs (nightly, morning brief, follow-ups)
├── agent/
│   └── brain.py               — Claude message generation + quality filter
├── campaigns/
│   ├── base.py                — BaseCampaign: full run loop
│   ├── real_estate.py         — RealEstateCampaign
│   ├── recruitment.py         — RecruitmentCampaign
│   ├── events.py              — EventsCampaign
│   ├── fintech.py             — FintechCampaign
│   ├── legal.py               — LegalCampaign
│   ├── logistics.py           — LogisticsCampaign
│   └── agriculture.py         — AgricultureCampaign
├── api/
│   ├── campaigns.py           — POST /campaigns/run, /run-all, /followups
│   ├── contacts.py            — GET /contacts/pipeline, /replies, /export
│   ├── clients.py             — CRUD for client records
│   ├── portal.py              — Client portal + token generation
│   ├── approvals.py           — HITL approval queue
│   ├── roi.py                 — ROI summary endpoint
│   ├── social.py              — Social signal stats
│   ├── invoices.py            — Invoice CRUD + reminder trigger
│   ├── hooks.py               — Hook generator
│   ├── dashboard.py           — Dashboard HTML route
│   └── b2c.py                 — B2C CSV import campaigns
├── tools/
│   ├── discovery.py           — Google Maps Places API
│   ├── apollo_discovery.py    — Apollo.io org search
│   ├── social.py              — Instagram, TikTok, Twitter, Facebook scrapers
│   ├── messaging.py           — Unipile WhatsApp + email send
│   ├── memory.py              — Contact upsert, status updates, pipeline stats
│   ├── enrichment.py          — Website crawler for deep personalisation
│   ├── scoring.py             — Lead quality scoring (0–100)
│   ├── hitl.py                — Human-in-the-loop approval queue
│   ├── roi.py                 — ROI event logging + summary
│   ├── reply_router.py        — Fetches + classifies replies via Claude
│   ├── notifier.py            — Owner WhatsApp alerts
│   ├── invoices.py            — Invoice management + AI reminders
│   ├── hooks.py               — Content hook generator
│   ├── ab_testing.py          — A/B test variant tracking
│   ├── referral.py            — Referral tracking
│   ├── competitor.py          — Competitor monitoring
│   └── brief.py               — Morning brief compiler
├── templates/
│   ├── dashboard.html         — Operator dashboard (tabbed, dark UI)
│   ├── portal.html            — Client portal (luxury dark UI)
│   └── portal_demo.html       — Demo portal (hardcoded data)
├── database/
│   └── mongo.py               — MongoDB connection + index setup
├── mcp_server/
│   └── server.py              — MCP server (exposes tools to Claude)
├── requirements.txt           — Python dependencies
├── CLAUDE.md                  — Project context for AI assistant
└── REACHNG_DOCS.md            — This file
```

---

## 13. Environment Variables

Set all of these in Railway → Service → Variables.

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `MONGODB_URI` | ✅ | MongoDB Atlas connection string |
| `UNIPILE_API_KEY` | ✅ | Unipile API key |
| `UNIPILE_DSN` | ✅ | Unipile DSN (endpoint URL) |
| `GOOGLE_MAPS_API_KEY` | ✅ | Google Places API key |
| `DASHBOARD_USER` | ✅ (prod) | Dashboard Basic Auth username |
| `DASHBOARD_PASS` | ✅ (prod) | Dashboard Basic Auth password |
| `APOLLO_API_KEY` | ✅ | Apollo.io API key |
| `APIFY_API_TOKEN` | ✅ | Apify token (social scraping) |
| `APP_ENV` | ✅ | `production` or `development` |
| `DAILY_SEND_LIMIT` | optional | Max messages per day (default: 50) |
| `OWNER_WHATSAPP` | optional | Your number for system alerts |
| `TWITTER_BEARER_TOKEN` | optional | Twitter API v2 (requires $100/mo plan) |
| `APIFY_API_TOKEN` | optional | Unlocks IG/TikTok/Twitter/FB scraping |
| `APP_PORT` | optional | Server port (Railway sets this automatically) |

---

## 14. Deployment

### Platform: Railway
- Auto-deploys from GitHub `main` branch on every push
- Build: Nixpacks (detects Python automatically)
- Start command: `python main.py`
- Health check: `GET /health` → returns `{"status": "ok", "db": true}`
- URL: `https://reachng-production.up.railway.app`

### Debug endpoints (Basic Auth required)
| Endpoint | Purpose |
|----------|---------|
| `GET /health` | DB connectivity check |
| `GET /debug/maps` | Test Google Maps API key |
| `GET /debug/apollo` | Test Apollo API key |
| `GET /debug/apify` | Test Apify token (TikTok scraper) |
| `GET /docs` | FastAPI auto-generated API docs |

### Updating the system
1. Edit code locally in `c:\VIIBE\ReachNG\`
2. `git add . && git commit -m "your message" && git push`
3. Railway detects the push and auto-redeploys (takes ~2 minutes)
4. Hard refresh dashboard: `Ctrl + Shift + R`

---

## 15. Daily Limits & Safety

### Why limits exist
WhatsApp bans numbers that send too many messages too fast. ReachNG is designed to look human.

### Protections built in
- **Daily send limit:** 50 messages/day by default (configurable via `DAILY_SEND_LIMIT`)
- **Human jitter:** Random 45–210 second delay between each message (weighted toward 60–120s)
- **Per-contact dedup:** Never contacts the same business twice (checked via `place_id`)
- **Quality filter:** Claude scores each business before contacting (avoids obvious misfits)
- **Opt-out tracking:** Replied "stop" → marked `opted_out` → never contacted again

### Scheduler (automatic runs)
- **Nightly outreach:** Runs all verticals automatically each night
- **Follow-ups:** Re-contacts businesses that didn't reply after X days
- **Morning brief:** Sends overnight summary to your WhatsApp at 8am Lagos time
- **Invoice reminders:** Fires payment reminders on due dates

---

## 16. HITL — Human in the Loop

HITL mode queues every generated message for human review before sending.

### When to use it
- First week with a new client — review all messages before they go out
- High-value verticals (legal, fintech) — tone must be perfect
- Any time you're unsure about message quality

### How it works
1. Campaign runs with `hitl_mode=true`
2. Messages saved to `approvals` collection instead of being sent
3. Dashboard → Approvals tab shows all pending drafts
4. You read each message → Approve & Send / Edit / Skip
5. On approval, Unipile sends the message

### Current status
HITL mode is built and working but not yet exposed as a toggle in the dashboard Run Campaign form. It can be triggered via API directly: `POST /api/v1/campaigns/run` with `{"hitl_mode": true}`.

---

## 17. Invoice Collection

ReachNG includes an AI-powered payment reminder system for your clients to collect from their own debtors.

### How it works
1. Add an invoice (debtor name, phone, amount, due date)
2. ReachNG sends automatic WhatsApp reminders on your configured schedule
3. Tone escalates automatically: Polite → Firm → Payment Plan → Final Notice
4. Mark as Paid when collected

### Reminder schedule (recommended)
- Day 0: Polite reminder (due today)
- Day 5: Firm reminder (5 days overdue)
- Day 10: Payment plan offer
- Day 20: Final notice

### Upsell opportunity
Offer invoice collection as an add-on service to clients. They give you their debtors' numbers and you collect on their behalf.

---

## 18. Reply Routing

ReachNG automatically polls Unipile every few minutes for new WhatsApp replies.

### Reply classification (via Claude)
Every reply is classified into one of:

| Intent | Meaning | Action |
|--------|---------|--------|
| `interested` | "Tell me more", "How does this work?" | Reply within 2 hours — hot lead |
| `referral` | "Talk to my colleague/friend" | Follow up with referred contact |
| `question` | Asking about pricing, process, etc. | Answer within 24 hours |
| `not_now` | "Maybe later", "Not at the moment" | Follow up in 30 days |
| `opted_out` | "Stop messaging me", "Remove me" | Never contact again |
| `unknown` | Unclear | Review manually |

### Hot lead alerts
When an `interested` reply comes in and `OWNER_WHATSAPP` is set, ReachNG sends you an immediate WhatsApp alert so you never miss a hot lead.

---

## 19. Morning Brief

Every day at 8am Lagos time, ReachNG sends a WhatsApp message to `OWNER_WHATSAPP` with:
- Overnight social signals found (Instagram, TikTok, Twitter, Facebook)
- New replies received and their intents
- Pending approval count
- 30-day ROI summary
- Per-vertical pipeline snapshot

Requires `OWNER_WHATSAPP` to be set in Railway env vars.

---

## 20. Scaling Roadmap

### When you have 5 clients
- Upgrade Apollo to $49/month → get decision-maker emails → add email outreach channel
- Each client on their own Unipile account
- Consider dedicated MongoDB M10 cluster ($57/month)

### When you have 20 clients
- Hire a VA to manage approvals and hot lead responses
- The dashboard is designed for handoff — SOPs on every tab
- Consider Twitter API v2 Basic ($100/month) for richer Twitter data

### When you have 50+ clients
- Add LinkedIn scraping (Sales Navigator integration)
- Build client self-service onboarding (they scan QR themselves)
- Add CRM integration (HubSpot or Pipedrive webhook)
- WhatsApp Business API (Meta direct) for higher limits at scale

### Features already built, not yet active
- **A/B testing** — message variant tracking is logged, analysis UI pending
- **Referral tracking** — referral events logged, leaderboard pending
- **Competitor monitoring** — signals saved, dashboard view pending
- **Deep personalisation** — website crawling built in `tools/enrichment.py`

---

*Built by Oluwaseun Ajagun. Powered by Claude, Unipile, MongoDB, and Railway.*
