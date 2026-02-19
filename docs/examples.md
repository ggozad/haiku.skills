# Examples

## Filesystem skill

A complete skill directory with a `SKILL.md`, script tool, and resource file:

```
my-skill/
├── SKILL.md
├── scripts/
│   └── analyze.py
└── data/
    └── reference.txt
```

**`SKILL.md`:**

```markdown
---
name: my-skill
description: Analyze data using reference material.
resources:
  - data/reference.txt
---

# My Skill

You help users analyze data. Use the `analyze` script tool to process
input, and read the reference resource when you need context.
```

**`scripts/analyze.py`:**

```python
# /// script
# dependencies = ["pandas"]
# ///
"""Analyze data."""
import json, sys

import pandas as pd

def main(data: str, operation: str = "describe") -> str:
    """Analyze the given data.

    Args:
        data: Input data to analyze.
        operation: Analysis operation to perform.
    """
    df = pd.read_csv(pd.io.common.StringIO(data))
    if operation == "describe":
        return df.describe().to_string()
    return f"Analyzed {len(df)} rows"

if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    json.dump({"result": main(**args)}, sys.stdout)
```

**Usage:**

```python
from pathlib import Path
from pydantic_ai import Agent
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./my-skill")])
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=toolset.system_prompt,
    toolsets=[toolset],
)
```

## Entrypoint skill

A minimal package that registers a skill with tools and state via entrypoints.

**`pyproject.toml`:**

```toml
[project]
name = "my-skill-package"
version = "0.1.0"
dependencies = ["haiku.skills"]

[project.entry-points."haiku.skills"]
calculator = "my_skill_package:create_skill"
```

**`my_skill_package/__init__.py`:**

```python
from pydantic import BaseModel
from pydantic_ai import RunContext
from haiku.skills import Skill, SkillMetadata, SkillSource
from haiku.skills.state import SkillRunDeps

class CalculatorState(BaseModel):
    history: list[str] = []

def add(ctx: RunContext[SkillRunDeps], a: float, b: float) -> float:
    """Add two numbers."""
    result = a + b
    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, CalculatorState):
        ctx.deps.state.history.append(f"{a} + {b} = {result}")
    return result

def create_skill() -> Skill:
    return Skill(
        metadata=SkillMetadata(
            name="calculator",
            description="Perform mathematical calculations.",
        ),
        source=SkillSource.ENTRYPOINT,
        instructions="Use the add tool to add numbers.",
        tools=[add],
        state_type=CalculatorState,
        state_namespace="calculator",
    )
```

**Usage:**

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(use_entrypoints=True)
```

## MCP skill

Wrapping an existing MCP server as a skill:

```python
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai import Agent
from haiku.skills import SkillToolset, skill_from_mcp

skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
    instructions="Use these tools when the user asks about...",
)

toolset = SkillToolset(skills=[skill])
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=toolset.system_prompt,
    toolsets=[toolset],
)
```

## Built-in skill packages

haiku.skills includes distributable skill packages under `skills/`. Each is a standalone Python package that registers itself via entrypoints.

### web

Web search via [Brave Search API](https://brave.com/search/api/) and page content extraction via [trafilatura](https://trafilatura.readthedocs.io/).

```bash
uv add haiku-skills-web
```

Requires `BRAVE_API_KEY` environment variable for search functionality.

### image-generation

Image generation via [Ollama](https://ollama.com/).

```bash
uv add haiku-skills-image-generation
```

### code-execution

Sandboxed Python execution via [pydantic-monty](https://github.com/pydantic/pydantic-monty).

```bash
uv add haiku-skills-code-execution
```

For a more elaborate use case involving RAG (retrieval-augmented generation), see the [haiku.rag](https://github.com/ggozad/haiku.rag) project which provides a full RAG skill for haiku.skills.

## Mixing sources

Combine filesystem, entrypoint, and MCP skills in a single toolset:

```python
from pathlib import Path
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai import Agent
from haiku.skills import SkillToolset, skill_from_mcp

mcp_skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
)

toolset = SkillToolset(
    skill_paths=[Path("./skills")],   # Filesystem skills
    use_entrypoints=True,              # Entrypoint skills
    skills=[mcp_skill],                # MCP skills
)

agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=toolset.system_prompt,
    toolsets=[toolset],
)
```
