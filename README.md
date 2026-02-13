# haiku.skills

A Python library for building skill-powered AI agents. Implements the [Agent Skills specification](https://agentskills.io/specification) and uses [pydantic-ai](https://ai.pydantic.dev/) for agent creation.

## Features

- **Skill discovery** — Scan filesystem paths for [SKILL.md](https://agentskills.io/specification) directories or load skills from Python entrypoints
- **MCP server integration** — Each MCP server maps to one skill
- **Task decomposition** — Agents decompose requests into subtasks, spawn dynamic sub-agents with targeted skill subsets, and synthesize results
- **Progressive disclosure** — Lightweight metadata loaded at startup, full instructions loaded on activation

## Installation

```bash
uv add haiku.skills
```

## Quick start

### Creating a skill

A skill is a directory containing a `SKILL.md` file with YAML frontmatter:

```
my-skill/
└── SKILL.md
```

```markdown
---
name: my-skill
description: Helps with data analysis tasks.
---

# My Skill

Instructions for the agent go here...
```

See the [Agent Skills specification](https://agentskills.io/specification) for the full format.

### Discovering skills

```python
from haiku.skills.registry import SkillRegistry

registry = SkillRegistry()

# Discover from filesystem paths
registry.discover(paths=[Path("./skills")])

# Or from Python entrypoints
registry.discover(use_entrypoints=True)

# List available skills
print(registry.names)

# Activate a skill (loads full instructions)
registry.activate("my-skill")
```

### Entrypoint skills

Packages can expose skills via Python entrypoints in `pyproject.toml`:

```toml
[project.entry-points."haiku.skills"]
my-skill = "my_package.skills:create_my_skill"
```

Where the entry point is a callable returning a `Skill`:

```python
from haiku.skills.models import Skill, SkillMetadata, SkillSource

def create_my_skill() -> Skill:
    return Skill(
        metadata=SkillMetadata(
            name="my-skill",
            description="Helps with data analysis tasks.",
        ),
        source=SkillSource.ENTRYPOINT,
        instructions="# My Skill\n\nInstructions here...",
    )
```

## License

MIT
