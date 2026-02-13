import asyncio
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.models import Model

from haiku.skills.models import (
    DecompositionPlan,
    OrchestratorResult,
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

    async def plan(self, user_request: str) -> DecompositionPlan:
        catalog = self._build_skill_catalog()
        system_prompt = PLAN_PROMPT.format(skill_catalog=catalog)
        agent = Agent(
            self._model,
            system_prompt=system_prompt,
            output_type=DecompositionPlan,
        )
        result = await agent.run(user_request)
        return cast(DecompositionPlan, result.output)

    async def execute_task(self, task: Task, user_request: str) -> Task:
        task.status = TaskStatus.IN_PROGRESS
        try:
            skill_instructions = self._gather_skill_instructions(task.skills)
            system_prompt = SUBTASK_PROMPT.format(
                task_description=task.description,
                skill_instructions=skill_instructions,
            )
            agent = Agent(self._model, system_prompt=system_prompt)
            async with self._semaphore:
                result = await agent.run(user_request)
            task.status = TaskStatus.COMPLETED
            task.result = result.output
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        return task

    async def synthesize(self, user_request: str, tasks: list[Task]) -> str:
        task_results = "\n\n".join(
            f"### Task {t.id}: {t.description}\n{t.result or t.error or 'No result.'}"
            for t in tasks
        )
        system_prompt = SYNTHESIS_PROMPT.format(
            user_request=user_request,
            task_results=task_results,
        )
        agent = Agent(self._model, system_prompt=system_prompt)
        result = await agent.run(user_request)
        return result.output

    async def orchestrate(self, user_request: str) -> OrchestratorResult:
        decomposition = await self.plan(user_request)
        executed = await asyncio.gather(
            *(self.execute_task(t, user_request) for t in decomposition.tasks)
        )
        tasks = list(executed)
        answer = await self.synthesize(user_request, tasks)
        return OrchestratorResult(answer=answer, tasks=tasks)

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
