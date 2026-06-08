# North Star — the acquisition thesis (and how it shapes the build)

Last updated: 2026-06-08

This is the anchor doc. When a build decision is ambiguous, it resolves here.
The thesis is deliberately also the thesis for being a *great independent
business* — we never trade customer value for acquirer optics. Building "to be
acquired" as a goal is a trap (it optimizes for someone's org chart instead of
the customer, and acquirers smell it). So the rule is:

> **Build the thing that makes the acquisition inevitable — which is the same
> thing that makes us win if the call never comes.**

---

## 1. The thesis in one paragraph

EYO is the **owner-side brain** for African SME commerce: it drafts in the
owner's voice, catches the money, remembers the customer, and never sends
without a human tap (HITL). That brain is **channel-agnostic** — WhatsApp,
email, Instagram, Messenger are just transport adapters. We run on **Meta's own
rails** (WhatsApp Cloud API, Messenger/Instagram Messaging), and we own the part
of the SME's workday that **Meta structurally cannot** — the voice, the money
graph, the unified customer across every inbox. Win Lagos, then Nigeria, then
Africa.

## 2. Why an acquirer (Meta or otherwise) would want EYO

Acquirers don't buy ₦60k/mo revenue — that's a rounding error. They buy one of:

| Lever | What it means for EYO | The build it demands |
|---|---|---|
| **Distribution in a market they can't crack** | EYO becomes *the* way African SMEs do business on Meta's messaging rails. Meta wants Business Messaging to win in emerging markets and can't manufacture local trust. | **Density** — thousands of SMEs whose livelihood runs through EYO on Meta rails. |
| **A wedge into a workflow they don't own** | Meta owns the pipes; EYO owns the owner's actual workday (voice, money-catching, daily brief). | **The brain as moat** — proprietary owner-voice + money graph + unified-customer graph. |
| **A team + system worth buying not building** | They'd rather absorb us than rebuild. | **Clean, documented, scalable engineering.** |

Strongest for us: **distribution + workflow-wedge together** — be the operating
system for African SME commerce, on Meta's rails, owning what Meta can't.

## 3. The five build commitments

Each is good business on its own. Together they are the acquisition thesis.

### C1 — Run on Meta's rails, deepen the dependency (deliberately)
Every customer on WhatsApp Cloud API + IG/Messenger makes EYO more valuable to
Meta and harder to route around. The CAC → Business Verification → App Review
path isn't just "unblock IG" — it's the on-ramp to **Meta Tech Provider /
Solution Partner** status, the relationship that precedes most of these deals.
- **Built:** channel-agnostic brain; Meta IG/Messenger adapter (dormant, dev-mode-ready); WhatsApp Cloud API send path + multi-account health failover; webhook HMAC verification.
- **Next:** CAC registration → Business Verification → App Review → production self-serve. (See `docs/META_AND_CHANNELS.md`.) Treat IG/Messenger as *strategic*, not optional.

### C2 — Own a moat Meta can't trivially clone
Meta will never build "drafts in *this* Lagos landlord's voice, reads his
transfer screenshots, knows his tenants." Invest there, not in chat plumbing
(plumbing is Meta's — they'll always out-plumb us).
- **Built:** owner-voice drafter (channel-aware); Money-Leak + Cashflow engines; unified-customer dossier across WhatsApp+email; the 5 inventions (Shield, Haggle, Radar, Cashflow, Referral) as deterministic cores.
- **Next:** keep the voice model + money graph + identity graph proprietary and deepening. Guard them as *the asset*.

### C3 — Density in one geography first
1,000 paying Lagos SMEs beats 50 scattered globally. Acquirers value *dominance
of a defined market* over thin global spread.
- **Built:** the wedge (WhatsApp + email) needs zero Meta/CAC gating — can onboard today.
- **Next:** land client #1, then the next 10, in Lagos real estate. Go-to-market, not code.

### C4 — Numbers that read as a category, not a tool
The three an M&A or Series-A team asks for:
1. **Money recovered for SMEs** (₦ across the book) — our headline. EYO *makes
   owners money*; this is the number.
2. **Retention** — do owners keep EYO running daily? (active-after-30-days.)
3. **Channel volume on Meta rails** — messages handled, channel mix.
- **Built:** per-client money-leak / cashflow / outcomes.
- **Gap → the one new build (see §5):** a **North-Star roll-up** across the whole book. This is also what the founder needs for fundraising — not vanity.

### C5 — Engineering they can absorb
A messy codebase kills an acqui-hire. Our existing discipline *is*
acquisition-readiness: HITL choke point, pure cores + thin adapters, CI gate,
fail-safe gating, honest `docs/SCALE_CONCERNS.md`.
- **Next (as density arrives, already tracked in SCALE_CONCERNS):** sync pymongo → Motor; integration tests with real creds for highest-risk paths; scheduler leader-election before horizontal scale.

## 3b. The Dirty-Work Doctrine (the heart of C2)

Meta is spending billions to **perfect the rails** — the platform, the APIs, the
deliverability, the AI primitives. They will make the *plumbing* immaculate.
What Meta will **never** do is the messy, local, human, low-status ground work
that actually closes a sale for a Lagos SME. That gap is our home.

**Meta perfects the platform. We do the dirty work on top of it.** Concretely,
the dirty work = our moat:

- **Reading blurry transfer screenshots** and matching them to an invoice.
- **Nigerian phone/name normalization** (`+234`/`0`, spaces, nicknames) and
  identity-stitching one customer across WhatsApp + email + IG.
- **Chasing money** through escalation bands (friendly → final) with **Lagos
  Tenancy Law** nuance — collections work nobody wants to do by hand.
- **Drafting in the owner's actual voice**, pidgin and code-switching included —
  not a generic "How can I help you today?" bot.
- **Local haggling** — owner-first fair-price negotiation with a secret floor.
- **The 7am owner brief** — turning a chaotic inbox into one human-readable page.
- **HITL judgement** — the human tap Meta's automation explicitly won't own.
- **The unglamorous trust layer** — KYC, PoF, lawyer bundles, consent, opt-out.

Why this is durable: it's **labour-shaped, not API-shaped.** Meta optimizes for
billions of generic interactions; we optimize for *one Lagos owner getting paid
today.* A platform company structurally won't go down-market into per-SME, per-
locale, human-in-the-loop drudgery — the margins and the support surface scare
them. So the more they perfect the rails, the more valuable the actor who does
the dirty work on those rails becomes. **We are not competing with Meta; we are
the thing that makes their rails actually pay off for the SME** — which is
exactly why they'd rather own us than build down into the mud themselves.

Build rule from this doctrine: when choosing what to build, **prefer the work
that is too messy, too local, or too human for a platform to want.** That is
always the moat, never the commodity.

## 4. Non-goals (what the thesis does NOT mean)

- **Don't build for an org chart.** No speculative features because "Meta might
  want it." Build for the Lagos owner; the rest follows.
- **Don't out-plumb Meta.** We are *aid*, on their rails — never a chatbot, never
  a Meta competitor. (Positioning: "Meta paid to open this market; we're the
  bottleneck-remover on top.")
- **Don't dilute HITL or multi-tenant isolation** for any growth metric.

## 5. The one new code surface this thesis justifies now

**North-Star / Traction roll-up** — aggregate, across the whole client book, the
C4 numbers from data EYO already collects:
- **₦ recovered** (sum of money-leak / cashflow realized across clients),
- **active clients & 30-day retention**,
- **messages handled + channel mix** (WhatsApp / email / Meta),
- **drafts approved (HITL throughput)**.

Surfaced as an admin **"Traction"** panel + a single `GET /api/v1/admin/traction`
endpoint. Pure read-side aggregation over existing collections — no new write
paths, no HITL change, no tenant-isolation risk. Doubles as the fundraising
scoreboard. **This is the only net-new build the thesis asks for right now;**
everything else is go-to-market (C3) or already built (C1/C2) or correctly
deferred (C5).

## 6. Sequenced roadmap

1. **Now:** land Lagos client #1 on WhatsApp + email (C3). Ship the Traction roll-up (C4).
2. **Parallel/background:** CAC registration → Meta Business Verification (C1).
3. **At ~10 clients:** App Review → IG/Messenger production self-serve (C1); begin Motor migration + integration tests (C5).
4. **At density:** scheduler leader-election, queue inbound, schema validators (C5, per SCALE_CONCERNS).
