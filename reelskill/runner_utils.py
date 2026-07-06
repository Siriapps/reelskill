"""Run a single ADK agent once and parse its structured output."""

import logging
import re
import uuid
from typing import TypeVar

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _strip_fences(text: str) -> str:
    """Remove a wrapping ```json fence if present. Only strips when the fence wraps the
    WHOLE payload -- the JSON itself may legitimately contain ``` blocks (e.g. a
    SKILL.md body with bash snippets), so an inner-block regex search would be wrong."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def run_agent(agent: Agent, parts: list[types.Part], schema: type[T], user_id: str) -> T:
    """One-shot invocation: build a runner+session, send parts, validate final JSON output."""
    runner = InMemoryRunner(agent=agent, app_name="reelskill")
    session = await runner.session_service.create_session(
        app_name="reelskill", user_id=user_id, session_id=uuid.uuid4().hex
    )
    final_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=parts),
    ):
        if event.content and event.content.parts:
            texts = [p.text for p in event.content.parts if p.text]
            if texts and event.is_final_response():
                final_text = "".join(texts)
    if not final_text:
        raise RuntimeError(f"Agent {agent.name} produced no final text response")
    return schema.model_validate_json(_strip_fences(final_text))
