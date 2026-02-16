from pathlib import Path

import pytest
from pydantic_ai import Agent
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
    Task,
    TaskStatus,
)
from haiku.skills.prompts import SKILL_PROMPT

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

    def test_tasks_empty_initially(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        assert toolset.tasks == []

    def test_clear_tasks(self):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        toolset._tasks.append(Task(id="1", description="test", skill="a"))
        assert len(toolset.tasks) == 1
        toolset.clear_tasks()
        assert toolset.tasks == []


class TestRunSkill:
    async def test_run_skill(self, allow_model_requests: None):
        toolset = SkillToolset(skill_paths=[FIXTURES])
        toolset.registry.activate("simple-skill")
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
        assert toolset.tasks == []

    async def test_run_with_skill_execution(self, allow_model_requests: None):
        """Agent delegates to skills and tracks tasks on toolset."""
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
        assert len(toolset.tasks) >= 1
        for task in toolset.tasks:
            assert task.status == TaskStatus.COMPLETED

    async def test_run_with_unknown_skill_records_failure(
        self, allow_model_requests: None
    ):
        """Unknown skill in execute_skill records task failure."""
        toolset = SkillToolset(skill_paths=[FIXTURES])
        agent = Agent(
            TestModel(), instructions=toolset.system_prompt, toolsets=[toolset]
        )
        await agent.run("Do something.")
        assert len(toolset.tasks) >= 1
        for task in toolset.tasks:
            assert task.status == TaskStatus.FAILED
            assert task.error is not None

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
        assert len(toolset.tasks) >= 1

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
        assert len(toolset.tasks) >= 1
