# Integrations

[[Home]] | [[Architecture]] | [[Ops]]

---

## Anthropic Claude

- **Use:** Outreach message generation, reply classification
- **Models:**
  - `claude-sonnet-4-6` — primary outreach writing
  - `claude-haiku-4-5-20251001` — cheap classification, fallback extraction
- **Key file:** `agent/brain.py`
- **Env var:** `ANTHROPIC_API_KEY`
- **Cost note:** Sonnet for writing, Haiku for cheap tasks — never use Sonnet for extraction

---

## Gemini Flash

- **Use:** PDF invoice parsing, cheap data extraction (90% of extraction load)
- **Model:** `gemini-1.5-flash`
- **Key file:** `agent/brain.py` → `extract_with_gemini()`
- **Env var:** `GEMINI_API_KEY` (optional — falls back to Claude Haiku)
- **Cost:** ~10x cheaper than Claude for extraction tasks
- **Endpoint:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent`
- **Get key:** Google AI Studio (free tier available)

---

## Unipile

- **Use:** WhatsApp message delivery + inbound reply handling
- **Key file:** `tools/outreach.py` → `send_whatsapp(phone, message, account_id)`
- **Env vars:** `UNIPILE_API_KEY`, `UNIPILE_DSN`, `UNIPILE_WHATSAPP_ACCOUNT_ID`
- **Per-client:** Each client has their own `account_id` — messages come from their number
- **Retry:** 3 attempts with exponential backoff built in
- **Jitter:** 45–210s human-mimicry delay (anti-ban)
- **Cost:** ~$10–20/month per client account
- **Status:** Active ✓

---

## Google Maps (Places API)

- **Use:** SME discovery by vertical + city
- **Key file:** `tools/discovery.py`
- **Env var:** `GOOGLE_MAPS_API_KEY`
- **Debug:** `GET /debug/maps`
- **Status:** ✓ Active — confirmed 2026-04-12, returns 20 results per query

---

## Apollo.io

- **Use:** B2B org/people discovery
- **Key file:** `tools/apollo_discovery.py`
- **Env var:** `APOLLO_API_KEY`
- **Free plan:** `/mixed_companies/search` — org data only, no emails
- **Paid ($49/mo):** `/mixed_people/search` — decision-maker contacts + emails
- **Debug:** `GET /debug/apollo`
- **Status:** Active ✓

---

## MongoDB

- **Use:** All persistence — contacts, campaigns, clients, approvals, invoices, replies
- **Env vars:** `MONGODB_URI`, `MONGODB_DB_NAME` (default: `reachng`)
- **Collections:** contacts, campaigns, clients, approvals, roi_events, social_leads, ab_tests, referrals, competitor_intel, invoices, b2c_contacts, chased_invoices
- **Status:** Active ✓

---

## Apify

- **Use:** TikTok scraping for social lead discovery
- **Env var:** `APIFY_API_TOKEN`
- **Actor:** `clockworks/tiktok-scraper`
- **Debug:** `GET /debug/apify`
- **Status:** Optional — only needed for social vertical

---

## PostHog

- **Use:** Product analytics — API requests, server start events
- **Env vars:** `POSTHOG_API_KEY`, `POSTHOG_HOST`
- **Middleware:** `posthog_request_middleware` captures every `/api/` request
- **Status:** Optional — wired but requires key

---

## NOT integrated (decisions)

| Service | Why not |
|---------|---------|
| Twilio | Unipile already handles WhatsApp better |
| Meta Official WhatsApp API | Requires business verification, slow approval |
| Instagram scraping | ToS violation — brittle |
| Firebase | MongoDB is sufficient |
