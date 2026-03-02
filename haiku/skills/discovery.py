from importlib.metadata import entry_points
from pathlib import Path

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.script_tools import discover_script_tools


def _load_skill_from_directory(skill_dir: Path) -> Skill:
    """Load a single skill from a directory containing SKILL.md."""
    skill_md = skill_dir / "SKILL.md"
    metadata, instructions = parse_skill_md(skill_md)
    if metadata.name != skill_dir.name:
        raise ValueError(
            f"Skill name '{metadata.name}' does not match "
            f"directory name '{skill_dir.name}'"
        )
    return Skill(
        metadata=metadata,
        source=SkillSource.FILESYSTEM,
        path=skill_dir,
        instructions=instructions,
        tools=discover_script_tools(skill_dir),
        resources=discover_resources(skill_dir),
    )


def discover_from_paths(paths: list[Path]) -> list[Skill]:
    """Scan directories for subdirectories containing SKILL.md."""
    skills: list[Skill] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Skill path does not exist: {path}")
        if (path / "SKILL.md").exists():
            skills.append(_load_skill_from_directory(path))
            continue
        for child in sorted(path.iterdir()):
            if child.name.startswith("."):
                continue
            if not child.is_dir() or not (child / "SKILL.md").exists():
                continue
            skills.append(_load_skill_from_directory(child))
    return skills


def discover_resources(skill_path: Path) -> list[str]:
    """Scan skill directory for resource files, excluding implementation artifacts."""
    resources: list[str] = []
    for file in skill_path.rglob("*"):
        if not file.is_file():
            continue
        relative = file.relative_to(skill_path)
        if relative.name == "SKILL.md" and relative.parent == Path("."):
            continue
        if relative.parts[0] in ("scripts", "__pycache__"):
            continue
        if relative.suffix in (".py", ".pyc"):
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
