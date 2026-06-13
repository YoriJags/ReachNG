# EYO Action Layer (MCP) — the seam

EYO drafts messages. The **action layer** lets EYO also *do work in a client's
own tools* — book a viewing in their Google Calendar, push a lead to their Zoho,
file a receipt in their Sheet — by talking to the client's **MCP server**.

This document describes the **seam**: the plumbing that makes that possible,
laid behind a flag that is **off by default**. No live agent is wired to it yet
(see "Hiring next" in [AGENT_ROSTER.md](AGENT_ROSTER.md)). The seam exists so
that the day a client asks for an integration, it's a flag flip + a connection
row, not a sprint.

Last updated: 2026-06-13.

---

## The one rule: actions are HITL, exactly like messages

Booking a calendar event or pushing to a CRM is an **outbound side-effect** —
the same category as sending a WhatsApp message. So it obeys the same
non-negotiable rule:

```
EYO proposes an action  →  owner sees a card  →  owner taps  →  code executes the approved tool call
```

The model **proposes**; **code executes**. The approved action is dispatched by
`tools/mcp_client.call_tool` (a deterministic `ClientSession`-style call), *not*
re-decided by Claude. That is the safety property: a prompt-injected customer
message can never trigger a real action, because the only thing that can fire an
action is an owner tap in the approval queue.

> ReachNG also runs an MCP **server** (`mcp_server/`, mounted at `/mcp`) that
> exposes *our* tools to an outside Claude (you, in a chat). The action layer is
> the **opposite direction** — EYO as a *client* calling out to the client's own
> tools.

---

## Components

| File | Role |
|---|---|
| `services/connections.py` | Per-client MCP connection registry (`client_connections`). Provider, URL, encrypted bearer token. Tenant-scoped, unique on `(client_name, provider)`. |
| `tools/mcp_client.py` | Thin MCP **client**: `list_tools` / `call_tool`. Lazy import — dormant if the lib is absent, never breaks boot. |
| `services/mcp_actions.py` | HITL action queue: `queue_action` (propose) → `approve_action` → `execute_approved_action`. Shares `pending_approvals` with `kind="action"`. |
| `api/mcp_actions.py` | Admin API under `/api/v1/admin/mcp` (Basic Auth). Connections CRUD + test + action approve/skip. |
| `config.py` | `MCP_ACTIONS_ENABLED` (default **false**). |

### Why it can't fire by accident

Three locks, all must be open:

1. `MCP_ACTIONS_ENABLED` must be set. Off by default → `queue_action` raises `McpActionsDisabled`.
2. The client must have an **enabled** connection for that provider, or `queue_action` raises `McpConnectionMissing`.
3. The action must be **approved** (owner tap). `execute_approved_action` refuses any doc whose status isn't `approved`.

Action proposals are also filtered **out** of the message-draft queue
(`hitl.get_pending` excludes `kind="action"`), so an action can never be
"sent" as a message.

---

## Credentials

Bearer tokens are encrypted at rest with Fernet (`EMAIL_CRED_KEY`) via
`services/crypto.py` — the same fail-safe as email creds: **no key → refuse to
store, never plaintext.** The token is decrypted in exactly one place
(`connections.resolve_connection`), only for an enabled connection, and is never
logged. (Long term, OAuth providers like Google Calendar will want a refresh
flow / a vault; for now a bearer/static token to the client's MCP endpoint is
the seam.)

---

## Switch-on runbook (when a client asks)

1. Set `MCP_ACTIONS_ENABLED=true` on Railway (and `EMAIL_CRED_KEY` if not already).
2. Register the connection:
   `POST /api/v1/admin/mcp/connections`
   `{ "client_name": "Lekki Crest", "provider": "google_calendar", "url": "<mcp url>", "auth_type": "bearer", "token": "<token>" }`
3. Prove it: `POST /api/v1/admin/mcp/connections/test` → lists the server's tools.
4. EYO (or a future Scheduler agent) calls `mcp_actions.queue_action(...)` to
   propose; the owner approves in the queue; `execute_approved_action` fires it.

`GET /api/v1/admin/mcp/status` reports `{enabled, encryption_ready, client_ready}`.

---

## Status

- ✅ Seam shipped: connection registry, encrypted creds, HITL action path, MCP
  client wrapper, admin API — all behind `MCP_ACTIONS_ENABLED` (off).
- ✅ Tests: `tests/test_mcp_seam.py` (flag gate, tenant scope, encryption
  round-trip, propose→approve→execute, unapproved/failed paths, queue exclusion).
- ⏳ No live agent wired (deliberate — roster Rule 2: no new agents before client #1).
- ⏳ First connector when a client asks: **Scheduler → Google Calendar** (needs a
  Google OAuth app / refresh-token handling beyond the bearer seam).
