# EYO Agent Roster — the org chart

EYO is not one feature; it is a staff of AI agents behind one WhatsApp number.
This doc is the canonical roster: what's on payroll today, what gets hired
next, and the two rules every agent obeys. Use it for the pitch deck and the
pricing page ("hire one employee, get a staff of ten").

Last updated: 2026-06-13.

---

## Rule 1 — every agent is HITL
Agents are staff, not autopilots. Every outbound routes through
`tools/hitl.py::queue_draft()` and waits for the owner's tap. The single
exception is a client with `autopilot=true` who has *earned* it through the
readiness gate (`services/autopilot.py`) — and the EYO Demo persona (below),
which is our own fictional business.

## Rule 2 — no new agents before client #1
The ten live agents are sellable today. Everything in "Hiring next" is
sequenced for after the first paying client — except the Demo Agent, which is
go-to-market, not product.

---

## On payroll today (live in the codebase)

| Agent | Job | Lives in |
|---|---|---|
| **The Drafter** | Drafts every inbound reply in the owner's voice, any channel | `agent/brain.py` + HITL queue |
| **The Bookkeeper** | Reads transfer screenshots, matches them to orders | `receipt_match` |
| **The Gatekeeper** | Triages inbound, qualifies leads, shields the owner | inbound classifier + Shield |
| **The Negotiator** | Detects haggling; alerts owner first with the fair price; drafts within the secret floor | Haggle (owner-first) |
| **The Collector** | Chases rent/invoices through escalation bands, Lagos Tenancy Law aware | rent chase · invoice chaser · debt collector |
| **The Analyst** | Money Leak, Cashflow projection, Demand Radar | the inventions |
| **The Briefer** | 7am daily owner brief | morning brief jobs |
| **The Promoter** | Asks for referrals at the win moment | Referral wire |
| **The SDR** | *Our* agent: discovers prospects, drafts founder cold email, runs the 3-touch drip, stops on reply | Prospect OS + v2 drip |
| **The Coach** | Weekly win/miss distil → sharper prompts next week. The agent that improves the other agents | outcome learning loop |

Tier framing: **Solo** = Drafter + Bookkeeper + Briefer · **Team** = + Gatekeeper,
Analyst, Promoter · **Empire** = the full staff.

---

## Hiring next (in order)

1. **The Demo Agent** — public WhatsApp number persona. *Ungated — this IS
   distribution.* See runbook below.
2. **The Fraud Officer** — Fake Alert Shield: "did this transfer actually
   land?" Plausibility checks first (pending-vs-successful, sender/amount
   sanity, known fake-alert patterns); Paystack verify / Mono rails later.
   The reframe that opens wallets.
3. **The Voice** — voice-note *replies* (TTS), English/Pidgin first,
   owner-approved like any draft. Yoruba/Igbo/Hausa quality-gated R&D.
4. **The Scheduler** — books viewings/appointments into a calendar, confirms
   with the customer. EstateOS deepening.
5. **The Reconciler** — month-end: bank statement ↔ orders ↔ chats → "what
   never got collected." Premium Analyst upgrade.
6. **The Paralegal** — drafts quit notices / tenancy documents from chase
   data EstateOS already holds. **Lawyer-reviewed templates only.**

---

## Demo Agent — switch-on runbook (config, not build)

Prereq: one spare SIM/number. Everything else exists.

1. **Create the client** — Clients tab → Save Client:
   - Name: `EYO Demo` · Vertical: Real Estate · Plan: (none)
   - Brief (the persona — paste as-is):
     > Lekki Crest Properties is a boutique estate agency in Lekki Phase 1,
     > Lagos. We sell and let 2-4 bedroom apartments and terraces between
     > ₦80m and ₦450m, and short-lets from ₦150k/night. Tone: warm,
     > professional, quietly confident; plain English with a Lagos ear.
     > Always ask budget, preferred area, and timeline before recommending.
     > Never quote exact availability; offer to arrange a viewing instead.
     > Never discuss discounts beyond 5%. Sign as "Kemi from Lekki Crest".
2. **Pair the number** — portal link → Connect WhatsApp → scan QR with the
   demo SIM.
3. **Enable autopilot** — the demo must reply instantly (that's the magic).
   The readiness gate exists to protect *real* clients; for our own fictional
   persona, set `autopilot: true` directly on the `EYO Demo` client doc if
   the API gate refuses a zero-history client.
4. **Guardrails** (all existing machinery):
   - `daily_send_limit` modest (e.g. 100) — it's a demo, not a hotline.
   - The autopilot safety classifier still screens every reply.
   - Demo client name is excluded from Traction/billing rollups by its
     `plan: none` / non-paid status.
5. **Distribute the number** — WhatsApp groups, the landing page hero, your
   email signature: *"Message +234-XXX and pretend you're a customer. Watch
   EYO work."* The share unit is a phone number, not a URL.

Kill switch: set the client `active: false` — inbound stops routing same
minute.
