# CONTEXT.md — Running project state

> Update this file after every response/session. Newest entries first in the log.
> `CLAUDE.md` holds the stable reference (architecture, file map, conventions).

## Current state

- **Code:** MVP complete and now VERIFIED END-TO-END against live Gemini (2026-07-06):
  `process_reel` on a synthetic ffmpeg test clip produced a correct, gap-filled
  SKILL.md (`data/skills/test-user/generate-color-test-pattern-video-ffmpeg/`),
  including 3 correctly inferred steps with rationale.
- **Environment:** `.venv` in this folder; `GOOGLE_API_KEY` is set in `.env` (IG tokens
  still empty). ffmpeg 8.1.2 installed and working.
- **New since transfer:** MCP server (5 tools incl. `extract_video_frames`),
  /watch-style frame fallback (`frames.py`), trigger-word gating for
  personal-account mode (`IG_TRIGGER_WORD=claude` default).
- **Live bugs found & fixed during e2e:** (1) `google_search` + `output_schema` →
  400 from Gemini; resolver now prompts for raw JSON instead. (2) `_strip_fences`
  regex grabbed inner ```bash blocks inside skill_markdown; now only strips a
  whole-payload fence. (3) `gemini-flash-latest` hit 503 high-demand; consider
  pinning `REELSKILL_MODEL=gemini-2.5-flash` if it recurs.

## Blockers / needs from the user

1. Instagram wiring only: convert the second account to a (free) professional account +
   Meta app with `messages` webhook subscribed (README §3). Dev mode suffices for the
   demo; public launch needs Advanced Access review.

## Next steps (in order)

1. Run `python cli.py <real-reel.mp4>` on 2–3 actual saved reels to judge extraction
   quality on real content (synthetic clip already passes).
2. Wire the Meta app in dev mode; test share-reel → say "claude" → DM reply loop.
3. Push to public GitHub repo; record ≤5-min video; write Kaggle Writeup + cover image;
   submit before deadline (drafts don't count).
4. Parked: persistent message-id dedupe, multiple pending clarifications per user,
   per-user auth on library endpoints, Cloud Run deployment, Chrome extension.

## Hackathon plan (deadline ~1 day away)

Target: Kaggle AI Agents Intensive Vibe Coding Capstone, **Concierge Agents** track.
Remaining work, in priority order:

1. **User: put `GOOGLE_API_KEY` in `.env`** → run `python cli.py <reel.mp4>` on 2–3 real
   saved reels; iterate on `agents.py` instructions if extraction/gap-fill is weak.
   This is the only blocker for a credible demo.
2. Push to a **public GitHub repo** (project link is required; live deploy is optional).
3. Record the **≤5-min YouTube video**: problem (graveyard of saved reels) → why agents
   → architecture diagram → demo (share reel → DM Q&A → SKILL.md → Claude applies it via
   MCP/find-skills) → build (ADK 2.3, Gemini video, Meta webhook, MCP).
4. Write the **Kaggle Writeup** (≤2500 words) + cover image; attach video + repo link;
   click Submit before the deadline (drafts don't count).

## Session log

### 2026-07-06 — /watch integration, trigger-word mode, first live e2e
- Added `reelskill/frames.py`: ffmpeg frame sampling (auto-scaled 30–100 frames,
  512px, timestamped filenames) + mono 16kHz audio — the technique from the popular
  Claude /watch skill (bradautomates/claude-video). Pipeline uses it as the >19MB
  fallback; MCP server exposes it as `extract_video_frames`.
- Added personal-account trigger mode: `IG_TRIGGER_WORD` (default "claude"). Reels are
  downloaded immediately but stashed (`data/inbox/`) until a DM with the trigger word;
  extra text rides along as instruction; untriggered chatter is ignored.
- Documented all env vars + costs in `.env.example` (everything needed is free).
- **First live Gemini e2e run passed** (synthetic ffmpeg tutorial clip → correct
  SKILL.md with 3 inferred steps). Fixed two real bugs found by the run: resolver
  output_schema × google_search conflict; `_strip_fences` inner-fence corruption.

### 2026-07-05 (late) — MCP server + hackathon direction
- Answered the framing question: Instagram-as-trigger already true (webhook = Slack-style
  mention); Instagram-as-MCP made literal by adding `mcp_server.py`.
- Added `mcp_server.py` (FastMCP, stdio): `list_skills`, `get_skill`, `learn_from_video`
  (full ADK pipeline on a local mp4), `answer_pending_question`. Pinned `mcp==1.28.1`.
  Smoke-tested: all 4 tools register; `list_skills` returns `{"skills": []}` on empty lib.
- Updated README (MCP consumption path + registration snippet) and CLAUDE.md
  (file map, design decisions, hackathon framing: 5 rubric concepts covered).

### 2026-07-05 — Transfer into kaggle workspace
- Copied all project files (14 files, minus `.venv`/`__pycache__`) from
  `C:\Users\siria\reelskill` to `c:\Users\siria\OneDrive\Documents\code\kaggle` via robocopy.
- Created `CLAUDE.md` (stable reference) and this `CONTEXT.md` (running state).
- Recreated the virtualenv and installed `requirements.txt` in the new location.

### (prior, at C:\Users\siria\reelskill) — MVP build
- Validated the two load-bearing facts (ig_reel webhook attachment with CDN URL;
  Google ADK 2.3.0 with Gemini native video) before building.
- Built: FastAPI webhook server, IG client, 3-agent ADK pipeline with disk-persisted
  clarification pause, skill packaging + per-user library + index, `find-skills`
  meta-skill, `cli.py` local test harness, `sync_skills.py`.
- Smoke-tested handshake/signature/webhook-POST live; unit-tested payload parsing;
  lints clean. Chose disk-persisted pauses over ADK in-memory suspension deliberately.
