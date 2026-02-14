import asyncio
from collections.abc import Callable
from typing import Any

from pydantic_ai import Agent, Tool
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from haiku.skills.models import (
    DecompositionPlan,
    OrchestratorPhase,
    OrchestratorResult,
    OrchestratorState,
    Task,
    TaskStatus,
)
from haiku.skills.prompts import PLAN_PROMPT, SUBTASK_PROMPT, SYNTHESIS_PROMPT
from haiku.skills.registry import SkillRegistry


class Orchestrator:
    def __init__(
        self,
        model: Model,
        registry: SkillRegistry,
        max_concurrency: int = 5,
    ) -> None:
        self._model = model
        self._registry = registry
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def _build_skill_catalog(self) -> str:
        lines: list[str] = []
        for meta in self._registry.list_metadata():
            lines.append(f"- **{meta.name}**: {meta.description}")
        return "\n".join(lines)

    async def plan(
        self, user_request: str, state: OrchestratorState
    ) -> DecompositionPlan:
        catalog = self._build_skill_catalog()
        system_prompt = PLAN_PROMPT.format(skill_catalog=catalog)
        agent = Agent[OrchestratorState, DecompositionPlan](
            self._model,
            system_prompt=system_prompt,
            output_type=DecompositionPlan,
            deps_type=OrchestratorState,
        )
        result = await agent.run(user_request, deps=state)
        return result.output

    async def execute_task(
        self, task: Task, user_request: str, state: OrchestratorState
    ) -> Task:
        task.status = TaskStatus.IN_PROGRESS
        try:
            skill_instructions = self._gather_skill_instructions(task.skills)
            skill_tools = self._gather_skill_tools(task.skills)
            skill_toolsets = self._gather_skill_toolsets(task.skills)
            system_prompt = SUBTASK_PROMPT.format(
                task_description=task.description,
                skill_instructions=skill_instructions,
            )
            agent = Agent[OrchestratorState, str](
                self._model,
                system_prompt=system_prompt,
                tools=skill_tools,
                toolsets=skill_toolsets or None,
                deps_type=OrchestratorState,
            )
            async with self._semaphore:
                result = await agent.run(user_request, deps=state)
            task.status = TaskStatus.COMPLETED
            task.result = result.output
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        return task

    async def synthesize(
        self, user_request: str, tasks: list[Task], state: OrchestratorState
    ) -> str:
        task_results = "\n\n".join(
            f"### Task {t.id}: {t.description}\n{t.result or t.error or 'No result.'}"
            for t in tasks
        )
        system_prompt = SYNTHESIS_PROMPT.format(
            user_request=user_request,
            task_results=task_results,
        )
        agent = Agent[OrchestratorState, str](
            self._model,
            system_prompt=system_prompt,
            deps_type=OrchestratorState,
        )
        result = await agent.run(user_request, deps=state)
        return result.output

    async def orchestrate(
        self, user_request: str, state: OrchestratorState
    ) -> OrchestratorResult:
        state.phase = OrchestratorPhase.IDLE
        state.plan = None
        state.tasks = []
        state.result = None

        state.phase = OrchestratorPhase.PLANNING
        decomposition = await self.plan(user_request, state)
        state.plan = decomposition
        state.tasks = list(decomposition.tasks)

        state.phase = OrchestratorPhase.EXECUTING
        executed = await asyncio.gather(
            *(self.execute_task(t, user_request, state) for t in state.tasks)
        )
        state.tasks = list(executed)

        state.phase = OrchestratorPhase.SYNTHESIZING
        answer = await self.synthesize(user_request, state.tasks, state)

        state.phase = OrchestratorPhase.IDLE
        result = OrchestratorResult(answer=answer, tasks=state.tasks)
        state.result = result
        return result

    def _gather_skill_tools(
        self, skill_names: list[str]
    ) -> list[Tool[Any] | Callable[..., Any]]:
        tools: list[Tool[Any] | Callable[..., Any]] = []
        for name in skill_names:
            skill = self._registry.get(name)
            if skill and skill.tools:
                tools.extend(skill.tools)
        return tools

    def _gather_skill_toolsets(
        self, skill_names: list[str]
    ) -> list[AbstractToolset[Any]]:
        toolsets: list[AbstractToolset[Any]] = []
        for name in skill_names:
            skill = self._registry.get(name)
            if skill and skill.toolsets:
                toolsets.extend(skill.toolsets)
        return toolsets

    def _gather_skill_instructions(self, skill_names: list[str]) -> str:
        parts: list[str] = []
        for name in skill_names:
            skill = self._registry.get(name)
            if skill is None:
                raise KeyError(f"Skill '{name}' not found in registry")
            self._registry.activate(name)
            if skill.instructions:
                parts.append(f"## {name}\n\n{skill.instructions}")
        return "\n\n---\n\n".join(parts) if parts else "No specific instructions."
