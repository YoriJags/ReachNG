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
| tower → Client Roster (rich operator view) | **Clients** (now the primary roster) |
| tower → System Health strip | **System** (`#tools-reflow-body`) |
| Needs-Attention "failed jobs" card | **System** (jobs) + surfaced in Command Center |

After this, `#tab-tower` is retired (its sections redistributed). Deferred-suite
panes were already stripped.

### 2026-06-02 cleanup (junk removal)

Three things were still stranded after the original split and have now been resolved:

- **Rich operator Client Roster** (Run / Invoice / Status / Autopilot / Signal /
  Pair-WA / Onboard / Offboard, usage bars, funnel, deals-won) had no reflow tag,
  so it was stuck in the hidden `#tab-tower`. It now `data-reflow="clients"` and is
  the single roster in **Clients**; the older simpler `roster-table` was removed
  (`refreshRoster()` kept only as the headline client-count feeder).
- **System Health** strip now `data-reflow="tools"` → **System** (`#tools-reflow-body`).
- **Dead nav severed:** `_TAB_REMAP.tower`, the `_subNavSwitch`/`switchTab` `tower`
  branches, the ⚡ quick-menu "Control Tower" button, and the Command Center
  "Needs attention →" button (its grid is already inline in Command Center) all
  removed. `#tab-tower` and `#tab-attention` are now `display:none` **reflow-source
  shells only** — never navigated to. `loadControlTower()` now also fires on the
  Clients tab + initial `fullRefresh()` so the relocated roster populates.
- Stale copy fixed: "Control Tower tab" SOP refs → Billing/Clients; plan labels
  aligned to the locked Solo ₦60k / Team ₦120k / Empire ₦250k ladder.

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

---

## Button → workflow map (operator surfaces)

What every primary action actually does end-to-end. Source of truth for hints,
tooltips, and onboarding copy. (Updated 2026-06-12.)

### Clients · Onboarding
| Button | Workflow |
|---|---|
| **✨ Draft with AI** | POST `/api/v1/admin/brief/draft` — Haiku reads the pasted notes/URL → composes the brief into the textarea. Nothing persists; operator reviews then saves. |
| **Save Client** | PUT `/api/v1/clients/` (upsert by name) → client doc created/updated; warm-up window seeded at creation. |
| **Generate Portal** | POST `/api/v1/portal/generate/{name}` → mints (or returns existing) portal token → copyable link. Send to client; no login needed. |
| **Run (campaign)** | POST `/api/v1/campaigns/run` → discovery (Maps/Apify/social) → score/dedup → drafts → **HITL queue**. Dry-run = preview only, nothing queues. |

### Approvals (Message Queue)
| Button | Workflow |
|---|---|
| **Approve** | Sends via the contact's channel (Unipile WA / Resend email / client SMTP / Meta) → records outreach → for self-outreach, schedules the next drip touch (T1→+3d, T2→+5d). |
| **Edit → Save & Send** | Same as Approve, but the edit is stored and feeds the per-client learning loop (next drafts improve). |
| **Skip** | Marks skipped. Nothing sends; no follow-up scheduled from this draft. |

### Growth · Prospect OS
| Button | Workflow |
|---|---|
| **Generate 5 sample drafts** | POST `/admin/self-outreach/dry-run` — pure copy preview (≈₦4/draft). Nothing sends, nothing queues. The calibration surface. |
| **+ Preview a real business** | Same drafter against one real prospect's enrichment. Preview only. |
| **Check now (Stop-on-reply)** | POST `/admin/self-outreach/reply-poll/run` — polls hello@reachng.ng inbox now; any sender who replied gets remaining drip touches cancelled. Also runs automatically every 10 min. |
| **Refresh (Analytics)** | Reloads the Resend open/click/bounce funnel + per-prospect table. Read-only. |

### Scheduled (no button — runs itself)
| Job | Workflow |
|---|---|
| **Drip tick** (weekdays 09:15 Lagos) | Finds contacts due for touch 2/3 → drafts via v2 (different capability than T1) → **queues to Approvals**. Never sends directly. |
| **Stop-on-reply poll** (every 10 min) | IMAP-polls the reply mailbox → marks repliers → cancels their remaining touches. |
| **Bounce stop** (Resend webhook) | Hard bounce/complaint → contact opted-out, drip ends. |
