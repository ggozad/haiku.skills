from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.result import RunUsage

from haiku.skills.agent import SkillToolset
from haiku.skills.models import Skill, SkillMetadata, SkillSource
from haiku.skills.prompts import build_system_prompt
from haiku.skills.tasks import Task, TaskStatus, TaskToolset


class TestTaskModel:
    def test_defaults(self):
        task = Task(id="1", subject="Do something")
        assert task.status == TaskStatus.PENDING
        assert task.depends_on == []
        assert task.description == ""

    def test_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"


class TestCreateTask:
    async def test_creates_task_with_id(self, allow_model_requests: None):
        toolset = TaskToolset()
        agent = Agent(TestModel(), toolsets=[toolset])
        result = await agent.run("Create a task.")
        assert result.output

    async def test_auto_incrementing_ids(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        r1 = await toolset.create_task(ctx, subject="First")
        r2 = await toolset.create_task(ctx, subject="Second")
        assert "1" in r1
        assert "2" in r2

    async def test_with_dependencies(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        await toolset.create_task(ctx, subject="First")
        result = await toolset.create_task(ctx, subject="Second", depends_on=["1"])
        assert "2" in result

    async def test_rejects_nonexistent_dependency(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        result = await toolset.create_task(ctx, subject="Bad", depends_on=["99"])
        assert "Error" in result


class TestUpdateTask:
    async def test_changes_status(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        await toolset.create_task(ctx, subject="Task")
        result = await toolset.update_task(ctx, task_id="1", status="in_progress")
        assert "1" in result

    async def test_unknown_id_returns_error(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        result = await toolset.update_task(ctx, task_id="99", status="completed")
        assert "Error" in result

    async def test_rejects_invalid_status(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        await toolset.create_task(ctx, subject="Task")
        result = await toolset.update_task(ctx, task_id="1", status="bogus")
        assert "Error" in result


class TestListTasks:
    async def test_empty(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        result = await toolset.list_tasks(ctx)
        assert "No tasks" in result

    async def test_shows_all_tasks(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        await toolset.create_task(ctx, subject="First")
        await toolset.create_task(ctx, subject="Second", depends_on=["1"])
        result = await toolset.list_tasks(ctx)
        assert "First" in result
        assert "Second" in result
        assert "pending" in result
        assert "1" in result  # dependency reference


class TestLifecycle:
    async def test_reset_clears_tasks(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        await toolset.create_task(ctx, subject="Task")
        toolset.reset()
        result = await toolset.list_tasks(ctx)
        assert "No tasks" in result

    async def test_get_tools_resets_at_step_zero(self, allow_model_requests: None):
        toolset = TaskToolset()
        ctx_step1 = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        await toolset.create_task(ctx_step1, subject="Task")

        ctx_step0 = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=0,
        )
        await toolset.get_tools(ctx_step0)

        result = await toolset.list_tasks(ctx_step1)
        assert "No tasks" in result

    async def test_get_tools_preserves_at_nonzero_step(
        self, allow_model_requests: None
    ):
        toolset = TaskToolset()
        ctx = RunContext(
            deps=None,
            model=TestModel(),
            usage=RunUsage(),
            run_step=1,
        )
        await toolset.create_task(ctx, subject="Task")
        await toolset.get_tools(ctx)
        result = await toolset.list_tasks(ctx)
        assert "Task" in result


class TestIntegration:
    async def test_both_toolsets_together(self, allow_model_requests: None):
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        skill_toolset = SkillToolset(skills=[skill])
        task_toolset = TaskToolset()
        agent = Agent(
            TestModel(),
            instructions=build_system_prompt(
                skill_toolset.skill_catalog, with_tasks=True
            ),
            toolsets=[skill_toolset, task_toolset],
        )
        result = await agent.run("Do something complex.")
        assert result.output
