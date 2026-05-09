---
tags: [reachng]
---
# Campaign Flow

[[Home]] | [[Architecture]] | [[Verticals]] | [[Integrations]]

---

## End-to-End Flow

```
1. Trigger
   └── Manual (dashboard) OR APScheduler (automated)

2. Discovery — 3 parallel sources
   ├── Google Maps → Places Text Search → business name, phone, address, rating
   ├── Apollo.io  → org search → company name, domain, industry, headcount
   └── Social     → TikTok/Instagram/Twitter hashtags → business signals

3. Deduplicate
   └── By phone + email across all sources before DB insert

4. Enrich
   └── Score leads (0–100), categorise by vertical, flag high-value

5. Generate
   └── Claude Sonnet writes personalised WhatsApp per lead
       Context fed in: business name, vertical, city, any enrichment data

6. Send
   ├── HITL ON  → queue in approvals → human reviews → approve/edit → send
   └── HITL OFF → immediate send via Unipile

7. Track
   ├── replied        → Replies tab, sorted by urgency
   ├── converted      → Clients tab
   └── opted-out      → Suppression list
```

---

## Follow-up Logic

- `FOLLOWUP_DELAY_HOURS` (default 48h) — wait before 2nd touch
- `MAX_FOLLOWUP_ATTEMPTS` (default 2) — max follow-ups per lead
- APScheduler runs the follow-up job automatically

---

## Tone Escalation (Invoice Chaser)

| Condition | Tone |
|-----------|------|
| `reminder_count == 0` | polite |
| `reminder_count == 1` or `days_overdue < 14` | firm |
| `reminder_count == 2` or `days_overdue < 30` | payment_plan |
| else | final |

---

## HITL (Human-in-the-Loop)

- Messages queued in `approvals` MongoDB collection
- Dashboard Approvals tab shows pending queue
- Each item has `expires_at` — stale drafts auto-expire
- Approve → sends via Unipile immediately
- Edit → update message text → then send

---

## Campaign Config (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `DAILY_SEND_LIMIT` | 50 | Max messages per day |
| `FOLLOWUP_DELAY_HOURS` | 48 | Hours before follow-up |
| `MAX_FOLLOWUP_ATTEMPTS` | 2 | Max follow-ups per lead |
| `DEFAULT_CITY` | Lagos, Nigeria | Default discovery city |
