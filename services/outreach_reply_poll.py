"""
Stop-on-reply for the self-outreach v2 drip.

When a prospect replies to one of Yori's cold emails, the next touch must not
fire. Resend (our send path) doesn't tell us about replies, so we watch the
reply mailbox directly: poll UNSEEN messages, match the sender's email to a
contact, and mark them replied (which clears next_followup_at and removes them
from the follow-up queue).

Dormant unless OUTREACH_IMAP_HOST/USER/PASSWORD are all configured. Without
them the drip is still bounded by the 3-touch hard cap — this only makes the
stop *early and automatic*.
"""
from __future__ import annotations

import structlog

from config import get_settings
from services.email_imap import parse_email_message
from tools.memory import stop_followups_for_email

log = structlog.get_logger()


def outreach_reply_polling_enabled() -> bool:
    s = get_settings()
    return bool(s.outreach_imap_host and s.outreach_imap_user and s.outreach_imap_password)


def poll_outreach_replies(*, max_messages: int = 50) -> dict:
    """Poll the outreach reply mailbox and stop the drip for anyone who replied.

    Returns a summary. Best-effort: any failure is logged and swallowed so the
    scheduler tick never crashes. PII (the sender address) is never logged."""
    s = get_settings()
    if not outreach_reply_polling_enabled():
        return {"skipped": "not_configured"}

    stopped = 0
    scanned = 0
    try:
        import imaplib
        M = imaplib.IMAP4_SSL(s.outreach_imap_host, int(s.outreach_imap_port or 993))
        M.login(s.outreach_imap_user, s.outreach_imap_password)
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN")
        ids = (data[0].split() if data and data[0] else [])[:max_messages]
        for mid in ids:
            typ, md = M.fetch(mid, "(RFC822)")
            if not md or not md[0]:
                continue
            scanned += 1
            parsed = parse_email_message(md[0][1])
            from_email = parsed.get("from_email")
            if from_email:
                try:
                    stopped += stop_followups_for_email(from_email, reason="replied")
                except Exception as e:
                    log.warning("outreach_reply_stop_failed", error=str(e))
            M.store(mid, "+FLAGS", "\\Seen")
        M.logout()
    except Exception as e:
        log.warning("outreach_reply_poll_failed", error=str(e))

    if scanned:
        log.info("outreach_reply_poll_run", scanned=scanned, stopped=stopped)
    return {"scanned": scanned, "stopped": stopped}
