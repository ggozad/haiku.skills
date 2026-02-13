from pathlib import Path

from pydantic_ai.models import Model

from haiku.skills.models import OrchestratorResult, Skill
from haiku.skills.orchestrator import Orchestrator
from haiku.skills.registry import SkillRegistry


class SkillAgent:
    def __init__(self, orchestrator: Orchestrator, registry: SkillRegistry) -> None:
        self._orchestrator = orchestrator
        self._registry = registry

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def skills(self) -> list[str]:
        return self._registry.names

    async def run(self, prompt: str) -> OrchestratorResult:
        return await self._orchestrator.orchestrate(prompt)


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
    return SkillAgent(orchestrator=orchestrator, registry=registry)
