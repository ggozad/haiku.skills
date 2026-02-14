from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets.function import FunctionToolset

from haiku.skills.models import (
    DecompositionPlan,
    OrchestratorPhase,
    OrchestratorState,
    Skill,
    SkillMetadata,
    SkillSource,
    Task,
    TaskStatus,
)
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
        state = OrchestratorState()
        result = await orchestrator.plan("Do something simple.", state)
        assert len(result.tasks) >= 1
        assert result.reasoning

    async def test_execute_task(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        task = Task(id="1", description="Do the thing.", skills=["simple-skill"])
        model = TestModel(custom_output_text="Task completed successfully.")
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        executed = await orchestrator.execute_task(task, "Do something.", state)
        assert executed.status == TaskStatus.COMPLETED
        assert executed.result is not None

    async def test_execute_task_activates_skills(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        task = Task(id="1", description="Do the thing.", skills=["simple-skill"])
        model = TestModel(custom_output_text="Done.")
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        await orchestrator.execute_task(task, "Do something.", state)
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
        state = OrchestratorState()
        answer = await orchestrator.synthesize("Do two things.", tasks, state)
        assert answer

    async def test_execute_task_unknown_skill_fails(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        task = Task(id="1", description="Do the thing.", skills=["nonexistent-skill"])
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        executed = await orchestrator.execute_task(task, "Do something.", state)
        assert executed.status == TaskStatus.FAILED
        assert executed.error is not None
        assert "nonexistent-skill" in executed.error

    async def test_orchestrate_end_to_end(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        result = await orchestrator.orchestrate("Do something.", state)
        assert result.answer
        assert len(result.tasks) >= 1
        for task in result.tasks:
            assert task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    def test_gather_skill_tools_empty(self, registry: SkillRegistry):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        tools = orchestrator._gather_skill_tools(["simple-skill"])
        assert tools == []

    def test_gather_skill_tools_with_tools(self):
        def my_tool(x: int) -> int:
            """Double a number."""
            return x * 2

        meta = SkillMetadata(name="tool-skill", description="Has tools.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            instructions="Use the tool.",
            tools=[my_tool],
        )
        registry = SkillRegistry()
        registry.register(skill)
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        tools = orchestrator._gather_skill_tools(["tool-skill"])
        assert len(tools) == 1
        assert tools[0] is my_tool

    def test_gather_skill_tools_unknown_skill_skipped(self, registry: SkillRegistry):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        tools = orchestrator._gather_skill_tools(["nonexistent"])
        assert tools == []

    async def test_execute_task_with_tools(self, allow_model_requests: None):
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
        registry = SkillRegistry()
        registry.register(skill)
        model = TestModel(custom_output_text="The answer is 42.")
        orchestrator = Orchestrator(model=model, registry=registry)
        task = Task(id="1", description="Greet Alice.", skills=["greeter"])
        state = OrchestratorState()
        executed = await orchestrator.execute_task(task, "Greet Alice.", state)
        assert executed.error is None, f"Task failed: {executed.error}"
        assert executed.status == TaskStatus.COMPLETED

    def test_gather_skill_toolsets_empty(self, registry: SkillRegistry):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        toolsets = orchestrator._gather_skill_toolsets(["simple-skill"])
        assert toolsets == []

    def test_gather_skill_toolsets_with_toolsets(self):
        def greet(name: str) -> str:
            """Greet someone by name."""
            return f"Hello, {name}!"

        toolset = FunctionToolset()
        toolset.add_function(greet)
        meta = SkillMetadata(name="ts-skill", description="Has toolsets.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            instructions="Use the toolset.",
            toolsets=[toolset],
        )
        registry = SkillRegistry()
        registry.register(skill)
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        toolsets = orchestrator._gather_skill_toolsets(["ts-skill"])
        assert len(toolsets) == 1
        assert toolsets[0] is toolset

    def test_gather_skill_toolsets_unknown_skill_skipped(self, registry: SkillRegistry):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        toolsets = orchestrator._gather_skill_toolsets(["nonexistent"])
        assert toolsets == []

    async def test_execute_task_with_toolsets(self, allow_model_requests: None):
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
        registry = SkillRegistry()
        registry.register(skill)
        model = TestModel(custom_output_text="Hello!")
        orchestrator = Orchestrator(model=model, registry=registry)
        task = Task(id="1", description="Greet Alice.", skills=["greeter"])
        state = OrchestratorState()
        executed = await orchestrator.execute_task(task, "Greet Alice.", state)
        assert executed.error is None, f"Task failed: {executed.error}"
        assert executed.status == TaskStatus.COMPLETED

    async def test_state_after_orchestrate(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        result = await orchestrator.orchestrate("Do something.", state)
        assert state.phase == OrchestratorPhase.IDLE
        assert state.plan is not None
        assert state.tasks == result.tasks
        assert state.result is not None
        assert state.result.answer == result.answer
        assert state.result.tasks == result.tasks

    async def test_state_tracks_phase_transitions(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        phases_seen: list[OrchestratorPhase] = []

        original_plan = orchestrator.plan
        original_execute = orchestrator.execute_task
        original_synthesize = orchestrator.synthesize

        async def tracking_plan(
            user_request: str, state: OrchestratorState
        ) -> DecompositionPlan:
            phases_seen.append(state.phase)
            return await original_plan(user_request, state)

        async def tracking_execute(
            task: Task, user_request: str, state: OrchestratorState
        ) -> Task:
            phases_seen.append(state.phase)
            return await original_execute(task, user_request, state)

        async def tracking_synthesize(
            user_request: str, tasks: list[Task], state: OrchestratorState
        ) -> str:
            phases_seen.append(state.phase)
            return await original_synthesize(user_request, tasks, state)

        orchestrator.plan = tracking_plan  # type: ignore[assignment]
        orchestrator.execute_task = tracking_execute  # type: ignore[assignment]
        orchestrator.synthesize = tracking_synthesize  # type: ignore[assignment]

        await orchestrator.orchestrate("Do something.", state)

        assert OrchestratorPhase.PLANNING in phases_seen
        assert OrchestratorPhase.EXECUTING in phases_seen
        assert OrchestratorPhase.SYNTHESIZING not in phases_seen

    async def test_state_tracks_phase_transitions_multi_task(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        multi_plan = DecompositionPlan(
            tasks=[
                Task(id="1", description="First.", skills=["simple-skill"]),
                Task(id="2", description="Second.", skills=["simple-skill"]),
            ],
            reasoning="Two tasks.",
        )
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        phases_seen: list[OrchestratorPhase] = []

        original_execute = orchestrator.execute_task
        original_synthesize = orchestrator.synthesize

        async def fixed_plan(
            user_request: str, state: OrchestratorState
        ) -> DecompositionPlan:
            phases_seen.append(state.phase)
            return multi_plan

        async def tracking_execute(
            task: Task, user_request: str, state: OrchestratorState
        ) -> Task:
            phases_seen.append(state.phase)
            return await original_execute(task, user_request, state)

        async def tracking_synthesize(
            user_request: str, tasks: list[Task], state: OrchestratorState
        ) -> str:
            phases_seen.append(state.phase)
            return await original_synthesize(user_request, tasks, state)

        orchestrator.plan = fixed_plan  # type: ignore[assignment]
        orchestrator.execute_task = tracking_execute  # type: ignore[assignment]
        orchestrator.synthesize = tracking_synthesize  # type: ignore[assignment]

        await orchestrator.orchestrate("Do two things.", state)

        assert OrchestratorPhase.PLANNING in phases_seen
        assert OrchestratorPhase.EXECUTING in phases_seen
        assert OrchestratorPhase.SYNTHESIZING in phases_seen

    async def test_orchestrate_skips_synthesis_for_single_task(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        single_plan = DecompositionPlan(
            tasks=[Task(id="1", description="Do it.", skills=["simple-skill"])],
            reasoning="One task.",
        )
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        synthesize_called = False

        async def fixed_plan(
            user_request: str, state: OrchestratorState
        ) -> DecompositionPlan:
            return single_plan

        async def tracking_synthesize(
            user_request: str, tasks: list[Task], state: OrchestratorState
        ) -> str:
            nonlocal synthesize_called
            synthesize_called = True
            return "should not be used"

        orchestrator.plan = fixed_plan  # type: ignore[assignment]
        orchestrator.synthesize = tracking_synthesize  # type: ignore[assignment]

        result = await orchestrator.orchestrate("Do something.", state)
        assert not synthesize_called
        assert len(state.tasks) == 1
        assert state.tasks[0].status == TaskStatus.COMPLETED
        assert result.answer == state.tasks[0].result

    async def test_orchestrate_skips_synthesis_for_single_failed_task(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        failed_plan = DecompositionPlan(
            tasks=[Task(id="1", description="Do it.", skills=["nonexistent-skill"])],
            reasoning="One task.",
        )
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        synthesize_called = False

        async def fixed_plan(
            user_request: str, state: OrchestratorState
        ) -> DecompositionPlan:
            return failed_plan

        async def tracking_synthesize(
            user_request: str, tasks: list[Task], state: OrchestratorState
        ) -> str:
            nonlocal synthesize_called
            synthesize_called = True
            return "should not be used"

        orchestrator.plan = fixed_plan  # type: ignore[assignment]
        orchestrator.synthesize = tracking_synthesize  # type: ignore[assignment]

        result = await orchestrator.orchestrate("Do something.", state)
        assert not synthesize_called
        assert "nonexistent-skill" in result.answer

    async def test_state_resets_on_new_orchestration(
        self, registry: SkillRegistry, allow_model_requests: None
    ):
        model = TestModel()
        orchestrator = Orchestrator(model=model, registry=registry)
        state = OrchestratorState()
        first_result = await orchestrator.orchestrate("First request.", state)
        assert state.result is not None
        assert state.result.answer == first_result.answer
        second_result = await orchestrator.orchestrate("Second request.", state)
        assert state.result is not None
        assert state.result.answer == second_result.answer
        assert state.plan is not None
        assert state.phase == OrchestratorPhase.IDLE
