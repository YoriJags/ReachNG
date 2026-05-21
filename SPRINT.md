# ReachNG — Active Sprint Board

**One file. Three sprints. Knock items off in order.** Deep references stay in [PLAN.md](./PLAN.md) and [BACKLOG.md](./BACKLOG.md); this is the execution path that pulls from them.

Last updated: 2026-05-21 · North Star: **first paying client + path to 100 clients by Y1 exit**.

---

## How this works

- Items marked `[ ]` are open. Tick them as you ship.
- **Each sprint = ~5 working days.** Promote to next sprint only when current sprint is done.
- "Reason" line on each item answers "why is this here, not later?" so we don't relitigate priority.
- Acquisition is the binding constraint (PostHog: 9 visitors/week vs 700 needed). Distribution moves rank above feature builds.

---

## Sprint 1 — Distribution unlock + pre-paid-client safety net *(~5 days)*

The two gaps that block first paying client: (1) nobody visits the landing, (2) silent failure modes that would burn first client's trust.

- [ ] **1. Try-EYO sandbox widget on landing** *(2 days, BACKLOG P1 #1)*
  - Backend: `POST /api/v1/try-eyo` using our Anthropic key, IP-rate-limited, ~600 token cap, server-side PostHog logging
  - Frontend: textarea below hero with vertical selector (hospitality / RE / clinic), 2.4s response, typing indicator
  - **Reason:** single biggest landing-conversion lever. Each visit becomes a live product demo. Generates shareable Twitter artifacts.

- [ ] **2. Wire `services/subscription_invoice.py` into Paystack webhook** *(1 hour)*
  - File is built (last session). Webhook in `api/marketing.py::paystack_webhook` doesn't call it yet.
  - Generate receipt → email via Resend → store in `subscription_receipts` collection → link from welcome email.
  - **Reason:** first paid client will check "where's my receipt?" 30 seconds after Paystack confirms. The Paystack auto-email is generic. We have a branded receipt ready, just not connected.

- [ ] **3. WhatsApp session-expiry health loop** *(1 day, BACKLOG #8 in P1 from prior session)*
  - APScheduler job every 6h calling `services.whatsapp_pairing.get_account_status` on every `clients[].whatsapp_account_id`
  - Writes `whatsapp_health` + `last_health_check_at` to client doc
  - Portal banner if `whatsapp_health != "OK"` linking to reconnect flow
  - Owner alert via `OWNER_WHATSAPP` + email to client when health flips OK → NOT_OK
  - PostHog event `wa_session_expired`
  - **Reason:** WhatsApp linked-device sessions expire silently after ~14d. Silent expiry = silent product stop = churn before we even know.

- [ ] **4. Trust band below hero** *(30 min, BACKLOG P1 #2)*
  - Inline strip: "Your WhatsApp number stays yours · We never hold funds · Per-client memory isolation, audited nightly · Lagos-built"
  - All claims already true. Just say it on the homepage.

- [ ] **5. Social-proof refresh** *(10 min, BACKLOG P1 #16)*
  - Remove "2 Lagos & Abuja businesses already on the list" line until 10+ signups
  - Or swap for: "Founding cohort: applications open"

- [ ] **5b. Visible founder-slots counter on /pricing** *(30 min — added from Emergent strategic review 2026-05-21)*
  - Reads `clients` count, shows "${50 - count} of 50 founder slots remaining" when count < 50
  - Live scarcity > abstract "first 50" phrase
  - Emergent insight: "9 of 50 founder slots taken" converts because visible scarcity > abstract scarcity

- [ ] **5c. Bump onboarding tone-calibration from 10 → 20 approved drafts before live** *(half day — added from Emergent strategic review 2026-05-21)*
  - First-hour-of-onboarding is where churn happens
  - More approved drafts = sharper tone fit on day 1 = lower week-2 churn
  - Edit `services/onboarding.py` calibration step + wizard copy + the live-mode gate

**Sprint 1 ship gate:** all 5 ticked. After this, the landing converts, receipts auto-email, and WhatsApp expiry can't kill a paid client silently. Safe to push for first paid client.

---

## Sprint 2 — Retention + activation moats *(~5 days)*

Built only after sprint 1 ships AND first paid client is live (real data starts flowing).

- [ ] **6. EYO Vault tab in client portal** *(1-2 days, BACKLOG P1 #4)*
  - Per-customer memory surfaced as CRM view: lifetime spend, preferred table, allergies, last 3 deposits, last cancellation reason
  - Data already in `services/client_memory.py` — this is a portal surface, not a build
  - **Reason:** turns switching cost from "low" to "structural." Owners can't leave once 30 days of customer memory accumulates.

- [ ] **7. Streak counter on Owner Brief** *(half day, BACKLOG P1 #3)*
  - "EYO has briefed you 47 mornings in a row · ₦14.2M in deposits caught"
  - Reads from `brief_dispatch_log` + `paystack_events`
  - **Reason:** habit loop. Premium owners check WhatsApp first thing every morning anyway — make EYO the daily anchor.

- [ ] **8. Per-vertical landing picker above hero** *(1 day, BACKLOG P1 #5)*
  - `services/marketing_content.py` already supplies content for 5 verticals
  - Promote from footer to top of page: "Choose your industry"
  - **Reason:** 1-click ICP segmentation. Intercom/Pylon model.

- [ ] **9. Phase 1.6 Client Book Onboarding (vCard + WhatsApp share-contact)** *(start, see PLAN.md Phase 1.6 for full scope)*
  - Most-friction-free ingest path: owner shares contacts inside their own WhatsApp → EYO thread → vCard parsed → buckets created
  - Then bucket-level approval flow (Past / Dormant / Hot)
  - **Reason:** Phase 1.6 is fully scoped in PLAN.md. Pull Tier 1 (WhatsApp share) first; Tier 2-4 in sprint 3 if needed.

- [ ] **10. Mobile WhatsApp scene fixes ≤380px** *(1 hour, BACKLOG P1 #17)*
  - Playwright snapshot at iPhone SE width
  - Fix overflow + flex breakage in the hero mock
  - **Reason:** most Lagos premium owners view via mobile. Hero breaking on small screens = silent leak.

**Sprint 2 ship gate:** all 5 ticked. After this, first paid client has structural retention and the funnel is per-vertical segmented.

---

## Sprint 3 — Outbound cadence + content engine *(~5 days, mostly process)*

Less build, more execution. Activates the BACKLOG "Founder authority cadence" + ACQUISITION.md channel plan.

- [ ] **11. Founder authority cadence kickoff** *(BACKLOG P0 #5, ongoing 20 min/day)*
  - Yori posts 3×/week on Twitter + LinkedIn using the angles already drafted (brand voice / qualification / scale-without-hiring / mental-model shift)
  - Lead with the *mental-model shift* post Monday morning
  - **Reason:** the only acquisition channel we can run today at zero cost. Every other paid channel needs budget.

- [ ] **12. Off-boarding flow for non-renewing customers** *(1 day, raised prior session, never built)*
  - Graceful WhatsApp unpair + data export + ledger close + offer reactivation discount + survey "why are you leaving"
  - **Reason:** when first churn happens, we need the playbook ready. Better to build cold than under panic.

- [ ] **13. Add the LinkedIn post + Twitter threads to /blog/** *(half day, BACKLOG P1 #18)*
  - Each Twitter thread becomes a blog post too — SEO + content asset
  - `/blog/why-premium-lagos-owners-stopped-using-ai` and 5 others targeting `"whatsapp ai for [vertical] lagos"`
  - **Reason:** organic compounds. Each post is a Google-indexed entry point.

- [ ] **14. Sentry + BetterStack + Slack webhook tail** *(half day, BACKLOG P1 #8)*
  - Error tracking, uptime per integration (Unipile, Paystack, Anthropic), webhook-failure tail
  - **Reason:** by sprint 3 we have paid clients — silent failures = revenue impact.

**Sprint 3 ship gate:** 4 ticked + 2 weeks of consistent founder cadence shipped. After this, traffic should be measurably non-zero in PostHog, off-boarding is rehearsed, and observability covers production.

---

## Deferred — explicit triggers (do not build yet)

Pulled from BACKLOG + optimization checkpoint. Listed here so they're visible but not actionable until conditions fire.

| Item | Trigger to start |
|---|---|
| Redis caching layer | Monthly Haiku spend > ₦50k OR 10+ paid clients |
| Background queue (RQ + Redis) | 25+ active clients |
| Mongo M0 → M10 migration | 10-12 paid clients |
| HITL audit trail surfaced in portal | First legal or clinic client signs |
| Voice Operator (Premium add-on) | 3+ Premium clients live |
| Receipt-as-API for fintechs | Monthly receipt volume > 5,000 |
| Bundle auto-billing for additional accounts | First Premium bundle customer |
| Materialised dashboard snapshots | 25+ active clients |
| Self-host Whisper | Voice transcription cost > ₦20k/mo |
| Inline 12-sec demo loop on hero | If Sprint 1 #1 (Try-EYO widget) underperforms |

---

## Anti-recommendations (do NOT do, regardless of mood)

- ❌ Don't rename tiers. Locked: 🌱 Starter / ⭐ Growth / 👑 Premium at ₦60k / ₦120k / ₦250k.
- ❌ Don't fork the stack to React/Next. Jinja2 + FastAPI is correctly chosen.
- ❌ Don't migrate Mongo → Postgres yet.
- ❌ Don't lower prices below ₦60k Starter.
- ❌ Don't lead any new copy with the "covers your sleep shift" trope. Brand voice / qualification / scale / mental-model angles instead.
- ❌ Don't add a second LLM provider "for redundancy."
- ❌ Don't open self-serve fully public until Try-EYO widget validates funnel.

---

## Source map

- **Live work** → this file
- **Phase-level breakdown** → [PLAN.md](./PLAN.md)
- **All open ideas (P0–P5)** → [BACKLOG.md](./BACKLOG.md)
- **Pricing rationale** → [PRICING.md](./PRICING.md)
- **Unit economics** → [ECONOMICS.md](./ECONOMICS.md)
- **Investor brief** → [INVESTOR.md](./INVESTOR.md)
- **Y1 acquisition plan** → [ACQUISITION.md](./ACQUISITION.md)
