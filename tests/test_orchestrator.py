from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from haiku.skills.models import DecompositionPlan, Task, TaskStatus
from haiku.skills.orchestrator import Orchestrator
from haiku.skills.prompts import PLAN_PROMPT, SUBTASK_PROMPT, SYNTHESIS_PROMPT
from haiku.skills.registry import SkillRegistry

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.discover(paths=[FIXTURES])
    return reg


class TestPrompts:
    def test_plan_prompt_has_placeholder(self):
        assert "{skill_catalog}" in PLAN_PROMPT

    def test_subtask_prompt_has_placeholders(self):
        assert "{task_description}" in SUBTASK_PROMPT
        assert "{skill_instructions}" in SUBTASK_PROMPT

    def test_synthesis_prompt_has_placeholders(self):
        assert "{user_request}" in SYNTHESIS_PROMPT
        assert "{task_results}" in SYNTHESIS_PROMPT


class TestOrchestrator:
    async def test_plan_returns_decomposition(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        plan = DecompositionPlan(
            tasks=[Task(id="1", description="Do the thing.", skills=["simple-skill"])],
            reasoning="Simple request.",
        )
        model = TestModel(custom_output_args=plan.model_dump())
        orchestrator = Orchestrator(model=model, registry=registry)
        result = await orchestrator.plan("Do something simple.")
        assert len(result.tasks) >= 1
        assert result.reasoning

    async def test_execute_task(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        task = Task(id="1", description="Do the thing.", skills=["simple-skill"])
        model = TestModel(custom_output_text="Task completed successfully.")
        orchestrator = Orchestrator(model=model, registry=registry)
        executed = await orchestrator.execute_task(task, "Do something.")
        assert executed.status == TaskStatus.COMPLETED
        assert executed.result is not None

    async def test_execute_task_activates_skills(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        task = Task(id="1", description="Do the thing.", skills=["simple-skill"])
        model = TestModel(custom_output_text="Done.")
        orchestrator = Orchestrator(model=model, registry=registry)
        await orchestrator.execute_task(task, "Do something.")
        skill = registry.get("simple-skill")
        assert skill is not None
        assert skill.instructions is not None

    async def test_synthesize(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        tasks = [
            Task(
                id="1",
                description="Step 1.",
                skills=["simple-skill"],
                status=TaskStatus.COMPLETED,
                result="Result 1.",
            ),
            Task(
                id="2",
                description="Step 2.",
                skills=["skill-with-refs"],
                status=TaskStatus.COMPLETED,
                result="Result 2.",
            ),
        ]
        model = TestModel(custom_output_text="Combined answer.")
        orchestrator = Orchestrator(model=model, registry=registry)
        answer = await orchestrator.synthesize("Do two things.", tasks)
        assert answer

    async def test_execute_task_unknown_skill_fails(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        task = Task(id="1", description="Do the thing.", skills=["nonexistent-skill"])
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        executed = await orchestrator.execute_task(task, "Do something.")
        assert executed.status == TaskStatus.FAILED
        assert executed.error is not None
        assert "nonexistent-skill" in executed.error

    async def test_orchestrate_end_to_end(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        result = await orchestrator.orchestrate("Do something.")
        assert result.answer
        assert len(result.tasks) >= 1
        for task in result.tasks:
            assert task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
