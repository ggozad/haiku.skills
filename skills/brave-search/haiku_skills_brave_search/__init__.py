from pathlib import Path

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md


def create_skill() -> Skill:
    path = Path(__file__).parent
    metadata, _ = parse_skill_md(path / "SKILL.md")
    return Skill(metadata=metadata, source=SkillSource.ENTRYPOINT, path=path)
