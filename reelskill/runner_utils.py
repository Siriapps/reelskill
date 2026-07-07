"""Run a single ADK agent once and parse its structured output."""

import asyncio
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


# Gemini intermittently returns 503 UNAVAILABLE ("high demand"); ride it out instead
# of failing the whole DM. Last attempt swaps to the fallback model.
_RETRY_DELAYS = (15, 30, 45)
_FALLBACK_MODEL = "gemini-flash-lite-latest"


async def run_agent(agent: Agent, parts: list[types.Part], schema: type[T], user_id: str) -> T:
    """One-shot invocation with 503 retries: build a runner+session, send parts,
    validate final JSON output."""
    for i, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return await _run_agent_once(agent, parts, schema, user_id)
        except Exception as exc:
            if delay is None or "503" not in str(exc):
                raise
            log.warning("Agent %s hit 503 (attempt %d); retrying in %ds", agent.name, i + 1, delay)
            await asyncio.sleep(delay)
            if delay == _RETRY_DELAYS[-1]:
                # ponytail: mutates the shared agent's model; fine for a single-user demo
                agent.model = _FALLBACK_MODEL
                log.warning("Agent %s switching to fallback model %s", agent.name, _FALLBACK_MODEL)
    raise AssertionError("unreachable")


async def _run_agent_once(agent: Agent, parts: list[types.Part], schema: type[T], user_id: str) -> T:
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
