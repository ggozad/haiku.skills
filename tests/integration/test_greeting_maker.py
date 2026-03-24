"""Integration tests for the greeting-maker skill.

Exercises all tool types across both execution modes (subagent/direct)
and both skill sources (entrypoint/filesystem), with AG-UI event and
state assertions.

Entrypoint version: lookup tool (in-process) + resource + render script + state
Filesystem version: lookup script + resource + render script (no tools, no state)
"""

from pathlib import Path

import pytest
from ag_ui.core import ActivitySnapshotEvent, BaseEvent, StateDeltaEvent
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.openai import OpenAIChatModel

from haiku.skills.agent import SkillToolset
from haiku.skills.discovery import discover_resources
from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.prompts import build_system_prompt
from haiku.skills.state import SkillRunDeps

FIXTURES = Path(__file__).parent.parent / "fixtures"

PROMPT = "Use the greeting maker skill to produce a greeting for employee 42."


# -- helpers ------------------------------------------------------------------


class GreetingMakerState(BaseModel):
    lookups: list[dict[str, str]] = []


def lookup(ctx: RunContext[SkillRunDeps], employee_id: int) -> str:
    """Look up an employee by ID.

    Args:
        employee_id: The employee ID to look up.
    """
    employees = {
        42: {"name": "Alice", "department": "Engineering"},
    }
    emp = employees.get(employee_id)
    if emp is None:
        return f"Error: Employee {employee_id} not found"
    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, GreetingMakerState):
        ctx.deps.state.lookups.append(emp)
    return f"Name: {emp['name']}, Department: {emp['department']}"


def _make_greeting_maker_skill() -> Skill:
    """Create the greeting-maker skill as an entrypoint skill with tools and state."""
    fixture_dir = FIXTURES / "greeting-maker-entrypoint"
    metadata, instructions = parse_skill_md(fixture_dir / "SKILL.md")
    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=fixture_dir,
        instructions=instructions,
        resources=discover_resources(fixture_dir),
        tools=[lookup],
        state_type=GreetingMakerState,
        state_namespace="greeting-maker",
    )


def _collect_metadata_events(result: AgentRunResult[str]) -> list[BaseEvent]:
    """Collect all AG-UI events from ToolReturnPart metadata in a run result."""
    events: list[BaseEvent] = []
    for msg in result.all_messages():
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart) and part.metadata:
                    events.extend(part.metadata)
    return events


# -- entrypoint: tools + resources + scripts + state --------------------------


@pytest.mark.vcr()
async def test_entrypoint_subagent(
    allow_model_requests: None, ollama_model: OpenAIChatModel
):
    """Entrypoint skill via subagent: exercises execute_skill with tools, resources, scripts, and state."""
    skill = _make_greeting_maker_skill()
    toolset = SkillToolset(skills=[skill])
    agent = Agent(
        ollama_model,
        instructions=build_system_prompt(toolset.skill_catalog),
        toolsets=[toolset],
    )
    result = await agent.run(PROMPT)
    assert "Alice" in result.output
    assert "Engineering" in result.output

    # AG-UI events: sub-agent tool calls produce ActivitySnapshotEvents,
    # state mutation produces StateDeltaEvent
    events = _collect_metadata_events(result)
    activity_events = [e for e in events if isinstance(e, ActivitySnapshotEvent)]
    assert any(e.activity_type == "skill_tool_call" for e in activity_events)
    assert any(e.activity_type == "skill_tool_result" for e in activity_events)
    assert any(isinstance(e, StateDeltaEvent) for e in events)

    # State: lookup tool should have recorded the employee
    ns = toolset.get_namespace("greeting-maker")
    assert isinstance(ns, GreetingMakerState)
    assert {"name": "Alice", "department": "Engineering"} in ns.lookups


@pytest.mark.vcr()
async def test_entrypoint_direct(
    allow_model_requests: None, ollama_model: OpenAIChatModel
):
    """Entrypoint skill via direct mode: exercises query_skill, execute_skill_tool, read_skill_resource, run_skill_script."""
    skill = _make_greeting_maker_skill()
    toolset = SkillToolset(skills=[skill], use_subagents=False)
    agent = Agent(
        ollama_model,
        instructions=build_system_prompt(toolset.skill_catalog, use_subagents=False),
        toolsets=[toolset],
    )
    result = await agent.run(PROMPT)
    assert "Alice" in result.output
    assert "Engineering" in result.output

    # AG-UI events: execute_skill_tool with state mutation produces StateDeltaEvent
    events = _collect_metadata_events(result)
    assert any(isinstance(e, StateDeltaEvent) for e in events)

    # State: lookup tool should have recorded the employee
    ns = toolset.get_namespace("greeting-maker")
    assert isinstance(ns, GreetingMakerState)
    assert {"name": "Alice", "department": "Engineering"} in ns.lookups


# -- filesystem: resources + scripts (no tools, no state) ---------------------


@pytest.mark.vcr()
async def test_filesystem_subagent(
    allow_model_requests: None, ollama_model: OpenAIChatModel
):
    """Filesystem skill via subagent: exercises execute_skill with resources and scripts."""
    toolset = SkillToolset(skill_paths=[FIXTURES / "greeting-maker-filesystem"])
    agent = Agent(
        ollama_model,
        instructions=build_system_prompt(toolset.skill_catalog),
        toolsets=[toolset],
    )
    result = await agent.run(PROMPT)
    assert "Alice" in result.output
    assert "Engineering" in result.output

    # AG-UI events: sub-agent tool calls (read_resource, run_script) produce
    # ActivitySnapshotEvents
    events = _collect_metadata_events(result)
    activity_events = [e for e in events if isinstance(e, ActivitySnapshotEvent)]
    assert any(e.activity_type == "skill_tool_call" for e in activity_events)
    assert any(e.activity_type == "skill_tool_result" for e in activity_events)


@pytest.mark.vcr()
async def test_filesystem_direct(
    allow_model_requests: None, ollama_model: OpenAIChatModel
):
    """Filesystem skill via direct mode: exercises query_skill, read_skill_resource, run_skill_script."""
    toolset = SkillToolset(
        skill_paths=[FIXTURES / "greeting-maker-filesystem"], use_subagents=False
    )
    agent = Agent(
        ollama_model,
        instructions=build_system_prompt(toolset.skill_catalog, use_subagents=False),
        toolsets=[toolset],
    )
    result = await agent.run(PROMPT)
    assert "Alice" in result.output
    assert "Engineering" in result.output
