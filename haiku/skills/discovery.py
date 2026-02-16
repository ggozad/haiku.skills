from importlib.metadata import entry_points
from pathlib import Path

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md


def discover_from_paths(paths: list[Path]) -> list[Skill]:
    """Scan directories for subdirectories containing SKILL.md."""
    skills: list[Skill] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Skill path does not exist: {path}")
        for child in sorted(path.iterdir()):
            skill_md = child / "SKILL.md"
            if not child.is_dir() or not skill_md.exists():
                continue
            metadata, _ = parse_skill_md(skill_md)
            if metadata.name != child.name:
                raise ValueError(
                    f"Skill name '{metadata.name}' does not match "
                    f"directory name '{child.name}'"
                )
            skills.append(
                Skill(
                    metadata=metadata,
                    source=SkillSource.FILESYSTEM,
                    path=child,
                )
            )
    return skills


def discover_resources(skill_path: Path) -> list[str]:
    """Scan skill directory for resource files, excluding SKILL.md and scripts/."""
    resources: list[str] = []
    for file in skill_path.rglob("*"):
        if not file.is_file():
            continue
        relative = file.relative_to(skill_path)
        if relative.name == "SKILL.md" and relative.parent == Path("."):
            continue
        if relative.parts[0] == "scripts":
            continue
        resources.append(str(relative))
    return sorted(resources)


def discover_from_entrypoints(group: str = "haiku.skills") -> list[Skill]:
    """Load skills from Python entrypoints."""
    skills: list[Skill] = []
    for ep in entry_points(group=group):
        factory = ep.load()
        skill = factory()
        skill.source = SkillSource.ENTRYPOINT
        skills.append(skill)
    return skills
