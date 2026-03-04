from pathlib import Path

from haiku.skills.discovery import (
    discover_from_entrypoints,
    discover_from_paths,
)
from haiku.skills.models import Skill, SkillMetadata, SkillValidationError


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

    def discover(
        self,
        paths: list[Path] | None = None,
        use_entrypoints: bool = False,
    ) -> list[SkillValidationError]:
        errors: list[SkillValidationError] = []
        if paths:
            skills, path_errors = discover_from_paths(paths)
            errors.extend(path_errors)
            for skill in skills:
                self.register(skill)
        if use_entrypoints:
            for skill in discover_from_entrypoints():
                if skill.metadata.name not in self._skills:
                    self.register(skill)
        return errors
