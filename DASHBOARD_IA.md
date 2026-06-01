# Admin Dashboard — Information Architecture

How every admin tab + subsection links, and the target arrangement. Source of
truth for the dashboard nav. (Client portal IA is separate — see portal.html tabs.)

Last updated: 2026-06-01 (after deferred-suite strip + Control Tower tab).

---

## Mechanics (how nav works)

- **Sidebar** = the product + section nav. `sidebarNav(section, el)` → `switchTab(section)`
  shows `#tab-{section}` and highlights the sidebar item.
- **`switchTab(name)`** hides every `.tab-panel` and shows `#tab-{name}`; auto-loads
  data for heavy tabs. Any button anywhere can call `switchTab` / `switchTabByName`.
- Each suite (Outreach / EstateOS / TalentOS) has its own `.product-tabs` strip;
  the Outreach strip is hidden — the **sidebar is the nav**.

---

## Live panes (15 Outreach core + EstateOS + TalentOS)

Deferred-suite panes (LendOS, FleetOS, SchoolOS, LegalOS, BuildOS, TrustOS,
debt-collector, float, fuel, fx-lock, market-credit, salary-erosion, moonlighting,
fx-salary) were stripped 2026-06-01 — UI only, backend kept (PLAN.md).

| Pane | Purpose | Reached today by |
|---|---|---|
| `overview` | Command Center — KPI hero, today's work | sidebar |
| `attention` | Needs Attention triage feed | sidebar + Command strip |
| `approvals` | HITL message queue | sidebar, KPI hero, many buttons |
| `replies` | Inbound replies inbox | buttons only (orphan) |
| `closer` | Closer thread drill-down | buttons only (orphan) |
| `activate` | Money Engine — Leak/Rescue/Radar/Copilot | sidebar |
| `pipeline` | Contacts pipeline | buttons only (orphan) |
| `invoices` | Invoice chaser | buttons only (orphan) |
| `clients` | Client roster + onboarding | sidebar |
| `briefs` | Per-client Business Briefs | buttons only (orphan) |
| `campaigns` | Run campaigns | buttons only (orphan) |
| `tower` | Control Tower — self-outreach, prospect interviews, agent learning, pricing | sidebar |
| `waitlist` | Early-access list | buttons only (orphan) |
| `signal_leads` | Cash-signal leads | buttons only (orphan) |
| `tools` | System — health, logs, flow | sidebar |

**The problem:** 8 panes (`replies, closer, pipeline, invoices, briefs, campaigns,
waitlist, signal_leads`) have **no sidebar home** — reached only by scattered
in-page buttons, so the operational flow feels disconnected.

---

## Link graph (who navigates where)

- `clients` ← 6 entry points · `approvals` ← 7 · `replies` ← 5 · `campaigns` ← 3 ·
  `pipeline` ← 2 · `tower`/`invoices`/`briefs`/`attention` ← 1 each.
- Natural clusters that link to each other:
  - **Conversations:** approvals ↔ replies ↔ closer (the inbound→draft→approve→thread loop)
  - **Money:** activate (leak/rescue) ↔ pipeline ↔ invoices
  - **Clients:** clients ↔ briefs ↔ campaigns (setup → brief → run)
  - **Control Tower:** tower (self-outreach/prospect/learning/pricing) + waitlist
  - **System:** tools + signal_leads

---

## Target arrangement (7 sections, orphans grouped under their parent)

Each multi-pane section gets a **sub-tab bar** (rendered at the top of every pane in
the group, so it stays visible when you switch sub-panes). Sub-tabs call the existing
`switchTab`; the sidebar stays highlighted on the group's primary pane.

| Sidebar section | Primary pane | Sub-tabs |
|---|---|---|
| **Command Center** | `overview` | — |
| **Needs Attention** | `attention` | — |
| **Conversations** | `approvals` | Approval queue · Replies · Closer threads |
| **Money Engine** | `activate` | Leak/Rescue/Radar · Pipeline · Invoices |
| **Clients** | `clients` | Roster · Briefs · Campaigns |
| **Control Tower** | `tower` | (in-pane sections) + Waitlist |
| **System** | `tools` | System · Signal leads |

Implementation: a `.subtabs` bar injected at the top of each grouped pane; buttons
call `switchTab('<sibling>')`; active state per pane. No backend change; all existing
buttons keep working. Orphaned dead JS (e.g., `fr_letters`/`fd_incidents` calls left
from the strip) gets purged in the same pass.
