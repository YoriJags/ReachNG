"""Direct IMAP/SMTP — EYO reads and replies to a client's mailbox without Unipile.

  parse_email_message(raw)  — pure: pull from/subject/plain-body out of an RFC822
                              message (decodes MIME headers + multipart).
  poll_client_inbox(client) — fetch UNSEEN, hand each to the brain (handle_inbound_email),
                              mark seen.
  send_email_via_client(...) — send an approved reply FROM the client's mailbox
                              over their SMTP. This closes the email loop.

Best-effort + defensive: a mailbox hiccup logs and moves on, never raises into
the scheduler or the send path.
"""
from __future__ import annotations

import email as _email
import re
from email.header import decode_header, make_header
from typing import Optional

import structlog

log = structlog.get_logger()

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _decode_hdr(s: Optional[str]) -> str:
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def _plain_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
               "attachment" not in str(part.get("Content-Disposition") or "").lower():
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
        return ""
    try:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            return payload.decode(msg.get_content_charset() or "utf-8", "replace")
    except Exception:
        pass
    return msg.get_payload() if isinstance(msg.get_payload(), str) else ""


def parse_email_message(raw: bytes) -> dict:
    """{from_email, from_name, subject, body} from an RFC822 message."""
    msg = _email.message_from_bytes(raw)
    from_hdr = _decode_hdr(msg.get("From"))
    m = _EMAIL_RE.search(from_hdr or "")
    from_email = m.group(0).lower() if m else ""
    from_name = None
    if "<" in (from_hdr or ""):
        from_name = from_hdr.split("<", 1)[0].strip().strip('"') or None
    return {
        "from_email": from_email,
        "from_name":  from_name,
        "subject":    _decode_hdr(msg.get("Subject")),
        "body":       (_plain_body(msg) or "").strip(),
    }


def poll_client_inbox(client_doc: dict, *, max_messages: int = 25) -> int:
    """Pull UNSEEN customer emails and draft replies (HITL). Returns count handled."""
    from services.email_creds import get_email_credentials
    creds = get_email_credentials(client_doc)
    if not creds:
        return 0
    imap_cfg = creds["imap"]
    handled = 0
    try:
        import imaplib
        if imap_cfg.get("use_ssl", True):
            M = imaplib.IMAP4_SSL(imap_cfg["host"], int(imap_cfg.get("port", 993)))
        else:
            M = imaplib.IMAP4(imap_cfg["host"], int(imap_cfg.get("port", 143)))
        M.login(creds["username"], creds["password"])
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN")
        ids = (data[0].split() if data and data[0] else [])[:max_messages]
        from services.email_inbound import handle_inbound_email
        for mid in ids:
            typ, md = M.fetch(mid, "(RFC822)")
            if not md or not md[0]:
                continue
            parsed = parse_email_message(md[0][1])
            if parsed["from_email"] and parsed["body"]:
                handle_inbound_email(
                    account_id=creds["username"],
                    from_email=parsed["from_email"],
                    from_name=parsed["from_name"],
                    subject=parsed["subject"],
                    body=parsed["body"],
                    client=client_doc,
                )
                handled += 1
            M.store(mid, "+FLAGS", "\\Seen")
        M.logout()
    except Exception as e:
        log.warning("imap_poll_failed", client=client_doc.get("name"), error=str(e))
    return handled


def poll_all_email_inboxes() -> dict:
    """Scheduler entry: poll every IMAP-provider client. Best-effort per client."""
    from database import get_db
    clients = list(get_db()["clients"].find(
        {"active": True, "email_provider": "imap"},
        {"name": 1, "email_imap": 1, "email_smtp": 1, "email_username": 1,
         "email_password_enc": 1, "email_provider": 1}))
    total = 0
    for c in clients:
        try:
            total += poll_client_inbox(c)
        except Exception as e:
            log.warning("imap_client_poll_failed", client=c.get("name"), error=str(e))
    if clients:
        log.info("imap_poll_run", clients=len(clients), handled=total)
    return {"clients": len(clients), "handled": total}


def send_email_via_client(client_doc: dict, *, to_email: str, subject: str,
                          body: str) -> bool:
    """Send an approved reply FROM the client's own mailbox over their SMTP.
    Closes the email loop. Returns True on success. Never raises."""
    from services.email_creds import get_email_credentials
    creds = get_email_credentials(client_doc)
    if not creds:
        return False
    smtp_cfg = creds["smtp"]
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject or "Re: your message"
        msg["From"] = creds["username"]
        msg["To"] = to_email
        host = smtp_cfg["host"]
        port = int(smtp_cfg.get("port", 465))
        if smtp_cfg.get("use_ssl", True):
            with smtplib.SMTP_SSL(host, port) as s:
                s.login(creds["username"], creds["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as s:
                s.starttls()
                s.login(creds["username"], creds["password"])
                s.send_message(msg)
        log.info("email_sent_via_client", client=client_doc.get("name"))
        return True
    except Exception as e:
        log.warning("email_send_via_client_failed",
                    client=client_doc.get("name"), error=str(e))
        return False
