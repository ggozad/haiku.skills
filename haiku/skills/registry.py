from pathlib import Path

from haiku.skills.discovery import discover_from_entrypoints, discover_from_paths
from haiku.skills.models import Skill, SkillMetadata
from haiku.skills.parser import parse_skill_md


class SkillRegistry:
    """Central registry for skill discovery, loading, and lookup."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        name = skill.metadata.name
        if name in self._skills:
            raise ValueError(f"Skill '{name}' is already registered")
        self._skills[name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    @property
    def names(self) -> list[str]:
        return sorted(self._skills.keys())

    def list_metadata(self) -> list[SkillMetadata]:
        return [skill.metadata for skill in self._skills.values()]

    def activate(self, name: str) -> None:
        """Load full instructions for a skill (progressive disclosure step 2)."""
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"Skill '{name}' is not registered")
        if skill.instructions is not None:
            return
        if skill.path is None:
            return
        _, instructions = parse_skill_md(skill.path / "SKILL.md")
        skill.instructions = instructions

    def discover(
        self,
        paths: list[Path] | None = None,
        use_entrypoints: bool = False,
    ) -> None:
        if paths:
            for skill in discover_from_paths(paths):
                self.register(skill)
        if use_entrypoints:
            for skill in discover_from_entrypoints():
                self.register(skill)
