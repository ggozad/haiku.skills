from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model

from haiku.skills.agent import SkillToolset
from haiku.skills.models import Skill
from haiku.skills.prompts import DEFAULT_PREAMBLE, build_system_prompt


@dataclass
class SkillsCapability(AbstractCapability[Any]):
    """Expose skills as a pydantic-ai capability.

    Wraps a ``SkillToolset`` and provides both the toolset and a system prompt
    built from the skill catalog.  The underlying toolset is accessible via the
    ``toolset`` attribute for advanced use (state, registry, event sink, etc.).
    """

    toolset: SkillToolset
    preamble: str = DEFAULT_PREAMBLE

    def __init__(
        self,
        *,
        skills: list[Skill] | None = None,
        skill_paths: list[Path] | None = None,
        use_entrypoints: bool = False,
        skill_model: str | Model | None = None,
        use_subagents: bool = True,
        preamble: str = DEFAULT_PREAMBLE,
    ) -> None:
        self.toolset = SkillToolset(
            skills=skills,
            skill_paths=skill_paths,
            use_entrypoints=use_entrypoints,
            skill_model=skill_model,
            use_subagents=use_subagents,
        )
        self.preamble = preamble

    def get_toolset(self) -> SkillToolset:
        return self.toolset

    def get_instructions(self) -> Callable[[RunContext[Any]], str]:
        def _instructions(ctx: RunContext[Any]) -> str:
            return build_system_prompt(
                self.toolset.skill_catalog,
                preamble=self.preamble,
                use_subagents=self.toolset._use_subagents,
            )

        return _instructions
