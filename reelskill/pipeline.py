"""Orchestrates the reel -> skill pipeline, including the DM clarification loop.

The clarification pause is persisted to disk (data/pending/<user_id>.json) instead of
suspending an in-memory workflow, because the user may answer the DM hours later,
after a restart or redeploy.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from google.genai import types

from .agents import build_resolver_agent, extractor_agent, packager_agent
from .config import DATA_DIR, SKILLS_DIR
from .frames import extract_audio, extract_frames
from .runner_utils import run_agent
from .schemas import ExtractedTutorial, ResourceReport, SkillBundle

log = logging.getLogger(__name__)

PENDING_DIR = DATA_DIR / "pending"
PENDING_DIR.mkdir(parents=True, exist_ok=True)

# Gemini inline media limit; larger videos fall back to /watch-style frame sampling.
MAX_INLINE_VIDEO_BYTES = 19 * 1024 * 1024


@dataclass
class PipelineResult:
    status: str  # "done" | "needs_input"
    message: str  # DM-ready text to send back to the user
    skill_path: Path | None = None


def _pending_file(user_id: str) -> Path:
    return PENDING_DIR / f"{user_id}.json"


def _save_skill(user_id: str, bundle: SkillBundle) -> Path:
    skill_dir = SKILLS_DIR / user_id / bundle.slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(bundle.skill_markdown, encoding="utf-8")

    index_file = SKILLS_DIR / user_id / "index.json"
    index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else {"skills": []}
    index["skills"] = [s for s in index["skills"] if s["slug"] != bundle.slug]
    index["skills"].append({"slug": bundle.slug, "name": bundle.name, "description": bundle.description})
    index_file.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return skill_file


async def _package(
    user_id: str, tutorial: ExtractedTutorial, resources: ResourceReport, user_answers: str = ""
) -> PipelineResult:
    prompt = (
        "TUTORIAL JSON:\n" + tutorial.model_dump_json(indent=2)
        + "\n\nRESOURCE REPORT JSON:\n" + resources.model_dump_json(indent=2)
    )
    if user_answers:
        prompt += "\n\nUSER-PROVIDED ANSWERS for unresolved resources:\n" + user_answers
    bundle = await run_agent(
        packager_agent, [types.Part.from_text(text=prompt)], SkillBundle, user_id
    )
    skill_path = _save_skill(user_id, bundle)
    log.info("Saved skill %s for user %s", bundle.slug, user_id)
    return PipelineResult(
        status="done",
        message=(
            f"Done! I turned that reel into a skill: \"{bundle.name}\".\n\n"
            f"{bundle.description}\n\n"
            f"It's in your library as '{bundle.slug}' -- your find-skills assistant "
            f"will pick it up automatically next time it applies."
        ),
        skill_path=skill_path,
    )


def _video_parts(video_path: Path) -> list[types.Part]:
    """Prefer inline video (Gemini watches it natively). Over the inline limit, fall
    back to the /watch technique: timestamped sampled frames + mono audio track."""
    video_bytes = video_path.read_bytes()
    if len(video_bytes) <= MAX_INLINE_VIDEO_BYTES:
        return [types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")]

    log.info("%s over inline limit (%d bytes); using frame sampling", video_path.name, len(video_bytes))
    parts = [types.Part.from_text(
        text="The video was too large to attach whole. Below are uniformly sampled frames "
        "(filenames carry the tMM-SS timestamp) followed by the audio track. "
        "Reconstruct the tutorial from frames + audio together."
    )]
    for frame in extract_frames(video_path):
        parts.append(types.Part.from_text(text=f"Frame at {frame.stem.split('_')[0][1:].replace('-', ':')}:"))
        parts.append(types.Part.from_bytes(data=frame.read_bytes(), mime_type="image/jpeg"))
    audio = extract_audio(video_path)
    if audio:
        parts.append(types.Part.from_bytes(data=audio.read_bytes(), mime_type="audio/mp3"))
    return parts


async def process_reel(user_id: str, video_path: Path, caption: str = "") -> PipelineResult:
    """Full pipeline for a freshly shared reel."""
    tutorial = await run_agent(
        extractor_agent,
        [types.Part.from_text(text=f"Caption of the reel: {caption or '(none)'}"), *_video_parts(video_path)],
        ExtractedTutorial,
        user_id,
    )
    log.info("Extracted tutorial '%s' (%d steps)", tutorial.title, len(tutorial.steps))

    resources = ResourceReport()
    if tutorial.required_resources:
        resources = await run_agent(
            build_resolver_agent(),
            [types.Part.from_text(
                text="Resources JSON:\n"
                + json.dumps([r.model_dump() for r in tutorial.required_resources], indent=2)
            )],
            ResourceReport,
            user_id,
        )

    missing = [r for r in resources.resources if r.status == "not_found"]
    if missing:
        _pending_file(user_id).write_text(
            json.dumps({"tutorial": tutorial.model_dump(), "resources": resources.model_dump()}),
            encoding="utf-8",
        )
        questions = "\n".join(f"- {r.name}: {r.note}" for r in missing)
        return PipelineResult(
            status="needs_input",
            message=(
                f"I watched \"{tutorial.title}\" and extracted {len(tutorial.steps)} steps, "
                f"but this reel needs something I couldn't find:\n{questions}\n\n"
                "Reply here with a link or description and I'll finish building the skill."
            ),
        )

    return await _package(user_id, tutorial, resources)


async def resume_with_answer(user_id: str, answer_text: str) -> PipelineResult | None:
    """Called when the user sends a plain-text DM. Returns None if nothing was pending."""
    pending = _pending_file(user_id)
    if not pending.exists():
        return None
    state = json.loads(pending.read_text(encoding="utf-8"))
    pending.unlink()
    return await _package(
        user_id,
        ExtractedTutorial.model_validate(state["tutorial"]),
        ResourceReport.model_validate(state["resources"]),
        user_answers=answer_text,
    )
