# ReachNG Brain

> AI-powered outreach machine for Lagos businesses.
> Finds leads → writes WhatsApp messages → tracks replies → converts to clients.

---

## Quick Navigation

| Area | Note |
|------|------|
| What is this | [[Architecture]] |
| How campaigns work | [[Campaign Flow]] |
| The 7 verticals | [[Verticals]] |
| All integrations | [[Integrations]] |
| Current build status | [[Build Log]] |
| Product ideas pipeline | [[Ideas Pipeline]] |
| Key decisions made | [[Decisions]] |
| API endpoints | [[API Reference]] |
| Deployment & ops | [[Ops]] |

---

## Current State (2026-04-12)

- **Status:** Live on Railway
- **Last fix:** `tools.messaging` import → `tools.outreach` (deployment was broken)
- **First live campaign:** Not run yet — only dry runs
- **Google Maps:** Billing blocked (Nigerian card). Apollo is primary discovery
- **Invoice Chaser:** Built and live (`/api/v1/invoice-chaser`)
- **Gemini Flash:** Wired in for cheap PDF/data extraction

---

## Immediate Next Actions

1. Run first live campaign (legal or recruitment vertical, 10 contacts)
2. Build WhatsApp inbound webhook (Unipile → reply handler)
3. Pitch PLUGng to David Avante — artist vertical MVP

---

## Live URL

`https://reachng-production.up.railway.app`
