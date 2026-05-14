---
tags: [reachng]
---
# Ops

[[Home]] | [[Integrations]] | [[API Reference]]

---

## Deployment

- **Platform:** Railway
- **Repo:** GitHub `main` branch → auto-deploy on push
- **Live URL:** `https://www.reachng.ng`
- **GCP Project:** `reachng-492121` (Google Maps billing)

---

## Railway Environment Variables

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | ✓ | Claude API |
| `MONGODB_URI` | ✓ | MongoDB Atlas connection string |
| `UNIPILE_API_KEY` | ✓ | WhatsApp delivery |
| `UNIPILE_DSN` | ✓ | Unipile DSN endpoint |
| `UNIPILE_WHATSAPP_ACCOUNT_ID` | ✓ | Default WhatsApp account |
| `UNIPILE_EMAIL_ACCOUNT_ID` | ✓ | Email account |
| `GOOGLE_MAPS_API_KEY` | ✓ | Places API (billing currently blocked) |
| `APOLLO_API_KEY` | optional | B2B discovery |
| `GEMINI_API_KEY` | optional | Cheap extraction (get free from Google AI Studio) |
| `DASHBOARD_USER` | prod required | Basic Auth username |
| `DASHBOARD_PASS` | prod required | Basic Auth password |
| `APIFY_API_TOKEN` | optional | TikTok scraping |
| `POSTHOG_API_KEY` | optional | Analytics |
| `OWNER_WHATSAPP` | optional | Owner notifications |
| `SLACK_WEBHOOK_URL` | optional | Slack notifications |
| `ALLOWED_ORIGINS` | prod recommended | CORS (comma-separated) |
| `APP_ENV` | optional | `development` or `production` |

---

## Common Issues

### Deployment broken — ModuleNotFoundError
- Check import paths. WhatsApp send is in `tools/outreach.py`, not `tools/messaging.py`
- CLAUDE.md has a stale reference to `tools/messaging.py` — ignore it

### Google Maps returns no results
- Billing is blocked (Nigerian card rejected). Check `/debug/maps` endpoint
- Fix: add UK card to GCP project `reachng-492121` or get added as Billing Account Admin

### Apollo returns no orgs
- Check API key is set: `GET /debug/apollo`
- Free plan only returns org-level data — no emails until $49/mo upgrade

### First live campaign shows 0 results
- Only dry runs have been run. Run a live campaign: Campaigns tab → uncheck Dry Run → Run

---

## Monitoring

- **Health check:** `GET /health` — MongoDB ping
- **API analytics:** PostHog middleware captures all `/api/` requests (requires `POSTHOG_API_KEY`)
- **Logs:** structlog JSON logs in Railway dashboard

---

## Local Development

```bash
cd ReachNG
cp .env.example .env  # fill in your keys
pip install -r requirements.txt
python main.py
# App runs on http://localhost:8000
```

---

## Adding a New Client

1. Dashboard → Clients tab → Add Client
2. Fill: name, vertical, city, Unipile account ID
3. System generates portal token automatically
4. Share portal link: `https://www.reachng.ng/portal/{token}`
5. Client can view their campaign stats, contacts, replies at that link
