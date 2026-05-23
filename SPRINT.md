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

- [ ] **1. Try-EYO sandbox widget on landing** *(2 days, BACKLOG P1 #1)* ← **next big build**
  - Backend: `POST /api/v1/try-eyo` using our Anthropic key, IP-rate-limited, ~600 token cap, server-side PostHog logging
  - Frontend: textarea below hero with vertical selector (hospitality / RE / clinic), 2.4s response, typing indicator
  - **Reason:** single biggest landing-conversion lever. Each visit becomes a live product demo. Generates shareable Twitter artifacts.

- [x] ~~**2. Wire `services/subscription_invoice.py` into Paystack webhook**~~ — ✅ shipped `cb48ca1`. Receipt now auto-emails on charge.success.

- [x] ~~**3. WhatsApp session-expiry health loop**~~ — ✅ shipped `9e44a1f`. APScheduler every 6h, portal banner, owner WhatsApp alert + client reconnect email, PostHog `wa_session_expired` events.

- [x] ~~**4. Trust band below hero**~~ — ✅ shipped `fc8ac8f`. 4-column strip between hero and Problem section.

- [x] ~~**5. Social-proof refresh**~~ — ✅ shipped `fc8ac8f`. Waitlist counter now hides until total ≥10.

- [x] ~~**5b. Visible founder-slots counter on /pricing**~~ — ✅ shipped `1b19c7e`. Live "X of 50 founder slots taken · Y remaining" pill above tier cards, with sold-out fallback.

- [ ] **5c. Tone-fit confidence meter + Autopilot ≥20 gate** *(half day — decision (b) locked last session)*
  - Confidence meter in client portal grows with each approved draft per reply-type
  - Autopilot toggle per reply-type gates at ≥20 approvals (was unbounded)
  - Matches the locked PLAN.md rule: "Autopilot is earned, not defaulted"
  - Files: `services/autopilot.py` threshold check + new meter widget in `templates/portal.html`

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

- [x] ~~**8. Per-vertical landing picker above hero**~~ — ✅ shipped `fc8ac8f`. "I run a 🍽 restaurant / 🏛 real estate / ⚖ law / 🎓 school / something else" pill row routes to /for/{slug}.

- [ ] **9. Phase 1.6 Client Book Onboarding (vCard + WhatsApp share-contact)** *(start, see PLAN.md Phase 1.6 for full scope)*
  - Most-friction-free ingest path: owner shares contacts inside their own WhatsApp → EYO thread → vCard parsed → buckets created
  - Then bucket-level approval flow (Past / Dormant / Hot)
  - **Reason:** Phase 1.6 is fully scoped in PLAN.md. Pull Tier 1 (WhatsApp share) first; Tier 2-4 in sprint 3 if needed.

- [x] ~~**10. Mobile WhatsApp scene fixes ≤380px**~~ — ✅ shipped `a499545`. iPhone SE breakpoint added: hero h1 30px, CTAs stack full-width, mock cards tighten padding, bubbles 12.5px.

- [ ] **11. Voice-only owner control** *(5-7 days, added 2026-05-21 from Emergent triage A10)*
  - Owner sends a WhatsApp voice note to EYO ("Hold all replies tomorrow", "Update Friday minimum to ₦200k", "How am I doing this week?")
  - Whisper transcribes (already shipped, multilingual safe-switch) → Haiku parses to structured `{action, params, scope}` → applies to client_rules / brief / HITL queue / scorecard
  - V1 supports 5 command classes: pause/resume, rule toggle, pricing update, bulk approve/skip, status check
  - WhatsApp confirmation back to owner ("Done. EYO will hold all replies tomorrow until 6am Tuesday. Active rules: 3.") + one-tap undo
  - **Reason:** Replaces the portal for 80% of owner control tasks. 90% of needed components already shipped. Lagos owners live on WhatsApp voice notes — daily-driver control surface should match the medium they already use.

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
