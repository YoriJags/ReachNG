"""
Inbound media download — fetch image bytes from WhatsApp providers.

Supports both Meta Cloud API (2-step: media-id → URL → bytes) and Unipile
(direct attachment fetch by message_id + attachment_id).

Returns (bytes, mime_type). Raises on any HTTP error so callers can decide
to fall back gracefully.
"""
from __future__ import annotations

import httpx
import structlog

from config import get_settings

log = structlog.get_logger()


# ─── Meta Cloud API ───────────────────────────────────────────────────────────

async def download_meta_media(media_id: str) -> tuple[bytes, str]:
    """
    Download an image from Meta Cloud API by media_id.

    Two-step:
      1. GET /v19.0/{media_id}  →  {url: "https://lookaside.fbsbx.com/whatsapp_business/..."}
      2. GET that url (Bearer token) → bytes

    Returns (image_bytes, mime_type).
    """
    settings = get_settings()
    token = settings.meta_access_token
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        meta_resp = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        media_url = meta.get("url")
        mime = meta.get("mime_type") or "image/jpeg"
        if not media_url:
            raise RuntimeError("meta media url missing from response")

        bin_resp = await client.get(media_url, headers={"Authorization": f"Bearer {token}"})
        bin_resp.raise_for_status()
        return bin_resp.content, mime


# ─── Unipile ──────────────────────────────────────────────────────────────────

async def download_unipile_attachment(
    message_id: str,
    attachment_id: str,
) -> tuple[bytes, str]:
    """
    Download an attachment from Unipile by message_id + attachment_id.
    Endpoint: GET {dsn}/api/v1/messages/{message_id}/attachments/{attachment_id}
    """
    settings = get_settings()
    dsn = settings.unipile_dsn
    api_key = settings.unipile_api_key
    if not (dsn and api_key):
        raise RuntimeError("Unipile DSN / API key not configured")

    url = f"https://{dsn}/api/v1/messages/{message_id}/attachments/{attachment_id}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers={"X-API-KEY": api_key})
        resp.raise_for_status()
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return resp.content, mime


# ─── Payload parsing ──────────────────────────────────────────────────────────

def extract_meta_image(msg: dict) -> tuple[str, str] | None:
    """Pull (media_id, mime_type) from a Meta inbound message, if it's an image."""
    if msg.get("type") != "image":
        return None
    image = msg.get("image") or {}
    media_id = image.get("id")
    mime = image.get("mime_type") or "image/jpeg"
    if not media_id:
        return None
    return media_id, mime


def extract_meta_audio(msg: dict) -> tuple[str, str] | None:
    """Pull (media_id, mime_type) from a Meta inbound message, if it's audio/voice.

    Meta delivers WhatsApp voice notes as type=='audio' with `audio` payload.
    Some carriers also send normal audio recordings under the same type.
    """
    if msg.get("type") not in {"audio", "voice"}:
        return None
    audio = msg.get("audio") or msg.get("voice") or {}
    media_id = audio.get("id")
    mime = audio.get("mime_type") or "audio/ogg"
    if not media_id:
        return None
    return media_id, mime


def extract_unipile_image(data: dict) -> tuple[str, str, str] | None:
    """
    Pull (message_id, attachment_id, mime_type) from a Unipile inbound payload,
    if the first attachment is an image.

    Unipile attachment shape (typical):
      data.attachments = [{id, name, mimetype, ...}]
      data.id = message_id
    """
    attachments = data.get("attachments") or []
    if not attachments:
        return None
    first = attachments[0]
    mime = (first.get("mimetype") or first.get("mime_type") or "").lower()
    if not mime.startswith("image/"):
        return None
    msg_id = data.get("id") or data.get("message_id")
    att_id = first.get("id")
    if not (msg_id and att_id):
        return None
    return msg_id, att_id, mime or "image/jpeg"


def extract_unipile_audio(data: dict) -> tuple[str, str, str] | None:
    """Pull (message_id, attachment_id, mime_type) from a Unipile inbound payload,
    if the first attachment is an audio file (voice note / recording).

    Voice notes from WhatsApp via Unipile typically carry mimetype starting with
    'audio/' — common values: 'audio/ogg', 'audio/mpeg', 'audio/mp4', 'audio/m4a'.
    """
    attachments = data.get("attachments") or []
    if not attachments:
        return None
    first = attachments[0]
    mime = (first.get("mimetype") or first.get("mime_type") or "").lower()
    if not mime.startswith("audio/"):
        return None
    msg_id = data.get("id") or data.get("message_id")
    att_id = first.get("id")
    if not (msg_id and att_id):
        return None
    return msg_id, att_id, mime or "audio/ogg"
