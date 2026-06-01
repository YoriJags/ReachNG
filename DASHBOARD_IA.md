# Admin Dashboard — Information Architecture (8-tab command tower)

Source of truth for the admin dashboard nav. Goal: a coherent founder/operator
command center where every tab has one purpose and every subsection belongs under
it. (Client portal IA is separate — see portal.html tabs.)

Last updated: 2026-06-01.

---

## Target tab architecture (in workflow order)

1. **Command Center** — "What needs my attention right now?"
2. **Clients** — "Who are we operating for and how healthy are they?"
3. **Approvals** — "What messages are waiting for human review?"
4. **Money Engine** — "Where is money found / rescued / tracked?" (client money)
5. **Growth · Prospect OS** — "How we get new customers" (internal only)
6. **AI · Learning** — "How the agent performs and improves."
7. **Billing** — "Are we profitable per client?" (our money)
8. **System** — "Is the platform healthy and safe?"

Diagnostics/logs/config live low (System). High-frequency operator actions live
high (Command Center, Approvals). Client money (Money Engine) is kept separate
from our profitability (Billing).

---

## Audit: existing → new

The current `#tab-tower` ("Control Tower") is a grab-bag — it gets split apart.

| Existing pane / section | New home |
|---|---|
| `#tab-overview` KPI hero + today's work | **Command Center** |
| `#tab-attention` (Needs Attention feed) | **Command Center** (merged — it IS "what needs attention") |
| tower → "Revenue" KPIs | **Command Center** (revenue signals today) |
| `#tab-clients` roster | **Clients** |
| tower → "Add Pilot Client" | **Clients** (onboarding) |
| tower → "Client Roster" (dup) | **Clients** (merge with `#tab-clients`) |
| `#tab-briefs`, `#tab-campaigns` | **Clients** sub-nav (Briefs · Campaigns) |
| `#tab-approvals` (message queue) | **Approvals** |
| `#tab-replies`, `#tab-closer` | **Approvals** sub-nav (Replies · Closer) |
| `#tab-activate` (Leak/Rescue/Radar/Copilot) | **Money Engine** |
| `#tab-invoices`, `#tab-pipeline` | **Money Engine** sub-nav |
| tower → Self-Outreach dry-run | **Growth · Prospect OS** |
| tower → Outreach Analytics (open/click/convert) | **Growth · Prospect OS** |
| tower → Prospect Interviews | **Growth · Prospect OS** |
| `#tab-signal_leads`, `#tab-waitlist` | **Growth · Prospect OS** sub-nav |
| tower → Agent Learning (outcomes engine) | **AI · Learning** |
| (autopilot readiness, model cost by feature) | **AI · Learning** (Coming soon where no endpoint) |
| tower → Pricing Settings | **Billing** |
| tower → Billing (per-client cost vs revenue) | **Billing** |
| tower → MRR by Product Line | **Billing** |
| tower → Plan Packages | **Billing** |
| `#tab-tools` (health, logs, flow) | **System** |
| Needs-Attention "failed jobs" card | **System** (jobs) + surfaced in Command Center |

After this, `#tab-tower` is retired (its sections redistributed). Deferred-suite
panes were already stripped.

---

## Subsection layout per tab

- **Command Center** (`overview`): revenue signals today · priority queue · clients
  needing attention · pending approvals · WhatsApp/webhook health · failed jobs ·
  quick actions. (Absorbs the old Needs-Attention feed.)
- **Clients** (`clients`): roster (plan/MRR/margin/usage/WA status/last activity/
  portal link/pause-resume/onboarding state/health) · sub-nav → Briefs · Campaigns.
- **Approvals** (`approvals`): global queue + filters (client/vertical/urgency/risk) ·
  high-risk · edited · skipped · bulk-safe actions · sub-nav → Replies · Closer.
- **Money Engine** (`activate`): Money Leak · Revenue Rescue · Missed Opp Radar ·
  receipt/payment matches · collectible · bookings/deals · ROI/recovered · sub-nav →
  Invoices · Pipeline.
- **Growth · Prospect OS** (`growth`): self-outreach · prospect campaigns · lead
  imports · outreach analytics · prospect interviews · sub-nav → Signal leads ·
  Waitlist. Lead-quality scoring + nurture = **Coming soon**. (Internal only.)
- **AI · Learning** (`ai`): agent learning / outcome loop · owner edits · learning
  cards · autopilot readiness · drafter usage · model cost by feature (**Coming soon**
  where no endpoint).
- **Billing** (`billing`): subscription status · plan price · AI usage cost · gross
  margin · Paystack invoices/receipts · overdue · usage meter. (Data: `api/billing.py`
  `/api/v1/admin/billing`.)
- **System** (`tools`): webhook status · scheduler controls · background jobs · API
  health · logs · feature flags · env/config + security warnings.

---

## Implementation notes (keep it working)

- Sidebar = 8 items in the order above; each `sidebarNav('<tab>')` shows `#tab-<tab>`.
- Existing grouping helpers reused: `clientsNav`/`recoverNav`/`_subNavSwitch` for
  sub-navs (Clients, Approvals). New `growthNav`, `billingNav`, `aiNav` follow the
  same pattern.
- Tower's ct-sections are **relocated** into the new `#tab-billing`, `#tab-ai`,
  `#tab-growth` panes (move DOM, keep element IDs so loaders keep working:
  `loadAgentLearning`, `loadBillingTable`/`/api/v1/admin/billing`, self-outreach +
  prospect-interview loaders, pricing editor).
- Every existing `switchTab`/`switchTabByName`/`*Nav` call keeps resolving.
- Placeholders (lead scoring, nurture, model-cost-by-feature, autopilot-in-admin)
  render as "Coming soon" cards — never faked.
- Verify each phase: Jinja parse · `<div>`/`<script>` balance unchanged · smoke tests.
