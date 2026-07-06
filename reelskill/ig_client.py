"""Thin client for the Instagram Messaging API (Instagram API with Instagram Login)."""

import hashlib
import hmac
import logging
from pathlib import Path

import httpx

from .config import GRAPH_API_BASE, IG_ACCESS_TOKEN, IG_APP_SECRET, VIDEO_DIR

log = logging.getLogger(__name__)


def verify_signature(payload: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 from Meta. Skipped if no app secret is configured (dev mode)."""
    if not IG_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(IG_APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


async def send_dm(recipient_igsid: str, text: str) -> None:
    """Reply in the same DM thread via the Send API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GRAPH_API_BASE}/me/messages",
            params={"access_token": IG_ACCESS_TOKEN},
            json={"recipient": {"id": recipient_igsid}, "message": {"text": text[:1000]}},
        )
    if resp.status_code >= 400:
        log.error("Send API error %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()


async def download_reel(cdn_url: str, reel_video_id: str) -> Path:
    """Download the reel immediately -- Meta CDN attachment URLs expire quickly."""
    dest = VIDEO_DIR / f"{reel_video_id}.mp4"
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", cdn_url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    log.info("Downloaded reel %s -> %s (%d bytes)", reel_video_id, dest, dest.stat().st_size)
    return dest


def extract_reel_events(webhook_body: dict) -> list[dict]:
    """Pull (sender, reel) pairs out of a messages webhook payload.

    Returns dicts: {sender_id, reel_video_id, cdn_url, title, message_id, text}
    Plain-text messages (user replies to clarification questions) are returned
    with reel fields set to None.
    """
    events: list[dict] = []
    for entry in webhook_body.get("entry", []):
        for messaging in entry.get("messaging", []):
            message = messaging.get("message") or {}
            if message.get("is_echo"):
                continue
            sender_id = (messaging.get("sender") or {}).get("id")
            if not sender_id:
                continue
            base = {
                "sender_id": sender_id,
                "message_id": message.get("mid"),
                "text": message.get("text"),
                "reel_video_id": None,
                "cdn_url": None,
                "title": None,
            }
            attachments = message.get("attachments") or []
            reels = [a for a in attachments if a.get("type") in ("ig_reel", "reel")]
            if not reels:
                events.append(base)
                continue
            for att in reels:
                payload = att.get("payload") or {}
                events.append(
                    base
                    | {
                        "reel_video_id": str(payload.get("reel_video_id") or payload.get("id") or ""),
                        "cdn_url": payload.get("url"),
                        "title": payload.get("title") or "",
                    }
                )
    return events
