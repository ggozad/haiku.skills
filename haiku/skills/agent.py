from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from haiku.skills.models import OrchestratorState, Skill
from haiku.skills.orchestrator import Orchestrator
from haiku.skills.prompts import MAIN_AGENT_PROMPT
from haiku.skills.registry import SkillRegistry


@dataclass
class AgentDeps:
    orchestrator: Orchestrator
    state: OrchestratorState


async def _orchestrate(ctx: RunContext[AgentDeps], request: str) -> str:
    """Delegate a request to the skill orchestrator.

    Use this when the request requires specialized skills.
    The orchestrator decomposes the request into subtasks,
    executes them using the appropriate skills, and returns
    the synthesized result.

    Args:
        request: The request to process using available skills.
    """
    result = await ctx.deps.orchestrator.orchestrate(request, ctx.deps.state)
    return result.answer


class SkillAgent:
    def __init__(
        self, model: Model, orchestrator: Orchestrator, registry: SkillRegistry
    ) -> None:
        self._orchestrator = orchestrator
        self._registry = registry
        catalog = self._build_skill_catalog()
        prompt = MAIN_AGENT_PROMPT.format(skill_catalog=catalog)
        self._agent = Agent[AgentDeps, str](
            model,
            system_prompt=prompt,
            tools=[_orchestrate],
            deps_type=AgentDeps,
        )
        self._history: list[ModelMessage] = []

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def skills(self) -> list[str]:
        return self._registry.names

    @property
    def history(self) -> list[ModelMessage]:
        return self._history

    def clear_history(self) -> None:
        self._history = []

    async def run(self, prompt: str, state: OrchestratorState) -> str:
        deps = AgentDeps(orchestrator=self._orchestrator, state=state)
        result = await self._agent.run(prompt, deps=deps, message_history=self._history)
        self._history = list(result.all_messages())
        if state.result:
            return state.result.answer
        return result.output

    def _build_skill_catalog(self) -> str:
        lines: list[str] = []
        for meta in self._registry.list_metadata():
            lines.append(f"- **{meta.name}**: {meta.description}")
        return "\n".join(lines)


def create_agent(
    model: Model,
    skills: list[Skill] | None = None,
    skill_paths: list[Path] | None = None,
    use_entrypoints: bool = False,
    max_concurrency: int = 5,
) -> SkillAgent:
    """Create a skill-powered agent."""
    registry = SkillRegistry()
    if skill_paths:
        registry.discover(paths=skill_paths)
    if use_entrypoints:
        registry.discover(use_entrypoints=True)
    if skills:
        for skill in skills:
            registry.register(skill)
    orchestrator = Orchestrator(
        model=model, registry=registry, max_concurrency=max_concurrency
    )
    return SkillAgent(model=model, orchestrator=orchestrator, registry=registry)
