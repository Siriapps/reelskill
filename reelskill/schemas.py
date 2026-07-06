from typing import Literal, Optional

from pydantic import BaseModel, Field


class TutorialStep(BaseModel):
    order: int = Field(description="1-based position of the step")
    action: str = Field(description="What the user must do, phrased as an imperative")
    tool: str = Field(description="App/site/model used in this step, e.g. 'Cursor', 'Midjourney', 'Notion'")
    exact_input: Optional[str] = Field(
        default=None,
        description="Verbatim prompt, command, or setting shown or spoken in the video, if any",
    )
    inferred: bool = Field(
        default=False,
        description="True if this step was NOT shown in the video but is required to get from the previous step to the next",
    )
    inference_rationale: Optional[str] = Field(
        default=None, description="Why this inferred step is necessary (only when inferred=True)"
    )


class RequiredResource(BaseModel):
    name: str = Field(description="Short name, e.g. 'Notion second-brain template'")
    kind: Literal["template", "document", "dataset", "plugin", "account", "api_key", "other"]
    description: str = Field(description="What it is and which step needs it")
    mentioned_url: Optional[str] = Field(default=None, description="URL if one was shown/spoken in the video")


class ExtractedTutorial(BaseModel):
    """Structured understanding of a short-form tutorial video."""

    title: str = Field(description="Concise title of what the tutorial achieves")
    summary: str = Field(description="2-3 sentence summary of the outcome")
    category: str = Field(description="e.g. 'AI coding', 'image generation', 'productivity setup'")
    primary_tool: str = Field(description="Main tool the tutorial is about")
    steps: list[TutorialStep]
    required_resources: list[RequiredResource] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(
        description="Situations in which an agent should apply this tutorial, e.g. 'user is setting up a new Next.js project'"
    )
    confidence_notes: str = Field(
        description="What was unclear, cut too fast, or skipped in the video", default=""
    )


class ResolvedResource(BaseModel):
    name: str
    status: Literal["found", "not_found"]
    resolved_url: Optional[str] = Field(default=None, description="Working URL when status=found")
    note: str = Field(default="", description="How it was found, or why it could not be")


class ResourceReport(BaseModel):
    resources: list[ResolvedResource] = Field(default_factory=list)


class SkillBundle(BaseModel):
    """Final packaged skill, ready to be written as SKILL.md."""

    slug: str = Field(description="kebab-case identifier, e.g. 'midjourney-consistent-characters'")
    name: str
    description: str = Field(
        description="One paragraph starting with 'Use when...' so a skill router can select it by trigger conditions"
    )
    skill_markdown: str = Field(description="Full SKILL.md body in markdown")
