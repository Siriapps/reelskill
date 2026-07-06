"""MCP server exposing the ReelSkill library and pipeline to any MCP client (Claude, Cursor).

This is the third leg of the loop: Instagram DMs capture knowledge, the ADK pipeline
turns it into skills, and this server makes that knowledge a tool surface -- an
MCP-capable agent can browse the user's reel-derived skills, apply one, or feed a new
video through the same pipeline the Instagram trigger uses.

Run (stdio transport): python mcp_server.py

Claude Desktop / Cursor registration (stdio):
    {"command": "<path-to>/.venv/Scripts/python.exe", "args": ["<path-to>/mcp_server.py"]}
"""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from reelskill.config import SKILLS_DIR
from reelskill.frames import extract_audio, extract_frames
from reelskill.pipeline import process_reel, resume_with_answer

mcp = FastMCP("reelskill")

# The CLI and MCP paths share this id, so skills built either way land in one library.
DEFAULT_USER = "local-user"


def _result_json(status: str, message: str, skill_path: Path | None = None) -> str:
    return json.dumps(
        {"status": status, "message": message, "skill_path": str(skill_path) if skill_path else None}
    )


@mcp.tool()
def list_skills(user_id: str = DEFAULT_USER) -> str:
    """List every skill in the user's library. Each entry has a slug, name, and a
    description starting with 'Use when...' -- match those trigger conditions against
    the current task to decide which skill to apply."""
    index = SKILLS_DIR / user_id / "index.json"
    if not index.exists():
        return json.dumps({"skills": []})
    return index.read_text(encoding="utf-8")


@mcp.tool()
def get_skill(slug: str, user_id: str = DEFAULT_USER) -> str:
    """Fetch the full SKILL.md for one skill by slug. Follow its numbered steps and use
    its verbatim prompts/commands; steps marked inferred were reconstructed from a
    fast-cut video, so verify their output before continuing."""
    path = (SKILLS_DIR / user_id / slug / "SKILL.md").resolve()
    # Same path-traversal guard as the HTTP library endpoint in server.py.
    if not path.is_relative_to(SKILLS_DIR.resolve()) or not path.exists():
        raise ValueError(f"No skill '{slug}' for user '{user_id}'")
    return path.read_text(encoding="utf-8")


@mcp.tool()
async def learn_from_video(video_path: str, caption: str = "", user_id: str = DEFAULT_USER) -> str:
    """Watch a local tutorial video (mp4) and turn it into a new skill in the library.

    Runs the identical ADK pipeline the Instagram DM trigger uses: extract steps
    (inferring the ones the edit skipped), resolve required resources via Google
    Search, package a SKILL.md. If a resource cannot be found, status is
    'needs_input' and the message contains a question -- answer it with the
    answer_pending_question tool to finish the skill."""
    video = Path(video_path)
    if not video.exists():
        raise ValueError(f"Video not found: {video_path}")
    result = await process_reel(user_id, video, caption=caption)
    return _result_json(result.status, result.message, result.skill_path)


@mcp.tool()
async def answer_pending_question(answer: str, user_id: str = DEFAULT_USER) -> str:
    """Provide the missing resource or answer for a paused skill build (started by
    learn_from_video or by a reel shared over Instagram DM), completing the skill."""
    result = await resume_with_answer(user_id, answer)
    if result is None:
        return _result_json("none", "Nothing is pending for this user.")
    return _result_json(result.status, result.message, result.skill_path)


@mcp.tool()
def extract_video_frames(video_path: str) -> str:
    """Extract timestamped JPEG frames (auto-scaled count, 512px wide) plus a mono
    audio track from a local video, /watch-skill style. Returns the file paths --
    Read the frames in chronological order to 'watch' the video yourself instead of
    (or before) running the full learn_from_video pipeline."""
    video = Path(video_path)
    if not video.exists():
        raise ValueError(f"Video not found: {video_path}")
    frames = extract_frames(video)
    audio = extract_audio(video)
    return json.dumps({
        "frames": [str(f) for f in frames],
        "audio": str(audio) if audio else None,
        "note": "Filenames carry tMM-SS timestamps; read frames in order and align with audio.",
    })


if __name__ == "__main__":
    mcp.run()
