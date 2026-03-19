from collections.abc import Sequence
from pathlib import Path

from haiku.skills.discovery import (
    discover_from_entrypoints,
    discover_from_paths,
)
from haiku.skills.models import Skill, SkillMetadata, SkillValidationError
from haiku.skills.signing import TrustedIdentity


class SkillRegistry:
    """Central registry for skill discovery, loading, and lookup."""

    def __init__(
        self,
        trusted_identities: Sequence[TrustedIdentity] | None = None,
    ) -> None:
        self._skills: dict[str, Skill] = {}
        self._trusted_identities = trusted_identities

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
        trusted_identities: Sequence[TrustedIdentity] | None = None,
    ) -> list[SkillValidationError]:
        errors: list[SkillValidationError] = []
        identities = trusted_identities or self._trusted_identities
        if paths:
            skills, path_errors = discover_from_paths(
                paths, trusted_identities=identities
            )
            errors.extend(path_errors)
            for skill in skills:
                self.register(skill)
        if use_entrypoints:
            for skill in discover_from_entrypoints():
                if skill.metadata.name not in self._skills:
                    self.register(skill)
        return errors
