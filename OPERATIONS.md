# ReachNG — Operations Guide (A–Z)

Complete reference for running ReachNG as a managed outreach service.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [First-Time Setup](#2-first-time-setup)
3. [Environment Variables](#3-environment-variables)
4. [Dashboard Walkthrough](#4-dashboard-walkthrough)
5. [Onboarding a Client](#5-onboarding-a-client)
6. [Running a Campaign](#6-running-a-campaign)
7. [Approving Messages (HITL)](#7-approving-messages-hitl)
8. [Handling Replies](#8-handling-replies)
9. [Follow-ups](#9-follow-ups)
10. [Exporting Contacts](#10-exporting-contacts)
11. [Client Portal](#11-client-portal)
12. [A/B Testing](#12-ab-testing)
13. [Referral Tracking](#13-referral-tracking)
14. [Competitor Monitoring](#14-competitor-monitoring)
15. [ROI Reporting](#15-roi-reporting)
16. [Scheduler (Automated Jobs)](#16-scheduler-automated-jobs)
17. [Daily Operating Routine](#17-daily-operating-routine)
18. [Pricing & Billing](#18-pricing--billing)
19. [Troubleshooting](#19-troubleshooting)
20. [API Reference](#20-api-reference)

---

## 1. System Overview

ReachNG is an AI-powered outreach machine. It:

1. **Discovers** businesses in Lagos via Google Maps Places API
2. **Scores** each lead 0–100 (rating, phone, website, category)
3. **Generates** a personalised WhatsApp or email message using Claude AI
4. **Queues** drafts for your approval (HITL mode) or sends directly
5. **Tracks** every reply, classifies intent, and triggers follow-ups automatically

**Stack:** FastAPI · MongoDB · Claude (Anthropic) · Unipile (WhatsApp + Email) · Railway

**Live URL:** `https://www.reachng.ng`

**Dashboard:** `https://www.reachng.ng/dashboard`

**API Docs:** `https://www.reachng.ng/docs`

---

## 2. First-Time Setup

### Deploy to Railway
The app is already deployed. If you need to redeploy:
- Push to `main` branch on GitHub — Railway auto-deploys
- Do NOT manually set `PORT` in Railway Variables — Railway injects it

### Required Environment Variables (Railway → Variables)
See Section 3 for full list.

### Check the app is running
```
GET /health
→ { "status": "ok", "db": true }
```

---

## 3. Environment Variables

Set these in Railway → your service → Variables:

| Variable | Description | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude AI API key | Yes |
| `GOOGLE_MAPS_API_KEY` | Google Maps Places API key (billing must be enabled) | Yes |
| `UNIPILE_API_KEY` | Unipile API key | Yes |
| `UNIPILE_DSN` | Unipile DSN (e.g. `api4.unipile.com:13465`) | Yes |
| `UNIPILE_WHATSAPP_ACCOUNT_ID` | Your WhatsApp account ID in Unipile | Yes |
| `UNIPILE_EMAIL_ACCOUNT_ID` | Your email account ID in Unipile | Yes |
| `MONGODB_URI` | MongoDB connection string | Yes |
| `MONGODB_DB_NAME` | Database name (default: `reachng`) | No |
| `DAILY_SEND_LIMIT` | Max messages per day (default: `50`) | No |
| `FOLLOWUP_DELAY_HOURS` | Hours before follow-up is triggered (default: `48`) | No |
| `OWNER_WHATSAPP` | Your phone in E.164 format for notifications (e.g. `+2348012345678`) | No |
| `APP_ENV` | `production` or `development` | No |
| `LOG_LEVEL` | `INFO` or `DEBUG` | No |

**Never set `PORT`** — Railway injects this automatically.

---

## 4. Dashboard Walkthrough

Go to `/dashboard`. Sections from top to bottom:

| Section | What it does |
|---|---|
| **Pipeline Summary** | Live counts: Contacted / Replied / Converted / Opted Out |
| **Recent Replies** | Latest inbound replies from WhatsApp/email |
| **Approvals Queue** | Drafts waiting for your review before sending |
| **Run Campaign** | Manually trigger a campaign for any vertical |
| **Client Onboarding** | 3-step flow to add a new client |
| **Export Contacts** | Download CSV of all contacts (filterable) |
| **Hook Generator** | AI-generated content hooks for social media |

The dashboard auto-refreshes every 30 seconds. You can also press the refresh button.

---

## 5. Onboarding a Client

Use the **Client Onboarding** section on the dashboard.

### Step 1 — Create Brief
Fill in:
- **Client name** — e.g. "Mercury Lagos"
- **Vertical** — which industry they're in
- **Channel** — WhatsApp or Email
- **Plan** — Starter / Growth / Agency
- **Brief** — the most important field. Write who they are, what they sell, their tone, and their target customer.

**Good brief example:**
> Mercury Lagos is a luxury property agency on Victoria Island, Lagos. We sell high-end apartments and duplexes from ₦50M upwards. Our tone is professional, warm, and confident. Target clients: high-net-worth individuals, diaspora buyers, and property investors. We do not target first-time buyers or budgets below ₦30M.

Click **Save Client**. The brief is saved and Steps 2 & 3 are auto-filled.

### Step 2 — Generate Portal Link
Click **Generate Portal**. A unique URL is generated for this client — e.g.:
```
https://www.reachng.ng/portal/abc123xyz
```
Copy and send this link to the client. No login needed — the token in the URL is the auth.

### Step 3 — Run First Campaign
- Select the vertical and max contacts
- Leave **Dry run** ticked for the first run — preview the messages before sending live
- Click **Run**

---

## 6. Running a Campaign

### From the Dashboard
Use the **Run Campaign** panel:
- Pick vertical
- Set max contacts (10–60)
- Toggle Dry run on/off
- Click Run

### From the API
```http
POST /api/v1/campaigns/run
{
  "vertical": "real_estate",
  "max_contacts": 30,
  "dry_run": false,
  "client_name": "Mercury Lagos"   ← optional, for agency mode
}
```

### What happens during a run
1. Google Maps is queried for businesses matching the vertical
2. Social media leads are also pulled (if Apify/Twitter tokens configured)
3. Leads are scored 0–100 — highest scored contacted first
4. Already-contacted businesses are skipped
5. A personalised message is generated per lead
6. If HITL mode: drafts queued for approval
7. If live mode: messages sent immediately via Unipile
8. All activity is recorded in MongoDB

### Verticals available
`real_estate` · `recruitment` · `events` · `fintech` · `legal` · `logistics`

### Daily send limit
Default: 50 messages/day. Change via `DAILY_SEND_LIMIT` env var.
Check remaining: `GET /api/v1/campaigns/daily-limit`

---

## 7. Approving Messages (HITL)

HITL = Human In The Loop. This is the recommended mode — every message is reviewed by you before sending.

### Enable HITL
Pass `hitl_mode: true` in the campaign run request, or trigger via the scheduler (default for automated runs).

### Approvals Queue on Dashboard
Each draft shows:
- Business name
- Vertical
- Channel (WhatsApp/Email)
- The generated message
- Source (Google Maps or Social)

Actions:
- **Approve** → message sends immediately
- **Edit** → modify the text, then approve
- **Reject** → skip this contact entirely

### API
```http
GET  /api/v1/approvals/pending          ← list all pending drafts
POST /api/v1/approvals/{id}/approve     ← approve and send
POST /api/v1/approvals/{id}/edit        ← { "message": "..." } update text
POST /api/v1/approvals/{id}/reject      ← skip this contact
```

---

## 8. Handling Replies

Replies are polled from Unipile every 60 seconds by the scheduler.

### Viewing replies
Dashboard → **Recent Replies** section.
Or: `GET /api/v1/contacts/replies`

### Reply classification
Claude AI classifies every reply into:
- `interested` — warm lead, follow up immediately
- `not_now` — reschedule follow-up
- `opted_out` — never contact again
- `referral` — they mentioned someone else → creates a new lead
- `unmatched` — couldn't be matched to a contact

### Updating contact status manually
```http
PATCH /api/v1/contacts/{id}/replied
PATCH /api/v1/contacts/{id}/converted
PATCH /api/v1/contacts/{id}/opted-out
```

---

## 9. Follow-ups

The scheduler runs follow-ups automatically at 48 hours (configurable via `FOLLOWUP_DELAY_HOURS`).

### Manual follow-up run
```http
POST /api/v1/campaigns/{vertical}/followups?dry_run=false
```

### Rules
- Only contacts with status `contacted` and no reply qualify
- Max 2 follow-up attempts (configurable via `MAX_FOLLOWUP_ATTEMPTS`)
- Follow-up messages are generated differently — lighter touch, references the first message

---

## 10. Exporting Contacts

Dashboard → **Export Contacts** section.

Filter by:
- Vertical (or all)
- Status (New / Contacted / Replied / Converted / Opted Out)

Click **Download CSV**. Open in Google Sheets via **File → Import**.

Fields exported: name, vertical, status, phone, email, website, address, category, rating, lead_score, outreach_count, last_contacted_at, created_at.

### API
```http
GET /api/v1/contacts/export?vertical=real_estate&status=replied
```

---

## 11. Client Portal

Each client gets a private read-only dashboard.

### Generate the link
```http
POST /api/v1/portal/generate/Mercury Lagos
→ { "portal_url": "/portal/abc123xyz" }
```

Or use Step 2 of the Client Onboarding panel on the dashboard.

### What clients see
- Their contacts (scoped to their vertical)
- Pipeline stats (Contacted / Replied / Converted)
- ROI summary (value generated vs API cost)
- Lead scores and contact details

### Sharing
Send the full URL: `https://www.reachng.ng/portal/abc123xyz`
The token in the URL is the only authentication needed.

---

## 12. A/B Testing

Every message sent is randomly assigned Variant A or B. Over time, you can see which message style converts better.

### View results
```http
GET /api/v1/ab/stats?vertical=real_estate&days=30
→ {
    "A": { "sent": 45, "replied": 8, "reply_rate": 17.8 },
    "B": { "sent": 47, "replied": 12, "reply_rate": 25.5 },
    "winner": "B"
  }
```

Use the winning variant's style to inform future message briefs.

---

## 13. Referral Tracking

When a contact says "speak to my colleague" or refers someone, log it:

```http
POST /api/v1/referrals/
{
  "referrer_client_name": "Mercury Lagos",
  "referred_client_name": "Apex Properties",
  "notes": "Mercury referred via WhatsApp reply"
}
```

When the referred client converts:
```http
POST /api/v1/referrals/{id}/convert
```

When the reward is issued (1 free month):
```http
POST /api/v1/referrals/{id}/reward
```

View pipeline: `GET /api/v1/referrals/stats`

---

## 14. Competitor Monitoring

Discover competing outreach/marketing agencies in Lagos:

```http
POST /api/v1/competitors/discover?max_results=30
```

Runs in the background. View results:
```http
GET /api/v1/competitors/
```

Use this to:
- Know who else is targeting your verticals
- Identify their weaknesses from Google Maps reviews
- Position ReachNG against them in client pitches

---

## 15. ROI Reporting

Every message sent logs an ROI event comparing:
- **Manual cost:** ₦2,000 (one cold call equivalent)
- **API cost:** ₦15 (Claude + Unipile per message)

### View ROI
```http
GET /api/v1/roi/summary?days=30
→ {
    "messages_sent": 120,
    "manual_equivalent_ngn": 240000,
    "api_cost_ngn": 1800,
    "value_generated_ngn": 238200,
    "roi_percent": 13233,
    "roi_label": "₦238,200 generated for ₦1,800 spent — 13233x ROI"
  }
```

This is your **key sales number** when pitching clients. Print it. Show it.

---

## 16. Scheduler (Automated Jobs)

The scheduler runs automatically on startup. Jobs:

| Job | Schedule | What it does |
|---|---|---|
| `reply_poll` | Every 60 seconds | Checks Unipile for new replies, classifies them |
| `nightly_outreach` | 10:00 PM Lagos (WAT) | Runs all 6 verticals in HITL mode |
| `morning_brief` | 8:00 AM Lagos (WAT) | Sends owner a WhatsApp summary of yesterday's results |
| `followup_run` | 9:00 AM Lagos (WAT) | Sends follow-up messages to contacts due for a second touch |

All times are West Africa Time (UTC+1).

---

## 17. Daily Operating Routine

### Morning (5 minutes)
1. Open `/dashboard`
2. Check **Recent Replies** — any warm leads? Act on them immediately
3. Check **Approvals Queue** — approve or edit overnight drafts
4. Check pipeline stats — how many contacted / replied / converted?

### Evening (optional — automated)
The nightly job runs at 10 PM automatically. You'll get a WhatsApp notification (if `OWNER_WHATSAPP` is set) when drafts are ready.

### Weekly
1. `GET /api/v1/roi/summary?days=7` — review ROI for the week
2. `GET /api/v1/ab/stats?days=7` — check which message variant is winning
3. Export contacts CSV for any active clients
4. Review competitor discovery: `GET /api/v1/competitors/`

---

## 18. Pricing & Billing

### Plans

| Plan | Setup Fee | Monthly | Included |
|---|---|---|---|
| **Starter** | ₦50,000 | ₦50,000/mo (from month 2) | 300 messages/mo · 1 vertical · WhatsApp |
| **Growth** | ₦120,000 | ₦120,000/mo | 1,000 messages/mo · 3 verticals · WhatsApp + Email + follow-ups |
| **Agency** | ₦250,000 | ₦250,000/mo | Unlimited · All 6 verticals · Dedicated pipeline · ROI reporting |

**Setup fee = first month free.** Client pays setup fee once, month 1 is complimentary, billing starts month 2.

### Referral reward
Any client who refers a paying client gets **1 month free** on their next billing cycle. Log via `POST /api/v1/referrals/`.

---

## 19. Troubleshooting

### Dashboard shows no contacts / all zeros
- Google Maps billing is not active. Go to Google Cloud Console → Billing → enable a payment method. The Places API requires an active billing account.

### Messages not sending (WhatsApp)
- Check Unipile dashboard — is the WhatsApp account still connected?
- WhatsApp accounts can disconnect if the phone goes offline. Re-scan QR in Unipile.

### Railway deployment failed
- Check Railway deploy logs
- Do NOT set `PORT` manually in Railway Variables — delete it if present
- Run `GET /health` after deploy to confirm DB is connected

### Replies not appearing
- Reply poll runs every 60 seconds — wait up to 1 minute
- Check `GET /api/v1/contacts/replies` directly
- Manually trigger: `POST /api/v1/contacts/replies/sync`

### Campaign returns count=0
- Google Maps billing is the most common cause
- Test directly: `GET https://maps.googleapis.com/maps/api/place/textsearch/json?query=real+estate+Lagos&key=YOUR_KEY`
- If it returns `REQUEST_DENIED` → billing issue

### App starts but immediately crashes
- Check that all required env vars are set in Railway
- Missing `ANTHROPIC_API_KEY`, `MONGODB_URI`, `UNIPILE_API_KEY`, `UNIPILE_DSN`, `UNIPILE_WHATSAPP_ACCOUNT_ID`, or `UNIPILE_EMAIL_ACCOUNT_ID` will crash on startup

---

## 20. API Reference

Base URL: `https://www.reachng.ng/api/v1`

Full interactive docs: `/docs` (Swagger UI)

### Campaigns
| Method | Endpoint | Description |
|---|---|---|
| POST | `/campaigns/run` | Run a campaign |
| POST | `/campaigns/run-all` | Run all verticals |
| POST | `/campaigns/{vertical}/followups` | Send follow-ups |
| GET | `/campaigns/stats` | Pipeline stats |
| GET | `/campaigns/daily-limit` | Daily send usage |

### Contacts
| Method | Endpoint | Description |
|---|---|---|
| GET | `/contacts/` | List contacts (filterable) |
| GET | `/contacts/export` | Download CSV |
| GET | `/contacts/pipeline` | Status counts per vertical |
| GET | `/contacts/replies` | Recent inbound replies |
| POST | `/contacts/replies/sync` | Force reply poll |
| PATCH | `/contacts/{id}/replied` | Mark replied |
| PATCH | `/contacts/{id}/converted` | Mark converted |
| PATCH | `/contacts/{id}/opted-out` | Mark opted out |

### Clients
| Method | Endpoint | Description |
|---|---|---|
| GET | `/clients/` | List all clients |
| POST | `/clients/` | Create/update client |
| GET | `/clients/{name}` | Get client by name |
| DELETE | `/clients/{name}` | Deactivate client |

### Portal
| Method | Endpoint | Description |
|---|---|---|
| POST | `/portal/generate/{name}` | Generate portal link |
| GET | `/portal/{token}` | Client portal dashboard |
| GET | `/portal/data/{token}` | Portal data (JSON) |

### Approvals
| Method | Endpoint | Description |
|---|---|---|
| GET | `/approvals/pending` | List pending drafts |
| POST | `/approvals/{id}/approve` | Approve and send |
| POST | `/approvals/{id}/edit` | Edit draft text |
| POST | `/approvals/{id}/reject` | Reject draft |

### ROI
| Method | Endpoint | Description |
|---|---|---|
| GET | `/roi/summary` | ROI for last N days |
| GET | `/roi/by-vertical` | ROI breakdown by vertical |

### A/B Testing
| Method | Endpoint | Description |
|---|---|---|
| GET | `/ab/stats` | Compare variant A vs B reply rates |
| POST | `/ab/replied/{contact_id}` | Mark variant as replied |

### Referrals
| Method | Endpoint | Description |
|---|---|---|
| POST | `/referrals/` | Log a referral |
| POST | `/referrals/{id}/convert` | Mark converted |
| POST | `/referrals/{id}/reward` | Mark rewarded |
| GET | `/referrals/stats` | Referral pipeline summary |
| GET | `/referrals/` | List all referrals |

### Competitors
| Method | Endpoint | Description |
|---|---|---|
| POST | `/competitors/discover` | Trigger competitor discovery |
| GET | `/competitors/` | List known competitors |

---

*ReachNG · Built by Oluwaseun Oluyori Ajagun · Lagos, Nigeria*
