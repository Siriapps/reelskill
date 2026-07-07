"""Thin client for the Instagram Messaging API (Instagram API with Instagram Login)."""

import asyncio
import hashlib
import hmac
import logging
import subprocess
import sys
from pathlib import Path

import httpx

from .config import GRAPH_API_BASE, IG_ACCESS_TOKEN, IG_APP_SECRET, VIDEO_DIR

log = logging.getLogger(__name__)

_YTDLP = Path(sys.executable).parent / ("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")


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


def _is_instagram_page(url: str) -> bool:
    return "instagram.com" in url and any(p in url for p in ("/reel/", "/p/", "/tv/"))


def _is_valid_mp4(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 10_000:
        return False
    try:
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            check=True,
            timeout=30,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


async def _http_download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)


def _ytdlp_download(url: str, dest: Path) -> None:
    """Blocking yt-dlp fetch -- same approach as the Claude /watch skill."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    cmd = [
        str(_YTDLP),
        "-f", "best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", str(dest),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[-500:]}")


async def download_reel(cdn_url: str, reel_video_id: str) -> Path:
    """Download the reel immediately. Meta often sends an instagram.com/reel/ permalink
    instead of a raw CDN mp4 -- those must go through yt-dlp to get the real video."""
    dest = VIDEO_DIR / f"{reel_video_id}.mp4"

    if cdn_url and not _is_instagram_page(cdn_url):
        try:
            await _http_download(cdn_url, dest)
            if _is_valid_mp4(dest):
                log.info("Downloaded reel %s via CDN (%d bytes)", reel_video_id, dest.stat().st_size)
                return dest
            log.warning("CDN bytes for %s were not a valid mp4; falling back to yt-dlp", reel_video_id)
        except Exception:
            log.warning("CDN download failed for %s; falling back to yt-dlp", reel_video_id, exc_info=True)

    page_url = cdn_url if cdn_url and _is_instagram_page(cdn_url) else None
    if not page_url:
        raise RuntimeError(f"No Instagram page URL to download reel {reel_video_id}")

    await asyncio.to_thread(_ytdlp_download, page_url, dest)
    if not _is_valid_mp4(dest):
        raise RuntimeError(f"yt-dlp could not produce a valid mp4 for reel {reel_video_id}")
    log.info("Downloaded reel %s via yt-dlp (%d bytes)", reel_video_id, dest.stat().st_size)
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
