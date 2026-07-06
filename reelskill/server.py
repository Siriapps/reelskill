"""FastAPI server exposing the Meta webhook endpoint and a per-user skill library."""

import json
import logging
import time
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from .config import (
    DATA_DIR,
    IG_ALLOWED_SENDERS,
    IG_APP_SECRET,
    IG_TRIGGER_WORD,
    IG_VERIFY_TOKEN,
    SKILLS_DIR,
)
from .ig_client import download_reel, extract_reel_events, send_dm, verify_signature
from .pipeline import process_reel, resume_with_answer

# Reels held in personal-account mode until the trigger word arrives in the thread.
INBOX_DIR = DATA_DIR / "inbox"
INBOX_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("reelskill.server")

app = FastAPI(title="ReelSkill", version="0.1.0")

_seen_message_ids: set[str] = set()


@app.on_event("startup")
async def warn_if_unguarded() -> None:
    if not IG_APP_SECRET:
        log.warning(
            "IG_APP_SECRET is empty: webhook signature verification is DISABLED. "
            "Fine for local testing; set it before exposing this server."
        )
    if not IG_ALLOWED_SENDERS:
        log.warning(
            "IG_ALLOWED_SENDERS is empty: events from ANY sender will be processed. "
            "Set it to your own Instagram-scoped ID (logged on each event) to lock down."
        )


@app.get("/webhook")
async def webhook_verify(
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
):
    """Meta webhook verification handshake."""
    if mode == "subscribe" and token == IG_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def webhook_receive(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not verify_signature(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="Bad signature")

    payload = json.loads(body)
    for event in extract_reel_events(payload):
        # Personal-agent guardrail: only the owner's account may drive the pipeline.
        log.info("Webhook event from sender %s", event["sender_id"])
        if IG_ALLOWED_SENDERS and event["sender_id"] not in IG_ALLOWED_SENDERS:
            log.warning("Ignoring event from non-allowlisted sender %s", event["sender_id"])
            continue
        mid = event.get("message_id")
        if mid and mid in _seen_message_ids:
            continue
        if mid:
            _seen_message_ids.add(mid)
        # Must return 200 fast or Meta retries; do the real work in the background.
        background.add_task(_handle_event, event)
    return Response(status_code=200)


def _inbox_file(sender: str) -> Path:
    return INBOX_DIR / f"{sender}.json"


def _stash_reel(sender: str, video: Path, caption: str) -> None:
    _inbox_file(sender).write_text(
        json.dumps({"video": str(video), "caption": caption, "ts": time.time()}),
        encoding="utf-8",
    )


def _pop_stashed_reel(sender: str) -> dict | None:
    f = _inbox_file(sender)
    if not f.exists():
        return None
    stash = json.loads(f.read_text(encoding="utf-8"))
    f.unlink()
    return stash


async def _handle_event(event: dict) -> None:
    sender = event["sender_id"]
    try:
        if event["cdn_url"]:
            # Download immediately either way: CDN attachment URLs expire.
            video = await download_reel(event["cdn_url"], event["reel_video_id"])
            caption = event.get("title") or ""
            if IG_TRIGGER_WORD:
                # Personal-account mode: hold silently until the trigger word arrives,
                # so ordinary reel shares in the thread are left alone.
                _stash_reel(sender, video, caption)
                return
            await send_dm(sender, "Got it -- watching that reel now. Give me a minute...")
            result = await process_reel(sender, video, caption=caption)
            await send_dm(sender, result.message)

        elif event.get("text"):
            text = event["text"]
            triggered = IG_TRIGGER_WORD and IG_TRIGGER_WORD in text.lower()

            if triggered and (stash := _pop_stashed_reel(sender)):
                await send_dm(sender, "On it -- watching that reel now. Give me a minute...")
                # Anything typed alongside the trigger word is extra instruction.
                extra = text.lower().replace(IG_TRIGGER_WORD, "").strip()
                caption = stash["caption"] + (f"\n\nUser instruction: {extra}" if extra else "")
                result = await process_reel(sender, Path(stash["video"]), caption=caption)
                await send_dm(sender, result.message)
                return

            # A pending clarification answer doesn't need the trigger word.
            result = await resume_with_answer(sender, text)
            if result:
                await send_dm(sender, result.message)
            elif triggered:
                await send_dm(
                    sender,
                    f"No reel waiting. Share a reel to this chat, then say '{IG_TRIGGER_WORD}' "
                    "and I'll turn it into a reusable skill.",
                )
            elif not IG_TRIGGER_WORD:
                await send_dm(
                    sender,
                    "Share a reel to this chat and I'll turn it into a reusable skill for your AI tools.",
                )
            # else: personal-account mode, untriggered chatter -- stay silent.
    except Exception:
        log.exception("Failed to handle event from %s", sender)
        try:
            await send_dm(sender, "Something went wrong processing that. Try sharing it again.")
        except Exception:
            log.exception("Also failed to notify %s", sender)


@app.get("/skills/{user_id}/index.json")
async def skill_index(user_id: str):
    index = SKILLS_DIR / user_id / "index.json"
    if not index.exists():
        raise HTTPException(status_code=404, detail="No skills yet")
    return json.loads(index.read_text(encoding="utf-8"))


@app.get("/skills/{user_id}/{slug}/SKILL.md")
async def skill_file(user_id: str, slug: str):
    path = (SKILLS_DIR / user_id / slug / "SKILL.md").resolve()
    if not path.is_relative_to(SKILLS_DIR.resolve()) or not path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/health")
async def health():
    return {"ok": True}
