# ReachNG — Claude Handoff

Last updated: 2026-05-09

## Resume point

Opus 4.7 shipped the Lead Activation wedge on `main` up to:

- `94dc3ad` — cash-focused Owner Brief backend + `/portal/owner-brief/{token}`
- `9aab49d` — Owner Brief card in `templates/portal.html`
- `2694a18` — Lead Resurrection upload/run flow through portal token
- `b52d8c1` — Missed Opportunity Radar v1

Codex continued with a small portal-first Sales Copilot v0:

- `tools/sales_copilot.py`
- `/portal/sales-copilot/{token}` in `api/portal.py`
- Sales Copilot panel in `templates/portal.html`

Verification run:

```bash
python -m py_compile ReachNG/tools/sales_copilot.py ReachNG/api/portal.py
```

## What is complete

- Owner Brief cash signal pack is live.
- Portal Owner Brief card is live.
- Lead Resurrection portal upload + HITL-forced campaign run is live.
- Missed Opportunity Radar portal widget is live.
- Sales Copilot portal v0 is live: inbound reply cards, hot/warm/watch/closed priority, suggested next action, pending draft approve/skip, WhatsApp deeplink.

## What is not complete

Backlog item **WhatsApp Sales Copilot view** is only partially done. The remaining intended Claude plan is:

- Build admin/operator `/dashboard/copilot` surface.
- Show pipeline-card view of every active inbound thread.
- Add qualifying-question prompts using Business Brief / vertical primer context.
- Expose full operator actions from Control Tower, not only client portal cards.
- Wire it into the upcoming Outreach dashboard redesign.

## Next accurate step

Continue with the backlog sequence:

1. Finish **WhatsApp Sales Copilot view** as an admin/operator surface.
2. Then start **Outreach dashboard redesign**:
   - Today
   - Activate
   - Recover
   - Clients
   - System

Do not start Prospect OS, pressure-test follow-ups, or unrelated suites before the Sales Copilot/admin dashboard continuation unless the user explicitly redirects.

## Notes

- Follow `CLAUDE.md`: FastAPI/Jinja/Mongo stack, no Node/Next suggestions.
- Every outbound message still goes through `tools/hitl.py::queue_draft()`.
- Do not log PII.
- Existing untracked zero-byte files `400MB` and `5%` were present before Codex work and should be ignored unless the user asks to clean them.
