---
tags: [reachng]
---
# Decisions

[[Home]] | [[Architecture]] | [[Integrations]]

> Key architectural and product decisions — what was chosen and why.

---

## Messaging: Unipile over Twilio / Meta Official API

**Decision:** Use Unipile for WhatsApp delivery.

**Why:**
- Meta official API requires business verification + slow approval process
- Twilio's WhatsApp is expensive and also requires Meta approval
- Unipile works immediately, per-client account model fits multi-tenant needs
- Each client's messages come from their own number — more trust, better replies

**Trade-off:** ~$10–20/month per client account (passed through to client)

---

## AI Model Routing: 3-Tier

**Decision:** Route tasks to cheapest model that can handle them.

| Tier | Model | Use Cases |
|------|-------|-----------|
| Cheap | Gemini Flash | PDF extraction, data parsing |
| Medium | Claude Haiku | Classification, fallback extraction |
| Full | Claude Sonnet | Outreach writing, personalisation |

**Why:** Sonnet at scale gets expensive fast. Gemini Flash is ~10x cheaper for extraction.

---

## No Instagram Scraping

**Decision:** Never scrape Instagram directly.

**Why:** Terms of Service violation + brittle (rate limits, auth changes). Use hashtag signals from TikTok (via Apify) and Twitter instead.

---

## Discovery: Triple Source (Not Single)

**Decision:** Run Google Maps + Apollo + Social in parallel, then deduplicate.

**Why:** No single source has complete coverage. Google Maps is great for SMEs. Apollo has B2B decision-makers. Social finds businesses that aren't on Google/Apollo at all. Overlap is caught by deduplication.

---

## Apollo: Org Search Only (Free Tier)

**Decision:** Stay on free Apollo plan for now.

**Why:** $49/mo for people search (with emails) is only worth it once we have paying clients. Free org search is sufficient for MVP.

**Upgrade trigger:** First paying client → upgrade Apollo.

---

## HITL Default: On for Early Clients

**Decision:** Default HITL (Human-in-the-Loop) to enabled for first clients.

**Why:** Builds trust. Client sees messages before send. Allows correction if Claude writes something off-brand. Turn off as trust grows.

---

## Security: Fail Fast on Missing Env Vars

**Decision:** `_validate_env()` in startup — crash immediately with clear error if critical vars missing.

**Why:** Silent failures in production are worse than a loud crash. Dev + Railway both see the error immediately.

---

## Per-Client Portal: Token Auth, Not Basic Auth

**Decision:** Client portals use token-based auth, not HTTP Basic Auth.

**Why:** Clients don't need to manage usernames/passwords. One link = their dashboard. Tokens are rotatable per client without affecting others.
