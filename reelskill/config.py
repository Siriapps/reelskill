import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Meta / Instagram
IG_VERIFY_TOKEN = os.getenv("IG_VERIFY_TOKEN", "reelskill-verify")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_APP_SECRET = os.getenv("IG_APP_SECRET", "")
GRAPH_API_BASE = os.getenv("GRAPH_API_BASE", "https://graph.instagram.com/v23.0")

# Trigger word for personal-account mode: reels are held silently until a DM text
# containing this word arrives (like @-mentioning a Slack bot). Empty = process
# every shared reel immediately (dedicated bot-account mode).
IG_TRIGGER_WORD = os.getenv("IG_TRIGGER_WORD", "claude").strip().lower()

# Comma-separated Instagram-scoped sender IDs allowed to use the agent. Empty = allow
# anyone (dev mode relies on Meta's tester gating instead). The server logs each
# sender's ID, so run once, copy yours from the log, and lock it down.
IG_ALLOWED_SENDERS = frozenset(
    s.strip() for s in os.getenv("IG_ALLOWED_SENDERS", "").split(",") if s.strip()
)

# Gemini (used by google-adk); GOOGLE_API_KEY is read by the ADK itself too.
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
MODEL_NAME = os.getenv("REELSKILL_MODEL", "gemini-flash-latest")

# Storage
DATA_DIR = Path(os.getenv("REELSKILL_DATA_DIR", PROJECT_ROOT / "data"))
VIDEO_DIR = DATA_DIR / "videos"
SKILLS_DIR = DATA_DIR / "skills"

for d in (DATA_DIR, VIDEO_DIR, SKILLS_DIR):
    d.mkdir(parents=True, exist_ok=True)
