# ReelSkill — Agent Reference (CLAUDE.md)

> **Maintenance rule:** This file and `CONTEXT.md` are the project's memory. After every
> working session / response that changes code, behavior, or decisions, update
> `CONTEXT.md` (session log, current state, next steps). Update this file only when the
> architecture, file map, or conventions change.

## What this project is

**ReelSkill**: DM a tutorial Instagram Reel to a bot account → a Gemini agent (Google ADK
2.x) watches the video, extracts every step (including *inferred* steps the fast-cut edit
skipped), resolves the resources the tutorial depends on via Google Search, asks the user
clarifying questions **in the same DM thread** when something can't be found, and delivers
the result as an installable `SKILL.md` in the user's personal library. A `find-skills`
meta-skill (installed once in Claude Code / Cursor) then routes future tasks to the right
saved skill automatically.

This collapses three product ideas into one loop: capture (DM trigger, like Slack→Notion
automations), execution knowledge (skill packaging with gap-filling), and recall (the
meta-skill router). Origin story and product rationale: see the prior chat summary in
`CONTEXT.md`.

## Load-bearing facts (verified, do not re-derive)

1. **Instagram trigger is supported, not a hack.** Meta's Instagram Messaging API sends a
   `messages` webhook when someone DMs the bot; a shared Reel arrives as an `ig_reel`
   attachment with `title` (caption), `reel_video_id`, and a **CDN URL to the MP4**.
   CDN URLs expire → download immediately on webhook receipt. Replies go back in-thread
   via the Send API (`/me/messages`). ManyChat-style no-code tools can't handle `ig_reel`.
2. **Google ADK 2.x** (`pip install google-adk`, verified 2.3.0 at build time) + Gemini's
   native video ingestion = the "watch the reel" step is one multimodal call
   (`types.Part.from_bytes(data=..., mime_type="video/mp4")`), no frame extraction.
3. Meta **dev mode** lets you test the full DM loop with your own account before Advanced
   Access review of `instagram_business_manage_messages`.

## File map

```
CLAUDE.md                     ← this file (architecture + conventions)
CONTEXT.md                    ← running state: session log, decisions, next steps
README.md                     ← user-facing setup guide (Meta app wiring, CLI usage)
requirements.txt              ← google-adk, fastapi, uvicorn, httpx, python-dotenv
.env.example                  ← GOOGLE_API_KEY, IG_VERIFY_TOKEN, IG_ACCESS_TOKEN, IG_APP_SECRET, REELSKILL_MODEL
                                (requirements now also include mcp==1.28.1)
cli.py                        ← run the full pipeline on a local mp4; stdin = DM thread
mcp_server.py                 ← FastMCP stdio server: list_skills, get_skill,
                                learn_from_video (full pipeline), answer_pending_question
sync_skills.py                ← pull a user's skill library from the server to local disk
reelskill/
  config.py                   ← env loading, model name (default gemini-flash-latest), data dirs
  server.py                   ← FastAPI: GET/POST /webhook (handshake, signature, dedupe,
                                background processing), /skills/... library, /health
  ig_client.py                ← signature verify, Send API DMs, reel download, ig_reel payload parsing
  agents.py                   ← 3 ADK agents: reel_extractor, resource_resolver (google_search,
                                built fresh per run), skill_packager
  frames.py                   ← ffmpeg frame/audio extraction (/watch-skill technique):
                                auto-scaled timestamped JPEGs + mono audio; used as the
                                >19MB pipeline fallback and the extract_video_frames MCP tool
  pipeline.py                 ← orchestration + disk-persisted clarification pause
                                (data/pending/<user>.json) resumed by the user's next text DM
  runner_utils.py             ← one-shot ADK agent invocation via InMemoryRunner, JSON→pydantic
  schemas.py                  ← ExtractedTutorial, TutorialStep (inferred + rationale),
                                RequiredResource, ResourceReport, SkillBundle
meta-skill/find-skills/
  SKILL.md                    ← the router meta-skill (reads library index, matches triggers,
                                applies verbatim prompts, ≤1 install suggestion per convo)
data/                         ← runtime storage (videos/, skills/<user>/<slug>/, pending/)
```

## Pipeline flow

```
ig_reel webhook → verify sig → dedupe mid → 200 fast, work in background
  → download MP4 (expiring CDN URL) → reel_extractor (video+caption → ExtractedTutorial)
  → resource_resolver (Google Search → ResourceReport)
  → any not_found? → persist state to data/pending/<user>.json + DM a question
       (user's next plain-text DM → resume_with_answer → continue)
  → skill_packager (→ SkillBundle) → write SKILL.md + update index.json → confirm via DM
```

## Key design decisions

- **Disk-persisted pause, not ADK in-memory workflow suspension** — DM replies can arrive
  hours later, across restarts/redeploys.
- **Skill descriptions must start with "Use when…"** — the find-skills router selects
  skills by matching descriptions against the current task.
- **Inferred steps are first-class** (`inferred=True` + `inference_rationale`) — this is
  the "watch and rebuild" differentiator; fast-cut reels always skip steps.
- **`resource_resolver` built fresh per run** — `google_search` tool is stateful
  per-agent in some ADK versions.
- **Inline video ≤19 MB goes to Gemini whole; larger falls back to /watch-style frames**
  (`frames.py`: sampled timestamped JPEGs + mono audio, ffmpeg required).
- **Trigger-word gating (`IG_TRIGGER_WORD`, default "claude")** — personal-account mode:
  reels are downloaded immediately (CDN expires) but stashed in `data/inbox/<user>.json`
  until a DM containing the trigger word arrives; extra text in that message is passed as
  instruction. Clarification answers don't need the trigger. Empty = bot-account mode.
  Webhooks only fire for messages *received* by the professional account, so the user
  sends from their main account to their converted second account.
- **`resource_resolver` has no `output_schema`** — Gemini rejects combining the built-in
  `google_search` tool with function calling (400 INVALID_ARGUMENT); the agent is
  prompted to emit raw JSON which `runner_utils` validates against `ResourceReport`.
- **`_strip_fences` only strips a whole-payload fence** — generated SKILL.md bodies
  contain inner ``` code blocks, so an inner-fence regex search corrupts the JSON.
- **Meta-skill over Chrome extension** for the "knowing when to use it" half — ships in a
  day, no store review, no platform risk. Extension is a possible v2.
- **MCP server as a second consumption path** — makes the reel-derived library (and the
  pipeline itself) a tool surface for any MCP client; also satisfies the Kaggle capstone
  "MCP Server" key concept.

## Hackathon framing (Kaggle AI Agents Intensive Capstone)

Track: **Concierge Agents** (fallback: Freestyle). Key concepts demonstrated (need ≥3):
multi-agent ADK system (`agents.py`/`pipeline.py`), MCP server (`mcp_server.py`),
security (HMAC webhook signature, path-traversal guard, no keys in code), agent skills
(generated SKILL.md bundles + `find-skills` router), deployability (uvicorn/ngrok dev,
Cloud Run — show in video). Submission needs: Kaggle Writeup ≤2500 words, cover image,
≤5-min YouTube video, public repo link.

## Conventions

- Python 3.11+ style: `X | None`, pydantic v2 (`model_validate`, `model_dump_json`).
- All agent I/O is structured: pydantic `output_schema` on every agent; `runner_utils`
  strips code fences and validates.
- Server must ACK Meta within seconds → all real work in `BackgroundTasks`.
- Windows dev environment (PowerShell); paths via `pathlib` everywhere.

## Testing without Meta

`python cli.py path\to\video.mp4 --caption "..."` runs the identical pipeline with stdin
playing the DM thread. Requires only `GOOGLE_API_KEY` in `.env`.
