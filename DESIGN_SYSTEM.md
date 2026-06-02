# Admin Dashboard — Design System (incremental migration)

`templates/dashboard.html` grew with ~1,600 inline `style=` attributes, ~200
hand-rolled cards, 4 competing button systems and 8 rounding values. We're
migrating it to shared primitives **one screen at a time** — additively, never
breaking IDs / JS hooks / fetch calls / tab logic.

Status: **Phase 3 complete** — all 8 tabs migrated (Command Center, Clients,
Approvals, Money Engine, Growth, AI, Billing, System).

Counts (dashboard.html): inline-styled buttons **161 → 145**, ad-hoc cards
**199 → 183**, inline `style=` **1587 → 1553**. Regression ceilings: 145 / 183.

---

## Tokens (`:root`)

Surfaces/text/accent/status already existed; Phase 1 added the missing scales.

| Group | Tokens |
|---|---|
| Surface | `--bg-deep` `--bg-base` `--bg-card`(=`--surface`) `--bg-card-hover`(=`--surface-2`) |
| Line | `--border`(=`--line`) `--border-bright` |
| Text | `--text-hi` `--text-mid` `--text-lo` |
| Accent | `--accent: #ff5c00` (**canonical orange**) `--accent-soft` |
| Status | `--green` `--amber` `--red` `--blue` (+ `*-soft` variants) |
| Radius | `--r-sm 6` `--r-md 10` `--r-lg 14` `--r-pill 999` |
| Spacing | `--s1 4` `--s2 8` `--s3 12` `--s4 16` `--s5 24` |

**Canonical orange = `#ff5c00`** (97 uses vs `#ff5500` 19; it's the sidebar/tab
accent and the marketing-site brand colour). `#ff5500` is migrated away per phase.

## Primitives (classes)

- `.card` / `.card--flush` — replaces ad-hoc `background+border+border-radius` divs.
- `.panel-title` / `.panel-title--eyebrow` — section headers.
- `.toolbar` / `.toolbar--divided` — horizontal action row (wraps; full-width divider variant).
- `.btn` (existing base) **+ modifiers** `--primary` `--ghost` `--ok` `--danger` `--sm` `--icon`.
  Do **not** redefine `.btn`'s base — 122 buttons depend on it.
- `.badge` + `--ok` `--warn` `--danger` `--info` `--neutral`.
- `.kpi` (+`__label`/`__value`) — simple stat tile (the richer `.kpi-card` hero stays).
- `.empty-state` — reuse the existing class; don't fork it.

## Migration order

1. ✅ **Phase 1** — tokens + primitives; **Command Center** (`#tab-overview`) launcher + Demo Sandbox.
2. ✅ **Phase 2** — **Clients** (Demo Sandbox + Unipile cards), **Approvals** (approve-all bar + `.btn--ok/--danger`), **Money Engine** (copilot controls + empty-states).
3. ✅ **Phase 3** — **Growth** + **AI** ("Coming soon" cards → `.card--placeholder`+`.soon-tag`), **Billing** (intro header), **System** (sub-nav action buttons, fixed stray `#ff5500`). Shared `.tab-intro-title/.tab-intro-sub` for tab headers.
4. ✅ **Phase 4 (done)** — `portal.html` warm control room.
   - **4a:** warm-valued primitives (`.card`, `.btn`+modifiers, `.badge`, `.toolbar`,
     `.panel-title`, `.empty-state`) on the cream palette (`--accent: var(--orange)`);
     fixed dark-on-cream CSS-rule bugs (topbar, `.sc-kpi`, `.brief-input`,
     `.activity-item`, `.leads-table`, status badges, `.score-badge`).
   - **4b:** migrated card wrappers + buttons (static **and** JS-rendered: copilot,
     radar, badges) to primitives; fixed the 3 dark-gradient hero cards
     (owner-brief, agent-learning, money-leak) the override couldn't reach; routed
     **every** `#ff5500` through `--accent`; tokenised remaining inline form
     inputs/tiles. Counts: inline buttons **8→0**, ad-hoc cards **35→11** (the 11 are
     warm form inputs/tiles, no dark hex), `#ff5500` **→0**. Ceilings 0 / 11.
   - Guarded by `tests/test_portal_design.py` (no dark rules, no dark inline, no
     raw `#ff5500`, regression budget).

## Rules

- Additive only. Migrate a screen end-to-end; never bulk-rename across tabs.
- Preserve every element ID, `onclick`, fetch URL, and tab/reflow hook.
- `tests/test_dashboard_ia.py` holds a **regression budget**: inline-button and
  ad-hoc-card counts may only trend down. Lower the ceiling after each phase.
