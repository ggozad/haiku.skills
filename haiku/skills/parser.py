from pathlib import Path

import yaml

from haiku.skills.models import SkillMetadata


def parse_skill_md(path: Path) -> tuple[SkillMetadata, str]:
    """Parse a SKILL.md file into metadata and instruction body."""
    content = path.read_text()

    if not content.startswith("---"):
        raise ValueError(f"SKILL.md at {path} is missing YAML frontmatter")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"SKILL.md at {path} is missing YAML frontmatter")

    frontmatter = yaml.safe_load(parts[1])
    if not isinstance(frontmatter, dict):
        raise ValueError(f"SKILL.md at {path} has invalid frontmatter")

    if "name" not in frontmatter:
        raise ValueError(f"SKILL.md at {path} is missing required field: name")
    if "description" not in frontmatter:
        raise ValueError(f"SKILL.md at {path} is missing required field: description")

    allowed_tools_raw = frontmatter.pop("allowed-tools", None)
    allowed_tools = allowed_tools_raw.split() if allowed_tools_raw else []

    metadata = SkillMetadata(
        allowed_tools=allowed_tools,
        **frontmatter,
    )

    body = parts[2].strip()
    return metadata, body
