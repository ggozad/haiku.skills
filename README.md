# haiku.skills

A Python library for building skill-powered AI agents. Implements the [Agent Skills specification](https://agentskills.io/specification) and uses [pydantic-ai](https://ai.pydantic.dev/) for agent creation.

## Features

- **Skill discovery** — Scan filesystem paths for [SKILL.md](https://agentskills.io/specification) directories or load skills from Python entrypoints
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

### Creating an agent

```python
from pathlib import Path
from haiku.skills import create_agent

agent = create_agent(
    model="anthropic:claude-sonnet-4-5-20250929",
    skill_paths=[Path("./skills")],
)

result = await agent.run("Analyze this dataset.")
print(result.answer)
```

`create_agent` discovers skills, builds a registry, and returns a `SkillAgent` that handles the full orchestration pipeline: decompose the request into subtasks, execute each with a targeted sub-agent, and synthesize the results.

### Entrypoint skills

Packages can expose skills via Python entrypoints in `pyproject.toml`:

```toml
[project.entry-points."haiku.skills"]
my-skill = "my_package.skills:create_my_skill"
```

Where the entry point is a callable returning a `Skill`:

```python
from haiku.skills import Skill, SkillMetadata, SkillSource

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

### Using the registry directly

```python
from haiku.skills import SkillRegistry

registry = SkillRegistry()
registry.discover(paths=[Path("./skills")])

print(registry.names)          # Available skill names
print(registry.list_metadata()) # Lightweight metadata for all skills

registry.activate("my-skill")  # Loads full instructions on demand
```

## License

MIT
