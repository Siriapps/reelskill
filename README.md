# ReelSkill

DM an Instagram Reel to your bot account and get back an installable agent skill.

**The loop:** share a tutorial Reel to the bot's Instagram DMs → a Gemini agent (built on
Google ADK 2.x) watches the video, extracts every step, infers the steps the fast-cut edit
skipped, and hunts down the templates/docs the tutorial depends on → if something can't be
found, the bot asks you in the same DM thread → the result is packaged as a `SKILL.md` in
your personal library → the `find-skills` meta-skill (installed once in Claude Code /
Cursor) routes your future tasks to the right saved skill automatically.

## Architecture

```
Instagram DM (share a Reel)
      │  Meta webhook: ig_reel attachment {url, title, reel_video_id}
      ▼
FastAPI server (reelskill/server.py)
  - verifies X-Hub-Signature-256, dedupes message ids, ACKs fast
  - downloads the video immediately (CDN URLs expire)
      ▼
ADK pipeline (reelskill/pipeline.py, reelskill/agents.py) — Gemini, google-adk 2.3
  1. reel_extractor    video+caption → ExtractedTutorial (steps, verbatim prompts,
                       inferred gap-fill steps, required resources, trigger conditions)
  2. resource_resolver Google Search → working URLs; flags what it can't find
  3. [pause]           unresolved resources → clarifying DM; state persisted to disk,
                       resumes when the user replies in the same thread
  4. skill_packager    → SkillBundle → data/skills/<user>/<slug>/SKILL.md + index.json
      ▼
Skill library, served at /skills/<user>/... → synced locally by sync_skills.py
      ▼
Consumption layer (two ways):
  - find-skills meta-skill: picks the right saved skill per task, tightens prompts,
    suggests unsynced skills
  - MCP server (mcp_server.py): exposes the library and the pipeline itself as MCP
    tools, so any MCP client (Claude Desktop, Cursor) can browse skills, apply one,
    or learn a new skill from a video directly
```

## Setup

### 1. Environment

```powershell
cd reelskill
.venv\Scripts\Activate.ps1        # deps already installed; else: pip install -r requirements.txt
copy .env.example .env             # then fill it in
```

`.env` values:

| Variable | What |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini API key (aistudio.google.com/apikey) — required |
| `IG_VERIFY_TOKEN` | Any string; must match what you enter in the Meta App Dashboard |
| `IG_ACCESS_TOKEN` | Instagram User access token with messaging permissions |
| `IG_APP_SECRET` | Meta app secret (enables webhook signature verification) |
| `REELSKILL_MODEL` | Optional, defaults to `gemini-flash-latest` |
| `IG_TRIGGER_WORD` | Default `claude`. Personal-account mode: shared reels are held silently until a DM containing this word arrives (like @-mentioning a Slack bot). Set empty to process every reel immediately. |

Everything above is obtainable for free: the Gemini API key has a free tier that covers
this workload, the verify token is a string you invent, and the Meta app + professional
account conversion + access token + app secret cost nothing.

### 2. Try it locally first (no Meta app needed)

```powershell
python cli.py path\to\tutorial.mp4 --caption "the reel caption"
```

This runs the exact same pipeline the webhook uses, with stdin standing in for the DM
thread. The skill lands in `data/skills/local-user/`.

### 3. Instagram wiring

1. Convert the bot account to an **Instagram professional account**.
2. Create a Meta app (developers.facebook.com) → add the **Instagram** product with
   Instagram API with Instagram Login.
3. Run the server and expose it: `uvicorn reelskill.server:app --port 8000` plus a
   tunnel (`ngrok http 8000`) or a real deployment (Cloud Run works well).
4. In the App Dashboard, set the webhook callback URL to `https://<host>/webhook` with
   your `IG_VERIFY_TOKEN`, and subscribe to the **`messages`** field. Note the dashboard
   banner: webhooks are only delivered once the app is in **published (Live) state** --
   flip the app to Live (this may require filling in a privacy policy URL in Settings >
   Basic). Tester-gating still applies, so going Live does not open the bot to strangers.
5. Generate an access token for the bot account → `IG_ACCESS_TOKEN`.
6. Dev mode: only accounts with a role on the app can DM the bot — enough to test the
   whole loop with your own account. Public launch needs Advanced Access app review for
   `instagram_business_manage_messages`.

Now share any Reel to the bot's DMs. It replies in-thread, asks questions in-thread if a
resource is missing, and confirms when the skill is saved.

**Personal-account mode (recommended):** the receiving account doesn't need to be a
dedicated bot -- any second account you own works after converting it to a (free)
professional account. With `IG_TRIGGER_WORD` set, sharing reels to that account does
nothing until you follow up with a message containing the trigger word (e.g. share a
reel, then type "claude"). Anything else in the trigger message is passed to the agent
as extra instruction ("claude, focus on the prompts they use"). Untriggered chatter in
the thread is ignored, so the account behaves like a normal account otherwise. One
constraint: the webhook only fires for messages *received* by the professional account,
so send from your main account to the converted one -- true message-yourself notes on
the same account don't generate webhooks.

### 4. Install the meta-skill

```powershell
python sync_skills.py --server https://<host> --user <your-ig-scoped-id>
```

Then copy `meta-skill/find-skills/` into your agent's skills directory (e.g.
`~/.claude/skills/` for Claude Code, or `.cursor/skills/` in a project). From then on the
agent checks your library on every task and applies the right saved skill.

### 5. MCP server (optional, instead of / alongside the meta-skill)

Register `mcp_server.py` as a stdio MCP server in Claude Desktop or Cursor:

```json
{
  "mcpServers": {
    "reelskill": {
      "command": "<project>\\.venv\\Scripts\\python.exe",
      "args": ["<project>\\mcp_server.py"]
    }
  }
}
```

Tools exposed: `list_skills`, `get_skill`, `learn_from_video` (runs the full ADK
pipeline on a local mp4), and `answer_pending_question` (resumes a paused build).
This makes the reel-derived library — and the pipeline itself — directly callable
from any MCP-capable agent.

## How videos get "watched"

Short reels (≤19 MB) are handed to Gemini whole -- it ingests video natively. Larger
videos fall back to the technique behind the popular Claude `/watch` skill
(bradautomates/claude-video): `reelskill/frames.py` uses ffmpeg to sample auto-scaled,
timestamped JPEG frames (30-100 depending on length, 512px wide) plus a mono 16 kHz
audio track, and the extractor agent reconstructs the tutorial from frames + audio.
The same extraction is exposed as the `extract_video_frames` MCP tool so a Claude-side
agent can Read the frames and watch frame by frame itself. Requires `ffmpeg`
(`winget install ffmpeg` on Windows).

## Known limits (MVP)

- One pending clarification per user at a time (`data/pending/<user>.json`); a second
  reel shared while one is pending replaces the pending state's answer routing.
- Message-id dedupe is in-memory; restart may reprocess a retried webhook delivery.
- `ig_reel` webhook delivery requires the reel to be shareable; some creators disable it.
