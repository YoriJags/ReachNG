# ReachNG

AI-powered outreach machine for Lagos businesses.

Three verticals running simultaneously: **Real Estate · Recruitment · Events**

**Stack:** FastAPI · FastMCP · Claude (Anthropic) · Google Maps Places API · Unipile (WhatsApp + Email) · MongoDB

---

## How It Works

```
Google Maps Places API
        ↓
   Business Discovery
        ↓
   Claude (Sonnet)  ←→  FastMCP Tools
        ↓
Personalised Message per Contact
        ↓
  Unipile → WhatsApp / Email
        ↓
  MongoDB (tracks everything)
        ↓
  Follow-up at 48h if no reply
```

Runs automatically every night at 10pm Lagos time. Follow-ups trigger at 2pm the next day.

---

## Quick Start

### 1. Clone and set up environment

```bash
git clone https://github.com/YOUR_USERNAME/reachng.git
cd reachng
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Fill in your API keys (see API Setup below)

```bash
nano .env
```

### 3. Run the server

```bash
python main.py
```

Open `http://localhost:8000/docs` to see the full API.

---

## API Setup

### Claude (Anthropic) — Already have this
1. Go to console.anthropic.com → API Keys
2. Copy your key into `ANTHROPIC_API_KEY`

### Google Maps Places API
1. Go to console.cloud.google.com
2. Create a project → Enable **Places API**
3. Create an API key → Restrict to Places API
4. Copy into `GOOGLE_MAPS_API_KEY`
5. Free tier: 28,500 requests/month — enough for hundreds of campaigns

### Unipile (WhatsApp + Email)
1. Sign up at unipile.com (free trial available)
2. Connect your WhatsApp account (scan QR code in dashboard)
3. Connect your email account (Gmail/Outlook OAuth)
4. Go to Settings → API Keys → copy key into `UNIPILE_API_KEY`
5. Copy your DSN (e.g. `api4.unipile.com:13465`) into `UNIPILE_DSN`
6. Get Account IDs from the Accounts tab in dashboard

### MongoDB
1. Use your existing MongoDB Atlas cluster (or create free tier at mongodb.com/atlas)
2. Create a database called `reachng`
3. Copy connection string into `MONGODB_URI`

---

## Running Campaigns

### Via REST API

**Dry run first — always preview before sending:**
```bash
curl -X POST http://localhost:8000/api/v1/campaigns/run \
  -H "Content-Type: application/json" \
  -d '{"vertical": "real_estate", "max_contacts": 10, "dry_run": true}'
```

**Go live:**
```bash
curl -X POST http://localhost:8000/api/v1/campaigns/run \
  -H "Content-Type: application/json" \
  -d '{"vertical": "real_estate", "max_contacts": 20, "dry_run": false}'
```

**Run all three verticals:**
```bash
curl -X POST http://localhost:8000/api/v1/campaigns/run-all \
  -H "Content-Type: application/json" \
  -d '{"max_per_vertical": 15, "dry_run": false}'
```

**Check stats:**
```bash
curl http://localhost:8000/api/v1/campaigns/stats
curl http://localhost:8000/api/v1/campaigns/stats?vertical=real_estate
```

**Check daily limit:**
```bash
curl http://localhost:8000/api/v1/campaigns/daily-limit
```

### Via MCP (Claude Desktop)

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "reachng": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Then ask Claude:
- *"Check the daily limit and run a dry run for real estate with 10 contacts"*
- *"Run follow-ups for all verticals"*
- *"How many contacts have replied this week?"*

---

## Campaign Settings

| Setting | Default | Description |
|---|---|---|
| `DAILY_SEND_LIMIT` | 50 | Max messages per day across all verticals |
| `FOLLOWUP_DELAY_HOURS` | 48 | Hours before follow-up is sent |
| `MAX_FOLLOWUP_ATTEMPTS` | 2 | Max follow-ups per contact |

Start conservative (20–30/day) and increase as you verify delivery rates.

---

## Verticals

| Vertical | Channel | Target | Value prop |
|---|---|---|---|
| Real Estate | WhatsApp | Developers, agents | Qualified buyer conversations |
| Recruitment | Email | HR firms, staffing agencies | Faster candidate sourcing |
| Events | WhatsApp | Promoters, venue owners | RSVPs and bookings |

---

## Contact Status Flow

```
not_contacted → contacted → replied → converted
                          → opted_out (never contacted again)
```

Mark contacts manually via API:
```bash
curl -X PATCH http://localhost:8000/api/v1/contacts/{id}/replied
curl -X PATCH http://localhost:8000/api/v1/contacts/{id}/converted
curl -X PATCH http://localhost:8000/api/v1/contacts/{id}/opted-out
```

---

## Pricing Model (Sell This)

| Package | Price | What they get |
|---|---|---|
| Starter | ₦150,000/mo | 500 messages, 1 channel, monthly report |
| Growth | ₦350,000/mo | 2,000 messages, 2 channels, follow-ups |
| Done-for-You | ₦750,000 setup + ₦200,000/mo | Full campaign, copywriting, weekly call |

Your cost per client: ~₦30–50k/mo in API costs. **Margin: 80%+**

---

## Deployment (Railway)

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway init
railway up
```

Set all environment variables in Railway dashboard under Variables.

---

*Built for Lagos businesses.*
