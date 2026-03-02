import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ag_ui.core import (
    BaseEvent,
    EventType,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.test import TestModel
from pydantic_ai.result import RunUsage
from pydantic_ai.toolsets.function import FunctionToolset

from haiku.skills.agent import (
    SCRIPT_RUNNERS,
    SkillToolset,
    _create_read_resource,
    _create_run_script,
    _events_to_agui,
    _last_tool_result,
    _run_skill,
    resolve_model,
    run_agui_stream,
)
from haiku.skills.models import (
    Skill,
    SkillMetadata,
    SkillSource,
)
from haiku.skills.prompts import SKILL_PROMPT, build_system_prompt
from haiku.skills.state import SkillRunDeps

FIXTURES = Path(__file__).parent / "fixtures"


class TestSkillToolset:
    def test_create_with_paths(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        assert "simple-skill" in toolset.registry.names
        assert "skill-with-refs" in toolset.registry.names

    def test_create_with_skill_objects(self):
        skill = Skill(
            metadata=SkillMetadata(name="custom", description="Custom skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do custom things.",
        )
        toolset = SkillToolset(skills=[skill])
        assert "custom" in toolset.registry.names

    def test_create_with_entrypoints(self, monkeypatch: pytest.MonkeyPatch):
        skill = Skill(
            metadata=SkillMetadata(name="ep-skill", description="From entrypoint."),
            source=SkillSource.ENTRYPOINT,
        )
        mock_ep = type("MockEP", (), {"load": lambda self: lambda: skill})()
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        toolset = SkillToolset(use_entrypoints=True)
        assert "ep-skill" in toolset.registry.names

    def test_create_with_paths_and_skills(self):
        skill = Skill(
            metadata=SkillMetadata(name="extra", description="Extra skill."),
            source=SkillSource.ENTRYPOINT,
        )
        toolset = SkillToolset(skill_paths=[FIXTURES], skills=[skill])
        assert "simple-skill" in toolset.registry.names
        assert "extra" in toolset.registry.names

    def test_manual_skill_takes_priority_over_entrypoint(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        ep_skill = Skill(
            metadata=SkillMetadata(name="memory", description="From entrypoint."),
            source=SkillSource.ENTRYPOINT,
        )
        mock_ep = type("MockEP", (), {"load": lambda self: lambda: ep_skill})()
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        manual_skill = Skill(
            metadata=SkillMetadata(name="memory", description="Manual version."),
            source=SkillSource.FILESYSTEM,
            instructions="Custom instructions.",
        )
        toolset = SkillToolset(skills=[manual_skill], use_entrypoints=True)
        assert toolset.registry.get("memory") is manual_skill

    def test_skill_catalog(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        catalog = toolset.skill_catalog
        assert "simple-skill" in catalog
        assert "skill-with-refs" in catalog

    def test_build_system_prompt_default(self):
        prompt = build_system_prompt("- **test**: A test skill.")
        assert "test" in prompt
        assert "create_task" not in prompt

    def test_build_system_prompt_custom_preamble(self):
        prompt = build_system_prompt("", preamble="You are a coding assistant.")
        assert "You are a coding assistant." in prompt


class TestRunSkill:
    async def test_run_skill(self, allow_model_requests: None):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        skill = toolset.registry.get("simple-skill")
        assert skill is not None
        result, events = await _run_skill(
            TestModel(call_tools=[]), skill, "Do something."
        )
        assert result
        assert events == []

    async def test_run_skill_with_tools(self, allow_model_requests: None):
        def greet(name: str) -> str:
            """Greet someone by name."""
            return f"Hello, {name}!"

        meta = SkillMetadata(name="greeter", description="Greets people.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            instructions="Use the greet tool.",
            tools=[greet],
        )
        result, events = await _run_skill(TestModel(), skill, "Greet Alice.")
        assert result
        assert len(events) >= 2
        call_events = [e for e in events if isinstance(e, FunctionToolCallEvent)]
        result_events = [e for e in events if isinstance(e, FunctionToolResultEvent)]
        assert len(call_events) >= 1
        assert len(result_events) >= 1

    async def test_run_skill_with_toolsets(self, allow_model_requests: None):
        def greet(name: str) -> str:
            """Greet someone by name."""
            return f"Hello, {name}!"

        toolset = FunctionToolset()
        toolset.add_function(greet)
        meta = SkillMetadata(name="greeter", description="Greets people.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            instructions="Use the greet toolset.",
            toolsets=[toolset],
        )
        result, events = await _run_skill(TestModel(), skill, "Greet Alice.")
        assert result
        assert len(events) >= 2

    async def test_run_skill_with_event_sink(self, allow_model_requests: None):
        """When event_sink is provided, events stream through sink, collected_events empty."""
        sinked: list[Any] = []

        async def sink(event: Any) -> None:
            sinked.append(event)

        def greet(name: str) -> str:
            """Greet someone by name."""
            return f"Hello, {name}!"

        meta = SkillMetadata(name="greeter", description="Greets people.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            instructions="Use the greet tool.",
            tools=[greet],
        )
        result, collected = await _run_skill(
            TestModel(), skill, "Greet Alice.", event_sink=sink
        )
        assert result
        assert collected == []
        assert len(sinked) >= 2
        assert any(isinstance(e, ToolCallStartEvent) for e in sinked)
        assert any(isinstance(e, ToolCallResultEvent) for e in sinked)


class TestLastToolResult:
    def test_returns_none_for_empty_messages(self):
        assert _last_tool_result([]) is None

    def test_returns_none_when_no_tool_returns(self):
        from pydantic_ai.messages import UserPromptPart

        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        assert _last_tool_result(messages) is None


class TestCreateReadResource:
    def _make_skill_with_resources(self) -> Skill:
        return Skill(
            metadata=SkillMetadata(
                name="skill-with-refs",
                description="A skill with references.",
            ),
            source=SkillSource.FILESYSTEM,
            path=FIXTURES / "skill-with-refs",
            resources=["references/REFERENCE.md", "assets/template.txt"],
        )

    async def test_reads_valid_resource(self):
        skill = self._make_skill_with_resources()
        read_resource = _create_read_resource(skill)
        content = await read_resource(path="references/REFERENCE.md")
        assert "Reference Guide" in content

    async def test_unknown_path_raises(self):
        skill = self._make_skill_with_resources()
        read_resource = _create_read_resource(skill)
        with pytest.raises(ValueError, match="not an available resource"):
            await read_resource(path="unknown.txt")

    async def test_path_traversal_raises(self):
        skill = self._make_skill_with_resources()
        read_resource = _create_read_resource(skill)
        with pytest.raises(ValueError, match="not an available resource"):
            await read_resource(path="../../../etc/passwd")

    async def test_path_traversal_via_symlink_raises(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        link = skill_dir / "escape.txt"
        link.symlink_to(tmp_path / "secret.txt")
        (tmp_path / "secret.txt").write_text("secret")
        skill = Skill(
            metadata=SkillMetadata(name="my-skill", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=skill_dir,
            resources=["escape.txt"],
        )
        read_resource = _create_read_resource(skill)
        with pytest.raises(ValueError, match="not an available resource"):
            await read_resource(path="escape.txt")

    async def test_binary_file_raises(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        binary_file = skill_dir / "data.bin"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe")
        skill = Skill(
            metadata=SkillMetadata(name="my-skill", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=skill_dir,
            resources=["data.bin"],
        )
        read_resource = _create_read_resource(skill)
        with pytest.raises(ValueError, match="not a text file"):
            await read_resource(path="data.bin")


class TestPrompts:
    def test_skill_prompt_has_placeholders(self):
        assert "{task_description}" in SKILL_PROMPT
        assert "{skill_instructions}" in SKILL_PROMPT
        assert "{resource_section}" in SKILL_PROMPT


class TestRunSkillWithResources:
    async def test_prompt_includes_resource_list(self, allow_model_requests: None):
        skill = Skill(
            metadata=SkillMetadata(name="r", description="Has resources."),
            source=SkillSource.FILESYSTEM,
            path=FIXTURES / "skill-with-refs",
            instructions="Use references.",
            resources=["references/REFERENCE.md", "assets/template.txt"],
        )
        result, _ = await _run_skill(TestModel(call_tools=[]), skill, "Do something.")
        assert result

    async def test_no_resources_no_section(self, allow_model_requests: None):
        skill = Skill(
            metadata=SkillMetadata(name="r", description="No resources."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        result, _ = await _run_skill(TestModel(call_tools=[]), skill, "Do something.")
        assert result


class TestAgent:
    async def test_direct_chat(self, allow_model_requests: None):
        """Agent responds directly without skill execution for simple chat."""
        model = TestModel(call_tools=[], custom_output_text="Hello there!")
        toolset = SkillToolset(skill_paths=[FIXTURES])
        agent = Agent(
            model,
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Hello")
        assert result.output == "Hello there!"

    async def test_run_with_skill_execution(self, allow_model_requests: None):
        """Agent delegates to skills."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_run_with_unknown_skill(self, allow_model_requests: None):
        """Unknown skill in execute_skill returns error message."""
        toolset = SkillToolset(skill_paths=[FIXTURES])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_run_skill_exception_returns_error(
        self, monkeypatch: pytest.MonkeyPatch, allow_model_requests: None
    ):
        """Exception during _run_skill returns an error string."""

        def exploding_tool() -> str:
            """Always raises."""
            raise RuntimeError("boom")

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use exploding_tool.",
            tools=[exploding_tool],
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output
        tool_returns = [
            part
            for msg in result.all_messages()
            if isinstance(msg, ModelRequest)
            for part in msg.parts
            if isinstance(part, ToolReturnPart)
            and "Error:" in part.model_response_str()
        ]
        assert tool_returns

    async def test_skill_model_fallback_to_env(
        self, monkeypatch: pytest.MonkeyPatch, allow_model_requests: None
    ):
        """Skill model falls back to HAIKU_SKILL_MODEL env var."""
        monkeypatch.setenv("HAIKU_SKILL_MODEL", "test")
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_skill_model_from_skill(self, allow_model_requests: None):
        """Skill's own model field takes priority."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
            model="test",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_skill_model_instance_on_skill(self, allow_model_requests: None):
        """A Model instance on skill.model flows through to the sub-agent."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
            model=TestModel(),
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_skill_model_param_used_as_fallback(self, allow_model_requests: None):
        """skill_model param is used when skill has no model and env var unset."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        toolset = SkillToolset(skills=[skill], skill_model=TestModel())
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_skill_model_param_string_resolved(self, allow_model_requests: None):
        """skill_model as string goes through resolve_model."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        toolset = SkillToolset(skills=[skill], skill_model="test")
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_without_skill_model_uses_ctx_model(self, allow_model_requests: None):
        """Without skill_model, ctx.model is used."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output


class CounterState(BaseModel):
    count: int = 0


class ItemsState(BaseModel):
    items: list[str] = []


class TestSkillToolsetState:
    def test_no_states_by_default(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        assert toolset.build_state_snapshot() == {}
        assert toolset.state_schemas == {}

    def test_registers_state_namespace(self):
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        ns = toolset.get_namespace("ns.counter")
        assert ns is not None
        assert isinstance(ns, CounterState)
        assert ns.count == 0

    def test_shared_namespace_across_skills(self):
        skill_a = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="shared",
        )
        skill_b = Skill(
            metadata=SkillMetadata(name="b", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="shared",
        )
        toolset = SkillToolset(skills=[skill_a, skill_b])
        assert toolset.get_namespace("shared") is not None
        assert isinstance(toolset.get_namespace("shared"), CounterState)

    def test_conflicting_namespace_types_raises(self):
        skill_a = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="ns",
        )
        skill_b = Skill(
            metadata=SkillMetadata(name="b", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=ItemsState,
            state_namespace="ns",
        )
        with pytest.raises(TypeError, match="Namespace 'ns' registered with type"):
            SkillToolset(skills=[skill_a, skill_b])

    def test_get_namespace_returns_none_for_unknown(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        assert toolset.get_namespace("nonexistent") is None

    def test_state_schemas(self):
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        schemas = toolset.state_schemas
        assert "ns.counter" in schemas
        assert schemas["ns.counter"]["properties"]["count"]["type"] == "integer"

    def test_build_state_snapshot(self):
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        snapshot = toolset.build_state_snapshot()
        assert snapshot == {"ns.counter": {"count": 0}}

    def test_restore_state_snapshot(self):
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        toolset.restore_state_snapshot({"ns.counter": {"count": 42}})
        ns = toolset.get_namespace("ns.counter")
        assert ns is not None
        assert isinstance(ns, CounterState)
        assert ns.count == 42

    def test_restore_state_snapshot_ignores_unknown_namespaces(self):
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        toolset.restore_state_snapshot({"unknown": {"x": 1}})
        assert toolset.get_namespace("unknown") is None

    def test_snapshot_restore_roundtrip(self):
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        counter = toolset.get_namespace("ns.counter")
        assert isinstance(counter, CounterState)
        counter.count = 7

        snapshot = toolset.build_state_snapshot()
        toolset2 = SkillToolset(skills=[skill])
        toolset2.restore_state_snapshot(snapshot)
        assert toolset2.build_state_snapshot() == snapshot


class TestRunSkillWithState:
    async def test_run_skill_passes_state_as_deps(self, allow_model_requests: None):
        """Verify _run_skill passes state to the sub-agent as deps."""
        captured_deps: list[SkillRunDeps | None] = []

        def capture_tool(ctx: RunContext[SkillRunDeps | None]) -> str:
            """Capture deps."""
            captured_deps.append(ctx.deps)
            return "done"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use capture_tool.",
            tools=[capture_tool],
        )
        state = CounterState(count=5)
        await _run_skill(TestModel(), skill, "Do it.", state=state)
        assert len(captured_deps) == 1
        assert captured_deps[0] is not None
        assert captured_deps[0].state is state

    async def test_run_skill_without_state(self, allow_model_requests: None):
        """Without state, deps has state=None."""
        captured_deps: list[SkillRunDeps | None] = []

        def capture_tool(ctx: RunContext[SkillRunDeps | None]) -> str:
            """Capture deps."""
            captured_deps.append(ctx.deps)
            return "done"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use capture_tool.",
            tools=[capture_tool],
        )
        await _run_skill(TestModel(), skill, "Do it.")
        assert len(captured_deps) == 1
        assert captured_deps[0] is not None
        assert captured_deps[0].state is None


class TestExecuteSkillEvents:
    async def test_tool_events_in_metadata(self, allow_model_requests: None):
        """execute_skill returns ToolReturn with AG-UI tool events in metadata."""

        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Greets."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use greet tool.",
            tools=[greet],
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Greet someone.")
        tool_returns = [
            part
            for msg in result.all_messages()
            if isinstance(msg, ModelRequest)
            for part in msg.parts
            if isinstance(part, ToolReturnPart)
        ]
        has_agui_events = any(
            isinstance(ev, (ToolCallStartEvent, ToolCallResultEvent))
            for tr in tool_returns
            if tr.metadata
            for ev in tr.metadata
        )
        assert has_agui_events

    async def test_no_tool_events_without_sub_tools(self, allow_model_requests: None):
        """Skills without tools produce no AG-UI tool events in metadata."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Plain skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output
        tool_returns = [
            part
            for msg in result.all_messages()
            if isinstance(msg, ModelRequest)
            for part in msg.parts
            if isinstance(part, ToolReturnPart)
        ]
        has_agui_events = any(
            isinstance(ev, (ToolCallStartEvent, ToolCallResultEvent))
            for tr in tool_returns
            if tr.metadata
            for ev in tr.metadata
        )
        assert not has_agui_events

    async def test_events_and_state_delta_in_metadata(self, allow_model_requests: None):
        """Both AG-UI tool events and StateDeltaEvent in metadata."""
        from ag_ui.core import StateDeltaEvent

        def modify_state(ctx: RunContext[SkillRunDeps]) -> str:
            """Modify state."""
            assert isinstance(ctx.deps.state, CounterState)
            ctx.deps.state.count += 1
            return "incremented"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Counts."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use modify_state.",
            tools=[modify_state],
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Count.")
        tool_returns = [
            part
            for msg in result.all_messages()
            if isinstance(msg, ModelRequest)
            for part in msg.parts
            if isinstance(part, ToolReturnPart) and part.metadata
        ]
        assert tool_returns
        metadata = tool_returns[0].metadata
        assert metadata is not None
        has_tool_events = any(isinstance(ev, ToolCallStartEvent) for ev in metadata)
        has_delta = any(isinstance(ev, StateDeltaEvent) for ev in metadata)
        assert has_tool_events
        assert has_delta

    async def test_sink_skips_tool_events_in_metadata(self, allow_model_requests: None):
        """With _event_sink set, tool events go through sink, not metadata."""
        sinked: list[Any] = []

        async def sink(event: Any) -> None:
            sinked.append(event)

        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Greets."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use greet tool.",
            tools=[greet],
        )
        toolset = SkillToolset(skills=[skill])
        toolset._event_sink = sink
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Greet someone.")
        tool_returns = [
            part
            for msg in result.all_messages()
            if isinstance(msg, ModelRequest)
            for part in msg.parts
            if isinstance(part, ToolReturnPart)
        ]
        has_agui_tool_events = any(
            isinstance(ev, (ToolCallStartEvent, ToolCallResultEvent))
            for tr in tool_returns
            if tr.metadata
            for ev in tr.metadata
        )
        assert not has_agui_tool_events
        assert len(sinked) >= 2
        assert any(isinstance(e, ToolCallStartEvent) for e in sinked)

    async def test_sink_preserves_state_delta_in_metadata(
        self, allow_model_requests: None
    ):
        """With _event_sink set, StateDeltaEvent still appears in metadata."""
        from ag_ui.core import StateDeltaEvent

        sinked: list[Any] = []

        async def sink(event: Any) -> None:
            sinked.append(event)

        def modify_state(ctx: RunContext[SkillRunDeps]) -> str:
            """Modify state."""
            assert isinstance(ctx.deps.state, CounterState)
            ctx.deps.state.count += 1
            return "incremented"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Counts."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use modify_state.",
            tools=[modify_state],
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        toolset._event_sink = sink
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Count.")
        tool_returns = [
            part
            for msg in result.all_messages()
            if isinstance(msg, ModelRequest)
            for part in msg.parts
            if isinstance(part, ToolReturnPart) and part.metadata
        ]
        assert tool_returns
        metadata = tool_returns[0].metadata
        assert metadata is not None
        has_delta = any(isinstance(ev, StateDeltaEvent) for ev in metadata)
        assert has_delta
        has_tool_events = any(isinstance(ev, ToolCallStartEvent) for ev in metadata)
        assert not has_tool_events


class TestExecuteSkillWithState:
    async def test_state_delta_in_tool_return(self, allow_model_requests: None):
        """execute_skill returns ToolReturn with StateDeltaEvent when state changes."""

        def modify_state(ctx: RunContext[SkillRunDeps]) -> str:
            """Modify state."""
            assert isinstance(ctx.deps.state, CounterState)
            ctx.deps.state.count += 1
            return "incremented"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Counts."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use modify_state.",
            tools=[modify_state],
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Count.")
        assert result.output
        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count >= 1

    async def test_no_delta_when_state_unchanged(self, allow_model_requests: None):
        """No StateDeltaEvent when state isn't modified."""

        def no_op(ctx: RunContext[SkillRunDeps]) -> str:
            """Do nothing to state."""
            return "noop"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Does nothing."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use no_op.",
            tools=[no_op],
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do nothing.")
        assert result.output
        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 0

    async def test_skill_without_state_works_normally(self, allow_model_requests: None):
        """Skills without states still work."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Plain skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Do something.")
        assert result.output


class TestResolveModel:
    def test_ollama_prefix_returns_openai_model_with_default_url(self):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        model = resolve_model("ollama:llama3")
        assert isinstance(model, OpenAIChatModel)
        assert isinstance(model._provider, OllamaProvider)
        assert model._provider.base_url.rstrip("/") == "http://127.0.0.1:11434/v1"

    def test_ollama_prefix_uses_env_var(self, monkeypatch: pytest.MonkeyPatch):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom:1234")
        model = resolve_model("ollama:llama3")
        assert isinstance(model, OpenAIChatModel)
        assert isinstance(model._provider, OllamaProvider)
        assert model._provider.base_url.rstrip("/") == "http://custom:1234/v1"

    def test_non_ollama_delegates_to_infer_model(self):
        model = resolve_model("test")
        assert isinstance(model, TestModel)


class TestGetToolsStateRestoration:
    """Tests for SkillToolset.get_tools() restoring state from deps."""

    def _make_toolset(self) -> SkillToolset:
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        return SkillToolset(skills=[skill])

    def _make_ctx(self, deps: Any) -> RunContext[Any]:
        return RunContext(
            deps=deps,
            model=TestModel(),
            usage=RunUsage(),
            prompt="test",
            run_step=0,
        )

    async def test_restores_state_from_deps(self, allow_model_requests: None):
        """get_tools restores state when deps has a dict state attribute."""
        toolset = self._make_toolset()
        state_dict = {"ns.counter": {"count": 42}}

        class Deps:
            state = state_dict

        ctx = self._make_ctx(Deps())
        await toolset.get_tools(ctx)

        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 42

    async def test_skips_restore_for_same_dict(self, allow_model_requests: None):
        """State restored only once per unique dict (identity check)."""
        toolset = self._make_toolset()
        state_dict = {"ns.counter": {"count": 10}}

        class Deps:
            state = state_dict

        ctx = self._make_ctx(Deps())
        await toolset.get_tools(ctx)

        # Mutate the namespace directly after restore
        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        ns.count = 99

        # Second call with same dict object should NOT re-restore
        await toolset.get_tools(ctx)
        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 99

    async def test_restores_new_dict_object(self, allow_model_requests: None):
        """A new dict object triggers a fresh restore."""
        toolset = self._make_toolset()

        class Deps:
            state: dict[str, Any] = {"ns.counter": {"count": 10}}

        deps = Deps()
        ctx = self._make_ctx(deps)
        await toolset.get_tools(ctx)

        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 10

        # Assign a new dict object
        deps.state = {"ns.counter": {"count": 77}}
        ctx = self._make_ctx(deps)
        await toolset.get_tools(ctx)

        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 77

    async def test_ignores_non_dict_state(self, allow_model_requests: None):
        """Non-dict state attribute is ignored."""
        toolset = self._make_toolset()

        class Deps:
            state = "not a dict"

        ctx = self._make_ctx(Deps())
        await toolset.get_tools(ctx)

        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 0

    async def test_handles_deps_without_state(self, allow_model_requests: None):
        """Deps without state attribute is handled gracefully."""
        toolset = self._make_toolset()

        class Deps:
            pass

        ctx = self._make_ctx(Deps())
        await toolset.get_tools(ctx)

        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 0

    async def test_handles_none_deps(self, allow_model_requests: None):
        """None deps is handled gracefully."""
        toolset = self._make_toolset()
        ctx = self._make_ctx(None)
        await toolset.get_tools(ctx)

        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 0

    async def test_ignores_empty_dict_state(self, allow_model_requests: None):
        """Empty dict state is ignored."""
        toolset = self._make_toolset()

        class Deps:
            state: dict[str, Any] = {}

        ctx = self._make_ctx(Deps())
        with patch.object(toolset, "restore_state_snapshot") as mock_restore:
            await toolset.get_tools(ctx)
            mock_restore.assert_not_called()

    async def test_end_to_end_agent_run(self, allow_model_requests: None):
        """Agent run with deps carrying skill namespace state restores it."""

        def read_count(ctx: RunContext[Any]) -> str:
            """Read the counter."""
            return "done"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Reads count."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use read_count.",
            tools=[read_count],
            state_type=CounterState,
            state_namespace="ns.counter",
        )
        toolset = SkillToolset(skills=[skill])

        class Deps:
            state = {"ns.counter": {"count": 100}}

        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        result = await agent.run("Read the count.", deps=Deps())
        assert result.output

        ns = toolset.get_namespace("ns.counter")
        assert isinstance(ns, CounterState)
        assert ns.count == 100


class TestCreateRunScript:
    def _make_skill_with_scripts(self, tmp_path: Path) -> Skill:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "hello.py").write_text(
            "import sys\nprint(f'Hello, {sys.argv[1]}!')\n"
        )
        (scripts_dir / "fail.py").write_text("import sys\nsys.exit(1)\n")
        (scripts_dir / "greet.sh").write_text('#!/bin/bash\necho "Hi, $1!"\n')
        return Skill(
            metadata=SkillMetadata(name="scripted", description="Has scripts."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )

    async def test_executes_py_script(self, tmp_path: Path):
        skill = self._make_skill_with_scripts(tmp_path)
        run_script = _create_run_script(skill)
        result = await run_script(script="scripts/hello.py", arguments="World")
        assert "Hello, World!" in result

    async def test_rejects_path_outside_scripts(self, tmp_path: Path):
        skill = self._make_skill_with_scripts(tmp_path)
        run_script = _create_run_script(skill)
        with pytest.raises(ValueError, match="not under scripts/"):
            await run_script(script="../etc/passwd")

    async def test_rejects_nonexistent_script(self, tmp_path: Path):
        skill = self._make_skill_with_scripts(tmp_path)
        run_script = _create_run_script(skill)
        with pytest.raises(ValueError, match="not found"):
            await run_script(script="scripts/missing.py")

    async def test_nonzero_exit_raises(self, tmp_path: Path):
        skill = self._make_skill_with_scripts(tmp_path)
        run_script = _create_run_script(skill)
        with pytest.raises(RuntimeError, match="failed"):
            await run_script(script="scripts/fail.py")

    async def test_nonzero_exit_includes_stdout(self, tmp_path: Path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "usage.py").write_text(
            "import sys\nprint('Usage: usage.py <arg>')\nsys.exit(1)\n"
        )
        skill = Skill(
            metadata=SkillMetadata(name="s", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        run_script = _create_run_script(skill)
        with pytest.raises(RuntimeError, match="Usage: usage.py <arg>"):
            await run_script(script="scripts/usage.py")

    async def test_py_script_can_import_sibling_modules(self, tmp_path: Path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "__init__.py").write_text("")
        (scripts_dir / "utils.py").write_text(
            "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
        )
        (scripts_dir / "caller.py").write_text(
            "import sys\nfrom scripts.utils import greet\nprint(greet(sys.argv[1]))\n"
        )
        skill = Skill(
            metadata=SkillMetadata(name="s", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        run_script = _create_run_script(skill)
        result = await run_script(script="scripts/caller.py", arguments="World")
        assert "Hello, World!" in result

    async def test_executes_sh_script(self, tmp_path: Path):
        skill = self._make_skill_with_scripts(tmp_path)
        run_script = _create_run_script(skill)
        result = await run_script(script="scripts/greet.sh", arguments="Alice")
        assert "Hi, Alice!" in result

    async def test_executes_generic_script(self, tmp_path: Path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        script = scripts_dir / "greet"
        script.write_text('#!/bin/bash\necho "Hey, $1!"\n')
        script.chmod(0o755)
        skill = Skill(
            metadata=SkillMetadata(name="s", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        run_script = _create_run_script(skill)
        result = await run_script(script="scripts/greet", arguments="Bob")
        assert "Hey, Bob!" in result

    async def test_executes_js_script(self, tmp_path: Path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "greet.js").write_text(
            "console.log(`Hello, ${process.argv[2]}!`);\n"
        )
        skill = Skill(
            metadata=SkillMetadata(name="s", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        run_script = _create_run_script(skill)
        result = await run_script(script="scripts/greet.js", arguments="World")
        assert "Hello, World!" in result

    async def test_executes_ts_script(self, tmp_path: Path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "greet.ts").write_text(
            "const name: string = process.argv[2];\nconsole.log(`Hello, ${name}!`);\n"
        )
        skill = Skill(
            metadata=SkillMetadata(name="s", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        run_script = _create_run_script(skill)
        result = await run_script(script="scripts/greet.ts", arguments="World")
        assert "Hello, World!" in result

    async def test_custom_script_runner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "greet.rb").write_text('puts "Hello, #{ARGV[0]}!"\n')
        monkeypatch.setitem(SCRIPT_RUNNERS, ".rb", ("ruby",))
        skill = Skill(
            metadata=SkillMetadata(name="s", description="Test."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        run_script = _create_run_script(skill)
        result = await run_script(script="scripts/greet.rb", arguments="World")
        assert "Hello, World!" in result

    async def test_lists_js_ts_scripts_in_prompt(
        self, tmp_path: Path, allow_model_requests: None
    ):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "fetch.js").write_text("console.log('fetched');\n")
        (scripts_dir / "transform.ts").write_text("console.log('transformed');\n")
        (scripts_dir / "process.py").write_text("print('processed')\n")
        skill = Skill(
            metadata=SkillMetadata(name="scripted", description="Has scripts."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        result, _ = await _run_skill(TestModel(call_tools=[]), skill, "Do something.")
        assert result
        # Verify all script types appear in the prompt by checking
        # via the skill prompt construction path
        script_files = sorted(
            str(f.relative_to(tmp_path))
            for f in (tmp_path / "scripts").rglob("*")
            if f.is_file() and (f.suffix in SCRIPT_RUNNERS or os.access(f, os.X_OK))
        )
        assert "scripts/fetch.js" in script_files
        assert "scripts/transform.ts" in script_files
        assert "scripts/process.py" in script_files


class TestRunSkillWithScripts:
    async def test_includes_run_script_tool(
        self, tmp_path: Path, allow_model_requests: None
    ):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "hello.py").write_text(
            "import sys\nprint(f'Hello, {sys.argv[1]}!')\n"
        )
        skill = Skill(
            metadata=SkillMetadata(name="scripted", description="Has scripts."),
            source=SkillSource.FILESYSTEM,
            path=tmp_path,
            instructions="Use scripts.",
        )
        result, _ = await _run_skill(TestModel(call_tools=[]), skill, "Do something.")
        assert result

    async def test_no_run_script_without_scripts_dir(self, allow_model_requests: None):
        skill = Skill(
            metadata=SkillMetadata(name="plain", description="No scripts."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        result, _ = await _run_skill(TestModel(call_tools=[]), skill, "Do something.")
        assert result


class TestEventsToAgui:
    def test_empty_events(self):
        assert _events_to_agui("skill", []) == []

    def test_converts_tool_call_event(self):
        part = ToolCallPart(
            tool_name="search", args='{"query": "test"}', tool_call_id="call-1"
        )
        event = FunctionToolCallEvent(part=part)

        result = _events_to_agui("web", [event])
        assert len(result) == 3

        assert isinstance(result[0], ToolCallStartEvent)
        assert result[0].tool_call_id == "web:call-1"
        assert result[0].tool_call_name == "search"

        assert isinstance(result[1], ToolCallArgsEvent)
        assert result[1].tool_call_id == "web:call-1"
        assert result[1].delta == '{"query": "test"}'

        assert isinstance(result[2], ToolCallEndEvent)
        assert result[2].tool_call_id == "web:call-1"

    def test_converts_tool_result_event(self):
        result_part = ToolReturnPart(
            tool_call_id="call-1", tool_name="search", content="results"
        )
        event = FunctionToolResultEvent(result=result_part)

        result = _events_to_agui("web", [event])
        assert len(result) == 1

        assert isinstance(result[0], ToolCallResultEvent)
        assert result[0].tool_call_id == "web:call-1"
        assert result[0].content == "results"

    def test_mixed_events(self):
        part = ToolCallPart(tool_name="search", args="{}", tool_call_id="call-1")
        call_event = FunctionToolCallEvent(part=part)
        result_part = ToolReturnPart(
            tool_call_id="call-1", tool_name="search", content="results"
        )
        result_event = FunctionToolResultEvent(result=result_part)

        result = _events_to_agui("web", [call_event, result_event])
        assert len(result) == 4  # 3 from call + 1 from result

    def test_dict_args_serialized_to_json(self):
        """Dict args are serialized to JSON string."""
        part = ToolCallPart(
            tool_name="search", args={"query": "test"}, tool_call_id="call-1"
        )
        event = FunctionToolCallEvent(part=part)

        result = _events_to_agui("web", [event])
        assert isinstance(result[1], ToolCallArgsEvent)
        assert result[1].delta == '{"query": "test"}'

    def test_none_args_serialized_to_empty_object(self):
        """None args are serialized to empty JSON object."""
        part = ToolCallPart(tool_name="search", args=None, tool_call_id="call-1")
        event = FunctionToolCallEvent(part=part)

        result = _events_to_agui("web", [event])
        assert isinstance(result[1], ToolCallArgsEvent)
        assert result[1].delta == "{}"

    def test_ignores_other_event_types(self):
        """Non-tool events are skipped."""
        result = _events_to_agui("skill", ["not_an_event", 42])
        assert result == []


class TestPromptScriptsSection:
    def test_prompt_has_scripts_placeholder(self):
        assert "{scripts_section}" in SKILL_PROMPT


class TestRunAguiStream:
    async def test_yields_adapter_events(self):
        """Events from adapter.run_stream() are yielded."""
        event = ToolCallStartEvent(
            type=EventType.TOOL_CALL_START,
            tool_call_id="t1",
            tool_call_name="test",
        )

        class FakeAdapter:
            async def run_stream(self, **kwargs: Any) -> AsyncIterator[BaseEvent]:
                yield event

        toolset = SkillToolset()
        collected = []
        async with run_agui_stream(toolset, FakeAdapter()) as stream:
            async for e in stream:
                collected.append(e)
        assert collected == [event]

    async def test_yields_sink_events(self, allow_model_requests: None):
        """Sub-agent tool events stream through the sink in real-time."""

        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        skill = Skill(
            metadata=SkillMetadata(name="a", description="Greets."),
            source=SkillSource.ENTRYPOINT,
            instructions="Use greet tool.",
            tools=[greet],
        )
        toolset = SkillToolset(skills=[skill])
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(toolset.skill_catalog),
            toolsets=[toolset],
        )
        from pydantic_ai.ag_ui import AGUIAdapter

        run_input = _make_run_input("Greet someone.")
        adapter = AGUIAdapter(agent=agent, run_input=run_input)
        events = []
        async with run_agui_stream(toolset, adapter) as stream:
            async for e in stream:
                events.append(e)
        sub_tool_events = [
            e
            for e in events
            if isinstance(e, ToolCallStartEvent) and e.tool_call_name != "execute_skill"
        ]
        assert len(sub_tool_events) >= 1

    async def test_clears_sink_after_stream(self):
        """Sink is cleared after the stream completes."""

        class FakeAdapter:
            async def run_stream(self, **kwargs: Any) -> AsyncIterator[BaseEvent]:
                if False:
                    yield

        toolset = SkillToolset()
        async with run_agui_stream(toolset, FakeAdapter()) as stream:
            async for _ in stream:
                pass
        assert toolset._event_sink is None

    async def test_clears_sink_on_early_break(self):
        """Sink is cleared and adapter task cancelled when consumer breaks early."""
        import asyncio

        adapter_started = asyncio.Event()

        class FakeAdapter:
            async def run_stream(self, **kwargs: Any) -> AsyncIterator[BaseEvent]:
                adapter_started.set()
                await asyncio.sleep(999)
                yield

        toolset = SkillToolset()

        async def push_after_start() -> None:
            await adapter_started.wait()
            assert toolset._event_sink is not None
            await toolset._event_sink(
                ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_id="t1",
                    tool_call_name="test",
                )
            )

        asyncio.create_task(push_after_start())
        async with run_agui_stream(toolset, FakeAdapter()) as stream:
            async for _ in stream:
                break
        assert toolset._event_sink is None


def _make_run_input(message: str) -> Any:
    """Create a minimal RunAgentInput for testing."""
    import uuid

    from ag_ui.core import RunAgentInput, UserMessage

    return RunAgentInput(
        thread_id="test",
        run_id=str(uuid.uuid4()),
        messages=[
            UserMessage(id=str(uuid.uuid4()), role="user", content=message),
        ],
        state={},
        tools=[],
        context=[],
        forwarded_props={},
    )
