# ReachNG — Current State & Flow
*Last updated: 2026-04-04*

---

## Where We Are

ReachNG is fully built and live. Here's the complete flow end-to-end.

---

## Lead Discovery (3 parallel sources)

1. **Google Maps** — finds SMEs by vertical + city (Lagos)
2. **Apollo.io** — B2B org search for decision-makers
3. **Social** — scrapes TikTok, Instagram, Twitter, Facebook hashtags for business signals

All three run in parallel, results merged and deduplicated by phone/email before hitting MongoDB.

---

## Campaign Flow (every run)

```
Run Campaign → Discover leads → Enrich (score + categorise)
             → Claude writes personalised WhatsApp message per lead
             → [if HITL] → queued in Approvals tab → you approve → send
             → [if live]  → sent immediately via Unipile
             → Track: replied / converted / opted-out
```

---

## Dashboard Tabs

| Tab | What it does |
|-----|-------------|
| **Overview** | Today's Work panel + pipeline stats across all 7 verticals |
| **Campaigns** | Run campaigns, dry run or live, with HITL toggle |
| **Clients** | Add clients, generate portal links, Unipile setup SOP |
| **Approvals** | Review + approve/edit HITL-queued messages before sending |
| **Replies** | Inbound replies sorted by urgency — hot leads at top |
| **Invoices** | Generate + send invoice to clients |
| **Tools** | Export CSV, export replies, hooks config |

---

## 7 Verticals

`real_estate` · `recruitment` · `events` · `fintech` · `legal` · `logistics` · `agriculture`

---

## What's NOT Done Yet

- **First live campaign run** — only dry runs done so far. Overview will show 0 until you run live.
- **Google Maps billing** — Active as of 2026-04-12. All 3 discovery sources live.
- **Client scaling** — currently using one Unipile account. Each paying client needs their own WhatsApp number + Unipile account (~$10–20/month, passed to client).

---

## Immediate Next Step

Run your first live campaign:

1. Go to Campaigns tab
2. Pick a vertical (try `legal` or `recruitment`)
3. Uncheck **Dry run**, leave **Review before send** unchecked
4. Max contacts: 10
5. Hit Run — leads go out, replies show up within hours
