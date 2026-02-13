# haiku.skills

A Python library for building skill-powered AI agents. Implements the [Agent Skills specification](https://agentskills.io/specification) and uses [pydantic-ai](https://ai.pydantic.dev/) for agent creation.

## Features

- **Skill discovery** — Scan filesystem paths for [SKILL.md](https://agentskills.io/specification) directories or load skills from Python entrypoints
- **Task decomposition** — Agents decompose requests into subtasks, spawn dynamic sub-agents with targeted skill subsets, and synthesize results
- **Progressive disclosure** — Lightweight metadata loaded at startup, full instructions loaded on activation
- **In-process tools** — Attach pydantic-ai `Tool` functions or `AbstractToolset` instances to skills
- **Script tools** — Python scripts in `scripts/` with a `main()` function, automatically discovered and executed via `uv run`

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

### Skills with tools

Skills can carry in-process tools that are passed to sub-agents:

```python
from haiku.skills import Skill, SkillMetadata, SkillSource, create_agent

def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    return str(eval(expression))

skill = Skill(
    metadata=SkillMetadata(
        name="calculator",
        description="Perform mathematical calculations.",
    ),
    source=SkillSource.ENTRYPOINT,
    instructions="Use the calculate tool to evaluate expressions.",
    tools=[calculate],
)

agent = create_agent(
    model="anthropic:claude-sonnet-4-5-20250929",
    skills=[skill],
)
```

For `FunctionToolset` or other `AbstractToolset` instances, use the `toolsets` parameter instead.

### Script tools

Skills can include executable Python scripts in a `scripts/` directory:

```
my-skill/
├── SKILL.md
└── scripts/
    └── analyze.py
```

Scripts must define a `main()` function with type-annotated parameters and a `__main__` block that reads JSON from stdin:

```python
"""Analyze data."""
import json
import sys

def main(data: str, operation: str = "describe") -> str:
    """Analyze the given data.

    Args:
        data: Input data to analyze.
        operation: Analysis operation to perform.
    """
    return f"Analyzed {len(data)} chars with {operation}"

if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    json.dump({"result": main(**args)}, sys.stdout)
```

Script tools are automatically discovered when a skill is activated and can use [PEP 723](https://peps.python.org/pep-0723/) inline dependencies.

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
