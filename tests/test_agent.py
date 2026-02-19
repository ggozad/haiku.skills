from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets.function import FunctionToolset

from haiku.skills.agent import (
    SkillToolset,
    _create_read_resource,
    _last_tool_result,
    _run_skill,
)
from haiku.skills.models import (
    Skill,
    SkillMetadata,
    SkillSource,
)
from haiku.skills.prompts import SKILL_PROMPT
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

    def test_skill_catalog(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        catalog = toolset.skill_catalog
        assert "simple-skill" in catalog
        assert "skill-with-refs" in catalog

    def test_system_prompt(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        prompt = toolset.system_prompt
        assert "simple-skill" in prompt
        assert "Available skills" in prompt


class TestRunSkill:
    async def test_run_skill(self, allow_model_requests: None):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        skill = toolset.registry.get("simple-skill")
        assert skill is not None
        result = await _run_skill(TestModel(), skill, "Do something.")
        assert result

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
        result = await _run_skill(TestModel(), skill, "Greet Alice.")
        assert result

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
        result = await _run_skill(TestModel(), skill, "Greet Alice.")
        assert result


class TestLastToolResult:
    def test_returns_none_for_empty_messages(self):
        assert _last_tool_result([]) is None

    def test_returns_none_when_no_tool_returns(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

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
        result = await _run_skill(TestModel(call_tools=[]), skill, "Do something.")
        assert result

    async def test_no_resources_no_section(self, allow_model_requests: None):
        skill = Skill(
            metadata=SkillMetadata(name="r", description="No resources."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        result = await _run_skill(TestModel(call_tools=[]), skill, "Do something.")
        assert result


class TestAgent:
    async def test_direct_chat(self, allow_model_requests: None):
        """Agent responds directly without skill execution for simple chat."""
        model = TestModel(call_tools=[], custom_output_text="Hello there!")
        toolset = SkillToolset(skill_paths=[FIXTURES])
        agent = Agent(model, instructions=toolset.system_prompt, toolsets=[toolset])
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
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_run_with_unknown_skill(self, allow_model_requests: None):
        """Unknown skill in execute_skill returns error message."""
        toolset = SkillToolset(skill_paths=[FIXTURES])
        agent = Agent(
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
        )
        result = await agent.run("Do something.")
        assert result.output

    async def test_run_skill_exception_returns_error(
        self, monkeypatch: pytest.MonkeyPatch, allow_model_requests: None
    ):
        """Exception during _run_skill returns an error string."""
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

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
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
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
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
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
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
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
        """Without state, deps is None."""
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
        assert captured_deps[0] is None


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
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
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
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
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
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
        )
        result = await agent.run("Do something.")
        assert result.output
