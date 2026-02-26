"""Integration tests using VCR-recorded cassettes against Ollama."""

from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from haiku.skills.agent import SkillToolset, resolve_model
from haiku.skills.models import Skill, SkillMetadata, SkillSource
from haiku.skills.prompts import build_system_prompt

FIXTURES = Path(__file__).parent / "fixtures"


def _ollama_model() -> OpenAIChatModel:
    model = resolve_model("ollama:gpt-oss")
    assert isinstance(model, OpenAIChatModel)
    return model


@pytest.mark.vcr()
async def test_single_skill_summarize(allow_model_requests: None):
    """Single skill: summarize a paragraph."""
    toolset = SkillToolset(skill_paths=[FIXTURES])
    agent = Agent(
        _ollama_model(),
        instructions=build_system_prompt(toolset.skill_catalog),
        toolsets=[toolset],
    )
    result = await agent.run(
        "Summarize the following: "
        "Python is a high-level programming language known for its readability "
        "and versatility. It supports multiple programming paradigms including "
        "procedural, object-oriented, and functional programming. Python has a "
        "large standard library and an active community that contributes "
        "thousands of third-party packages.",
    )
    assert result.output
    assert len(result.output) > 10


@pytest.mark.vcr()
async def test_skill_with_tool(allow_model_requests: None):
    """Skill with an in-process tool: calculator."""

    def calculate(expression: str) -> str:
        """Evaluate a mathematical expression and return the result.

        Args:
            expression: A mathematical expression to evaluate, e.g. '2 + 2'.
        """
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expression):
            return f"Error: invalid characters in expression: {expression}"
        try:
            return str(eval(expression))
        except Exception as e:
            return f"Error: {e}"

    meta = SkillMetadata(
        name="calculator",
        description="Perform mathematical calculations.",
    )
    skill = Skill(
        metadata=meta,
        source=SkillSource.ENTRYPOINT,
        instructions=(
            "You are a calculator assistant. Use the calculate tool "
            "to evaluate mathematical expressions. Always use the tool "
            "rather than computing in your head."
        ),
        tools=[calculate],
    )
    toolset = SkillToolset(skills=[skill])
    agent = Agent(
        _ollama_model(),
        instructions=build_system_prompt(toolset.skill_catalog),
        toolsets=[toolset],
    )
    result = await agent.run("What is 15 * 23 + 7?")
    assert result.output
    assert "352" in result.output


@pytest.mark.vcr()
async def test_multi_skill_decomposition(allow_model_requests: None):
    """Multi-skill: summarize then translate."""
    toolset = SkillToolset(skill_paths=[FIXTURES])
    agent = Agent(
        _ollama_model(),
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
