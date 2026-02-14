from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai.toolsets.function import FunctionToolset

from haiku.skills.models import (
    DecompositionPlan,
    OrchestratorPhase,
    OrchestratorResult,
    OrchestratorState,
    Skill,
    SkillMetadata,
    SkillSource,
    Task,
    TaskStatus,
)


class TestSkillMetadata:
    def test_minimal(self):
        meta = SkillMetadata(name="my-skill", description="Does things.")
        assert meta.name == "my-skill"
        assert meta.description == "Does things."
        assert meta.license is None
        assert meta.compatibility is None
        assert meta.metadata == {}
        assert meta.allowed_tools == []

    def test_all_fields(self):
        meta = SkillMetadata(
            name="full-skill",
            description="A full skill.",
            license="MIT",
            compatibility="Requires network",
            metadata={"author": "test", "version": "1.0"},
            allowed_tools=["Bash(git:*)", "Read"],
        )
        assert meta.license == "MIT"
        assert meta.compatibility == "Requires network"
        assert meta.metadata == {"author": "test", "version": "1.0"}
        assert meta.allowed_tools == ["Bash(git:*)", "Read"]

    def test_name_validation_uppercase_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="MySkill", description="Bad name.")

    def test_name_validation_leading_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="-bad", description="Bad name.")

    def test_name_validation_trailing_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="bad-", description="Bad name.")

    def test_name_validation_consecutive_hyphens_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="bad--name", description="Bad name.")

    def test_name_validation_too_long_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="a" * 65, description="Too long name.")

    def test_name_validation_empty_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="", description="Empty name.")

    def test_description_empty_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="ok", description="")

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="ok", description="x" * 1025)


class TestSkillSource:
    def test_values(self):
        assert SkillSource.FILESYSTEM.value == "filesystem"
        assert SkillSource.ENTRYPOINT.value == "entrypoint"
        assert SkillSource.MCP.value == "mcp"


class TestSkill:
    def test_minimal(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        assert skill.metadata.name == "test"
        assert skill.source == SkillSource.FILESYSTEM
        assert skill.path is None
        assert skill.instructions is None
        assert skill.tools == []
        assert skill.toolsets == []

    def test_with_path_and_instructions(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            path=Path("/some/path"),
            instructions="Do the thing.",
        )
        assert skill.path == Path("/some/path")
        assert skill.instructions == "Do the thing."

    def test_with_tools(self):
        def my_tool(x: int) -> int:
            return x * 2

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM, tools=[my_tool])
        assert len(skill.tools) == 1
        assert skill.tools[0] is my_tool

    def test_with_toolsets(self):
        toolset = FunctionToolset()
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM, toolsets=[toolset])
        assert len(skill.toolsets) == 1
        assert skill.toolsets[0] is toolset

    def test_tools_and_toolsets_settable(self):
        def tool_a(x: int) -> int:
            return x

        def tool_b(x: int) -> int:
            return x

        toolset = FunctionToolset()
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        skill.tools = [tool_a, tool_b]
        skill.toolsets = [toolset]
        assert len(skill.tools) == 2
        assert len(skill.toolsets) == 1

    def test_tools_and_toolsets_excluded_from_serialization(self):
        def my_tool(x: int) -> int:
            return x * 2

        toolset = FunctionToolset()
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            tools=[my_tool],
            toolsets=[toolset],
        )
        data = skill.model_dump()
        assert "tools" not in data
        assert "toolsets" not in data


class TestTaskStatus:
    def test_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


class TestTask:
    def test_defaults(self):
        task = Task(id="1", description="Do something.", skills=["my-skill"])
        assert task.status == TaskStatus.PENDING
        assert task.result is None
        assert task.error is None

    def test_completed_task(self):
        task = Task(
            id="1",
            description="Do something.",
            skills=["my-skill"],
            status=TaskStatus.COMPLETED,
            result="Done.",
        )
        assert task.status == TaskStatus.COMPLETED
        assert task.result == "Done."


class TestDecompositionPlan:
    def test_plan(self):
        tasks = [Task(id="1", description="Step 1.", skills=["a"])]
        plan = DecompositionPlan(tasks=tasks, reasoning="Simple task.")
        assert len(plan.tasks) == 1
        assert plan.reasoning == "Simple task."


class TestOrchestratorPhase:
    def test_values(self):
        assert OrchestratorPhase.IDLE.value == "idle"
        assert OrchestratorPhase.PLANNING.value == "planning"
        assert OrchestratorPhase.EXECUTING.value == "executing"
        assert OrchestratorPhase.SYNTHESIZING.value == "synthesizing"


class TestOrchestratorState:
    def test_defaults(self):
        state = OrchestratorState()
        assert state.phase == OrchestratorPhase.IDLE
        assert state.plan is None
        assert state.tasks == []
        assert state.result is None

    def test_with_plan_and_tasks(self):
        tasks = [Task(id="1", description="Do it.", skills=["a"])]
        plan = DecompositionPlan(tasks=tasks, reasoning="Because.")
        state = OrchestratorState(
            phase=OrchestratorPhase.EXECUTING,
            plan=plan,
            tasks=tasks,
        )
        assert state.phase == OrchestratorPhase.EXECUTING
        assert state.plan is plan
        assert len(state.tasks) == 1

    def test_with_result(self):
        tasks = [
            Task(
                id="1",
                description="Step 1.",
                skills=["a"],
                status=TaskStatus.COMPLETED,
                result="Done.",
            )
        ]
        result = OrchestratorResult(answer="Final.", tasks=tasks)
        state = OrchestratorState(result=result)
        assert state.result is result
        assert state.result.answer == "Final."


class TestOrchestratorResult:
    def test_result(self):
        tasks = [
            Task(
                id="1",
                description="Step 1.",
                skills=["a"],
                status=TaskStatus.COMPLETED,
                result="Done.",
            )
        ]
        result = OrchestratorResult(answer="Final answer.", tasks=tasks)
        assert result.answer == "Final answer."
        assert len(result.tasks) == 1
