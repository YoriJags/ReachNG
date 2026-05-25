# WhatsApp ban / suspension — operator playbook

What to do when Meta restricts, disables, or bans a client's WhatsApp Business number. Written so a non-engineer can follow it under pressure.

Owner: Yori. Last reviewed: 2026-05-25.

---

## What we already do to prevent this

These guard rails fire automatically. Don't disable them.

| Layer | Defence |
|---|---|
| **Warmup ramp** | New numbers cap at 10 → 25 → 50 outbound/day across weeks 1/2/3. `tools/account_guard.WARMUP_SCHEDULE`. |
| **Spike guard** | If inbounds exceed 25/5min (warmup) or 60/5min (live), auto-drafter pauses for 30 min and owner gets a WhatsApp alert. `services/spike_guard.py`. |
| **Opt-out auto-pause** | >3% opt-out rate over 30+ replies → outreach halts. `tools/account_guard.maybe_auto_pause_on_optout_spike`. |
| **24h template-window check** | Drafts beyond the 24h session window flagged `requires_template=true` so the operator knows a Meta-approved template is required. |
| **HITL gate** | Nothing auto-sends until Autopilot is earned (20 approvals + 70% unedited last 30 days). |
| **Tone scrub** | Casual endearments removed before send — Meta's spam classifier weights them. |
| **WhatsApp health loop** | `services/whatsapp_health.py` polls Unipile every 6h; on `NOT_OK`, raises portal banner + owner WhatsApp alert. |
| **Reply-rate monitor** | If <30% of recipients reply to outbound, the 7am brief surfaces a "review what's going out" warning. |
| **Number redundancy** | Clients can pair multiple lines via `clients.whatsapp_accounts: [...]`. `tools/outreach.send_whatsapp_for_client` fails over automatically on send failure. |

---

## Detection

We learn about a ban via any of:

1. **Unipile webhook** — `accounts/error` event fires when Meta disables the line. Lands at `POST /api/v1/webhooks/unipile/account`. Already wired to flip `clients.whatsapp_health = NOT_OK` and post the portal banner.
2. **Health loop** — every 6h sweep detects an account that's gone dark.
3. **Owner WhatsApp** — owner messages us "EYO isn't replying!" via OWNER_WHATSAPP.
4. **Operator radar** — outreach_log shows >5 consecutive send failures for a single account_id.

---

## Severity ladder (assume worst, work down)

| Symptom | Likely cause | First move |
|---|---|---|
| One contact reports "your number says it can't receive messages" | Targeted block by that contact | Verify with second contact. If isolated, no action — Meta lets users block. |
| Outbound succeeds via Unipile API but never delivers | Soft-throttled by Meta | Pause non-essential outbound 24h. Drop daily cap to 50% of warmup level. Continue receiving inbound. |
| Sends fail with `4xx` from Unipile referencing "rate_limit" or "account_paused" | Rate-limit hit | Switch failover to backup line if configured. Stop the drafter for that client (`POST /api/v1/clients/{name}` with `outreach_paused: true`). |
| Unipile reports `account_disconnected` with no user trigger | QR session expired | Send the owner to `/portal/{token}/connect-whatsapp` to re-pair. **No ban yet.** |
| WhatsApp Business Manager shows "Restricted from messaging" | Quality rating dropped to Red | Treat as soft ban. Stop ALL outbound for 7 days. Continue receiving. Address quality (see below). |
| Number completely disabled in Meta Business Manager | Hard ban | Run the Hard Ban Recovery procedure below. |

---

## Soft restriction recovery (Red quality rating)

1. **Stop outbound for 7 days.** Set `clients.outreach_paused = true` via admin API. Inbound still works.
2. **Audit the last 50 outbound** in `outreach_log` for that client:
   - Are messages going to people who didn't message us first within 24h? → these need to become template sends.
   - Are messages template-ish to many recipients? → too templated, vary wording.
   - Is anyone replying? → if reply rate <20%, the targeting is wrong, not the messages.
3. **Verify the owner's customer list** is consented contacts only — no scraped numbers, no purchased lists, no leads from sources that didn't opt in.
4. **Reduce daily cap to 25/day** for 14 days after resuming.
5. **Watch Quality Rating** in Meta Business Manager. Returns to Yellow → resume normal cap. Green → fully clear.

---

## Hard ban recovery procedure

When the number is fully disabled:

1. **Immediate (within 5 min)**
   - Set `clients.outreach_paused = true` so no further drafts queue.
   - Toggle failover to backup line: set the disabled account's `health: NOT_OK` in `clients.whatsapp_accounts`. New sends route to next healthy line automatically.
   - Tell the owner via OWNER_WHATSAPP. Use the customer comms template at the bottom of this doc.

2. **Within 1 hour**
   - File the appeal at https://business.facebook.com/wa/manage/phone-numbers/ (the owner does this, not us — it requires their Business Manager access).
   - Owner provides: business registration, sample of typical customer message, screenshot of customer consent (any WhatsApp chat where the customer messaged first).
   - Meta typically responds in 24–72h. Most first-offence appeals succeed.

3. **Within 24 hours**
   - If backup line exists, route all client traffic there. Update `clients.whatsapp_accounts.primary` flag to the backup.
   - If no backup line, message every recent inbound (last 7 days) via SMS (Termii / Twilio) explaining the temporary disruption + alternative contact. Template at the bottom of this doc.
   - Open a `client_audit_log` entry with everything we know about the cause.

4. **After Meta decision**
   - **Appeal granted:** wait 24h before resuming outbound. Drop daily cap to 25/day for 21 days. Walk the warmup ramp from scratch.
   - **Appeal denied:** the number is gone permanently. The client provisions a new SIM, pairs it via `/portal/{token}/connect-whatsapp`, becomes the new primary. We DO NOT spin up the new number with the old contact list — start clean.

---

## What survives a ban

- All `client_memory` facts (per-customer memory) — stays in Mongo.
- All `closer_leads` + thread history — stays in Mongo.
- All `pending_approvals` (drafts) — survive but go stale; expire after 72h.
- All `scorecard` history — untouched.
- The portal URL — works fine; only the WhatsApp send path is down.

The only thing that dies is the sending channel. The agent's brain is intact.

---

## Customer comms templates (do NOT improvise during an incident)

### To the owner, within 5 minutes of detection
```
EYO alert: Meta has restricted your WhatsApp Business line.

What this means:
• Inbound messages will still arrive but reply sending is paused
• Your customer memory + booking history are safe
• No drafts will go out until we clear this

I'm filing the appeal now. Most first-offence appeals clear in 24-72h. While we wait, I'll switch new sends to your backup line if you have one — otherwise customers will get an SMS with an alternative contact.

Reply 1 to file the appeal yourself · Reply 2 if you want me to walk you through it.
```

### To recent customers (SMS via Termii / Twilio), within 24h
```
Hi from {{business_name}} — our WhatsApp line is temporarily limited. Please use {{backup_contact}} for urgent enquiries. We'll be back on WhatsApp shortly. — {{business_name}}
```

---

## Engineering touchpoints

If you're me-in-six-months and forgot what's where:

- `services/spike_guard.py::record_inbound_and_check` — inbound rate limiter
- `tools/account_guard.py::WARMUP_SCHEDULE` — 10/25/50 ramp
- `tools/account_guard.maybe_auto_pause_on_optout_spike` — opt-out auto-pause
- `services/whatsapp_health.py::run_health_check` — Unipile poll loop
- `services/scorecard.py::compute_scorecard.customer_reply_rate` — reply-rate signal
- `tools/outreach.send_whatsapp_for_client` — multi-line failover
- `clients.outreach_paused: bool` — flag to halt all outbound for a client
- `clients.spike_paused_until: datetime` — short-term auto-set by spike guard
- `clients.whatsapp_accounts: [{label, meta_phone_number_id, meta_access_token, health, primary}]` — multi-line schema
- `pending_approvals.requires_template: bool` — flagged when draft falls outside 24h session window

---

## What we do NOT do

- **Never** spin up a "new" account with the banned number's contact list. Meta tracks this pattern.
- **Never** appeal an obviously legitimate ban (spam-bought lists, mass sends without consent). Wait out the suspension, then onboard the client properly.
- **Never** offer the client a refund pre-emptively — the agent is still functional, only the sending channel is paused. Refund discussion only after appeal is decided.
- **Never** route a banned client's traffic through ReachNG's own WhatsApp Business line. One ban does not cascade to others by design — keep it that way.
