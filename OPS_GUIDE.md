# ReachNG — Ops Guide (Non-Technical)

Your plain-English guide to keeping ReachNG healthy. Check this once a week.

---

## Your 3 dashboards

| Dashboard | URL | What it shows |
|-----------|-----|---------------|
| **ReachNG Admin** | https://reachng.up.railway.app/dashboard | Your leads, drafts, clients, everything |
| **Railway** | https://railway.app → your project | Server health, memory, logs |
| **MongoDB Atlas** | https://cloud.mongodb.com | Database storage and connections |

---

## Weekly health check (10 minutes every Monday)

### 1. Railway — is the server healthy?

1. Go to railway.app → open your ReachNG project
2. Click the service → click **Metrics** tab
3. Check **Memory** — should be under 400MB. If it's consistently above that, message me.
4. Check **Deployments** — the latest should say "Active". If it says "Failed", message me with a screenshot.

### 2. MongoDB Atlas — is the database healthy?

1. Go to cloud.mongodb.com → your cluster
2. Click **Metrics** tab
3. Check **Connections** — should be under 400. Over that, message me.
4. Check **Storage** — should be under 400MB. Over that, message me.
5. If you see any red warnings on the cluster overview page, message me.

### 3. ReachNG Admin — is the queue healthy?

1. Go to your dashboard → **Message Queue** tab
2. If there are more than 50 drafts sitting there unreviewed, work through them or turn on Autopilot for low-risk clients.
3. Go to **Control Tower** tab → check that all clients show green payment status.

---

## Actions only you can do (not automated)

### Add the Apify token to Railway (do this once)
This unlocks lead enrichment — currently coded but inactive.

1. Go to railway.app → ReachNG project → **Variables** tab
2. Click **New Variable**
3. Name: `APIFY_API_TOKEN`
4. Value: (your Apify token from apify.com → Settings → API tokens)
5. Click Save → Railway will restart the server automatically (takes ~60 seconds)

### Warm up a new client WhatsApp number
When you connect a new client's WhatsApp via Unipile, don't blast 50 messages on day 1. WhatsApp will ban the number.

- **Week 1:** max 10 messages/day
- **Week 2:** max 25 messages/day
- **Week 3+:** up to 50 messages/day (the default limit in the system)

To set a temporary lower limit:
Go to Admin → Control Tower → find the client → Edit → set `daily_send_limit` to 10.
Change it to 25 after a week, then remove the override after two weeks.

---

## When to call me (message in this chat)

| What you see | What it means |
|-------------|---------------|
| Railway memory above 400MB for 2+ days | Server under strain — needs a fix |
| MongoDB connections above 400 | Too many simultaneous processes — needs a fix |
| Message Queue not clearing (drafts stuck) | Unipile or WhatsApp issue — needs investigation |
| Dashboard not loading | Server down — message me immediately with the error |
| Client says their WhatsApp stopped sending | Number may be banned — message me with client name |
| 7am brief stops arriving on your WhatsApp | Scheduler broke — message me |

---

## Cost checkpoints

Check these once a month:

| Service | Where | What to check |
|---------|-------|---------------|
| Anthropic (Claude API) | console.anthropic.com → Usage | Monthly spend. Should be under $10 until 10+ active clients |
| Railway | railway.app → Billing | Monthly usage. Free tier lasts a while; pro is ~$20/mo |
| Unipile | your Unipile dashboard | Per-account charges for each connected WhatsApp |
| MongoDB Atlas | cloud.mongodb.com → Billing | Free tier until you hit 512MB storage |

---

## Scaling milestones — what changes when

| Clients | Action needed |
|---------|--------------|
| 5 paying clients | Upgrade MongoDB Atlas to M10 ($57/mo) — message me and I'll guide you |
| 10 paying clients | Upgrade Railway to Pro plan + split scheduler to separate service — message me |
| 20+ paying clients | Architecture review — we'll plan this together when we get there |

---

*Last updated: May 2026*
