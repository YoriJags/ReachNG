# Model Economics — intelligence as a tier feature

The smarter the model, the better EYO drafts in the owner's voice — and the more
it costs per message. Instead of eating that cost, we make it the thing clients
*buy*: **the plan chooses the brain, and the plan price carries the model cost
with margin.** A client who wants EYO to sound sharper or handle more nuance
upgrades; the upgrade pays for itself.

Last updated: 2026-06-13. Resolver: `services/model_tier.py`. Pricing below is
approximate (₦1,600/$ planning rate) — re-baseline when the FX rate moves.

---

## The tiers

| Plan | Price/mo | Brain | Why this model |
|---|---|---|---|
| **Solo** | ₦60k | **Haiku 4.5** | Fast, capable, cheap. The baseline EYO brain — already good. |
| **Team** | ₦120k | **Sonnet 4.6** | Sharper voice, better judgement on nuance and objections. |
| **Empire** | ₦250k | **Opus 4.8** | The strongest writer. Premium voice, hardest negotiations. |

The founder can also pin a single client to a higher brain without changing
their plan via a `model_tier` field on the client doc (a VIP courtesy, or a paid
add-on) — the resolver honors it over the plan.

> **Not tiered:** internal plumbing (intent classification, screenshot OCR,
> field extraction, campaign summaries) stays on **Haiku** for every plan — it's
> cheap, invisible to the client, and not the voice they pay for. Only the
> *client-facing reply brain* is tiered (EYO's drafts to the owner's customers,
> the closer's next-move drafts).

---

## Per-draft cost (short reply, ~1,500 in / ~200 out tokens)

| Model | $/1M in | $/1M out | ≈ per draft |
|---|---|---|---|
| Haiku 4.5 | $1 | $5 | **₦4** |
| Sonnet 4.6 | $3 | $15 | **₦12** |
| Opus 4.8 | $5 | $25 | **₦20** |

(The founder *self-outreach* drafter is a different, heavier surface — big v2
prompt + adaptive thinking, ~₦65/draft — and is deliberately Opus regardless of
any client plan. See `services/reachng_self_outreach.py`.)

---

## Monthly margin per plan

Assumes a realistic draft volume per tier, plus ~₦1.5–10k/mo of Haiku plumbing
(classification, OCR, extraction). HITL means not every inbound becomes a draft.

| Plan | Drafts/mo (est) | Model cost/mo | Revenue | Gross margin |
|---|---|---|---|---|
| **Solo** (Haiku) | ~500 | ~₦3.5k | ₦60k | **~94%** |
| **Team** (Sonnet) | ~1,500 | ~₦22k | ₦120k | **~82%** |
| **Empire** (Opus) | ~4,000 | ~₦90k | ₦250k | **~64%** |

Every tier clears a healthy SaaS gross margin. Empire is the tightest because
Opus at high volume is the real cost driver — which is exactly why it's the
priciest plan, and why the fair-use envelope below matters most there.

---

## Fair-use envelope (protects margin at the top)

Each plan includes a generous monthly draft allowance (the "Drafts/mo (est)"
column is the design point, set the published cap ~2× higher). Past the cap, the
options — in order of preference:

1. **Soft-cap nudge** — owner brief flags "you're past your plan's included
   drafts; upgrade or add a top-up." Keeps drafting; we absorb a little.
2. **Top-up block** — buy an extra N drafts at cost + margin.
3. **Auto-downgrade the brain** for the overage only (e.g. Empire overage drafts
   fall back to Sonnet) — never stops EYO working, just protects the floor.

The cap is a backstop, not the norm — typical SME volume sits well inside it.

---

## Why this is the right model (not eating the cost)

- **It's how serious AI SaaS prices.** Intelligence is the product; charging for
  it by tier is honest and scalable. Eating the cost caps how good we can let
  EYO be.
- **It creates a real upgrade path.** "Want EYO sharper? Move to Team." The
  demo on a higher tier sells the next tier.
- **It keeps Solo cheap and profitable.** Haiku is genuinely good; the entry
  plan stays a no-brainer at 94% margin, which is what lands the first cohort.
- **Margin survives scale.** Even the Opus tier clears ~64% before the fair-use
  backstop — and the backstop guarantees a runaway client can never go upside-down.

## Build status

- ✅ `services/model_tier.py` — resolver (plan → model, per-client override, fail-safe to Haiku).
- ✅ Wired into the client-facing reply brain: `generate_b2c_message`,
  `generate_auto_reply_draft`, `draft_inbound_reply` (agent/brain.py), and the
  closer `draft_next_move` (services/closer/brain.py).
- ⏳ Fair-use metering + soft-cap (deferred until real volume exists — `tools/account_guard.py` already meters sends and is the natural home).
- ⏳ Pricing-page copy: surface the brain per tier ("Solo runs on Haiku, Team on Sonnet, Empire on Opus").
