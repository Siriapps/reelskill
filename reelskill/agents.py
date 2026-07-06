"""The three ADK agents that make up the ReelSkill pipeline."""

from google.adk.agents import Agent

from .config import MODEL_NAME
from .schemas import ExtractedTutorial, ResourceReport, SkillBundle

extractor_agent = Agent(
    name="reel_extractor",
    model=MODEL_NAME,
    description="Watches a short-form tutorial video and extracts every actionable step.",
    instruction="""You are given a short-form tutorial video (an Instagram Reel) and its caption.
Watch it fully -- both the visuals (screen recordings, text overlays, UI shown) and the audio.

Extract EVERY actionable step needed to reproduce the result. Short-form video is compressed
and cut fast, so it almost always skips steps. When steps are missing, INFER them: add the
step with inferred=true and explain in inference_rationale why it must exist (e.g. "the video
jumps from an empty project to a running server, so dependencies must be installed").

Capture exact prompts, commands, settings, and model names verbatim in exact_input whenever
they are shown on screen or spoken, even briefly.

List every external resource the tutorial depends on (templates, documents, plugins,
accounts, API keys) in required_resources. If a URL is shown or said, record it.

Write trigger_conditions as concrete situations where an AI agent should apply this
tutorial on the user's behalf.""",
    output_schema=ExtractedTutorial,
    output_key="tutorial",
)


def build_resolver_agent() -> Agent:
    # google_search is stateful per-agent in some ADK versions; build fresh per run.
    from google.adk.tools import google_search

    return Agent(
        name="resource_resolver",
        model=MODEL_NAME,
        description="Finds working URLs for resources a tutorial depends on.",
        instruction="""You are given a JSON list of resources a video tutorial depends on.
For each resource, use Google Search to find a working, authoritative URL (official docs,
the creator's linked template, the tool's download page).

Rules:
- If the resource had a mentioned_url, verify it looks plausible and prefer it.
- Accounts and API keys count as "found" if you can locate the signup/keys page.
- If you genuinely cannot find it (private template, paywalled file, creator-only link),
  mark it not_found and say in the note exactly what the user must provide.

Respond with ONLY a JSON object, no prose or markdown, in exactly this shape:
{"resources": [{"name": str, "status": "found"|"not_found", "resolved_url": str|null, "note": str}]}""",
        tools=[google_search],
        # No output_schema here: Gemini rejects combining the built-in google_search
        # tool with function calling (which ADK uses to enforce schemas). The raw JSON
        # is validated against ResourceReport by runner_utils instead.
    )


packager_agent = Agent(
    name="skill_packager",
    model=MODEL_NAME,
    description="Packages an extracted tutorial into an installable SKILL.md bundle.",
    instruction="""You are given an extracted tutorial (JSON) and a resource report (JSON),
possibly including answers the user gave for resources that could not be found automatically.

Produce a SkillBundle:
- slug: kebab-case, short, unique-feeling (derive from the tutorial title).
- description: MUST start with "Use when" and enumerate the trigger conditions, because a
  skill router selects skills by matching this description against the user's current task.
- skill_markdown: a complete SKILL.md with this structure:

  ---
  name: <slug>
  description: <the same description>
  ---

  # <Title>

  <summary>

  ## When to use this skill
  <bullet list of trigger conditions>

  ## Steps
  <numbered steps; include exact prompts/commands in fenced code blocks; mark inferred
  steps with "(inferred -- not shown in the original video)" and one line of rationale>

  ## Required resources
  <table: resource | where to get it (resolved URL or user-provided answer)>

  ## Source
  Extracted from an Instagram Reel the user saved. Confidence notes: <confidence_notes>

Keep the markdown tight and executable -- an agent should be able to follow it without
watching the video.""",
    output_schema=SkillBundle,
    output_key="bundle",
)
