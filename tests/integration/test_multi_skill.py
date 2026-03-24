"""Integration tests for multi-skill decomposition."""

from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from haiku.skills.agent import SkillToolset
from haiku.skills.prompts import build_system_prompt

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.vcr()
async def test_multi_skill_decomposition(
    allow_model_requests: None, ollama_model: OpenAIChatModel
):
    """Multi-skill: summarize then translate."""
    toolset = SkillToolset(
        skill_paths=[FIXTURES / "summarizer", FIXTURES / "translator"]
    )
    agent = Agent(
        ollama_model,
        instructions=build_system_prompt(toolset.skill_catalog),
        toolsets=[toolset],
    )
    result = await agent.run(
        "First summarize the following text, then translate the summary to French: "
        "Machine learning is a subset of artificial intelligence that enables "
        "systems to learn and improve from experience without being explicitly "
        "programmed. It focuses on developing algorithms that can access data "
        "and use it to learn for themselves.",
    )
    assert result.output
