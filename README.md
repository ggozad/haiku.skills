# haiku.skills

[![Tests](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml/badge.svg)](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/ggozad/haiku.skills/graph/badge.svg)](https://codecov.io/gh/ggozad/haiku.skills)

Skill-powered AI agents implementing the [Agent Skills specification](https://agentskills.io/specification) with [pydantic-ai](https://ai.pydantic.dev/).

## How it works

`SkillToolset` is a pydantic-ai `FunctionToolset` that you attach to your own agent. It exposes a single `execute_skill` tool. When the agent calls it, a **focused sub-agent** spins up with only that skill's instructions and tools — then returns the result. The main agent never sees the skill's internal tools, so its tool space stays clean no matter how many skills you load.

This sub-agent architecture means each skill runs in isolation with its own system prompt, tools, and token budget. Skills don't interfere with each other, tool descriptions don't compete for attention, and failures in one skill can't confuse another.

## Features

- **Sub-agent execution** — Each skill runs in its own agent with dedicated instructions and tools
- **Skill discovery** — Scan filesystem paths for [SKILL.md](https://agentskills.io/specification) directories or load from Python entrypoints
- **Progressive disclosure** — Lightweight metadata at startup, full instructions loaded on activation
- **In-process tools** — Attach pydantic-ai `Tool` functions or `AbstractToolset` instances to skills
- **Script tools** — Python scripts in `scripts/` with a `main()` function, discovered and executed via `uv run`
- **MCP integration** — Wrap any MCP server (stdio, SSE, streamable HTTP) as a skill
- **Task tracking** — Observable task list on the toolset, populated during runs

## Installation

```bash
uv add haiku.skills
```

## Quick start

### Creating a skill

A skill is a directory containing a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: my-skill
description: Helps with data analysis tasks.
---

# My Skill

Instructions for the agent go here...
```

See the [Agent Skills specification](https://agentskills.io/specification) for the full format.

### Using SkillToolset

```python
from pathlib import Path
from pydantic_ai import Agent
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./skills")])
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=toolset.system_prompt,
    toolsets=[toolset],
)

result = await agent.run("Analyze this dataset.")
print(result.output)

# Task tracking — populated during runs
print(toolset.tasks)
toolset.clear_tasks()
```

### Skills with tools

```python
from haiku.skills import Skill, SkillMetadata, SkillSource, SkillToolset
from pydantic_ai import Agent

def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

skill = Skill(
    metadata=SkillMetadata(
        name="calculator",
        description="Perform mathematical calculations.",
    ),
    source=SkillSource.ENTRYPOINT,
    instructions="Use the add tool to add numbers.",
    tools=[add],
)

toolset = SkillToolset(skills=[skill])
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=toolset.system_prompt,
    toolsets=[toolset],
)
```

For `AbstractToolset` instances, use the `toolsets` parameter on `Skill` instead.

### Script tools

Skills can include executable Python scripts in a `scripts/` directory. Scripts must define a `main()` function with type-annotated parameters:

```python
"""Analyze data."""
import json, sys

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

Script tools are automatically discovered on skill activation and support [PEP 723](https://peps.python.org/pep-0723/) inline dependencies.

### MCP server skills

Any [MCP](https://modelcontextprotocol.io/) server can be wrapped as a skill:

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

SSE and streamable HTTP servers work the same way via `MCPServerSSE` and `MCPServerStreamableHTTP`.

### Entrypoint skills

Packages can expose skills via Python entrypoints:

```toml
[project.entry-points."haiku.skills"]
my-skill = "my_package.skills:create_my_skill"
```

```python
from haiku.skills import Skill, SkillMetadata, SkillSource

def create_my_skill() -> Skill:
    return Skill(
        metadata=SkillMetadata(name="my-skill", description="Data analysis."),
        source=SkillSource.ENTRYPOINT,
        instructions="# My Skill\n\nInstructions here...",
    )
```

### Using the registry directly

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./skills")])

print(toolset.registry.names)           # Available skill names
print(toolset.registry.list_metadata()) # Lightweight metadata

toolset.registry.activate("my-skill")   # Loads full instructions on demand
```

## Skill packages

Distributable skills under `skills/`:

- **[web](skills/web)** — Web search via [Brave Search API](https://brave.com/search/api/) and page content extraction via [trafilatura](https://trafilatura.readthedocs.io/) (requires `BRAVE_API_KEY` for search)
- **[image-generation](skills/image-generation)** — Image generation via [Ollama](https://ollama.com/)
- **[code-execution](skills/code-execution)** — Sandboxed Python execution via [pydantic-monty](https://github.com/pydantic/pydantic-monty)
- **[rag](skills/rag)** — Search, retrieve and analyze documents via [haiku.rag](https://github.com/ggozad/haiku.rag)

## CLI

### Listing skills

```bash
haiku-skills list --use-entrypoints
haiku-skills list -s ./skills
```

### Chat TUI

A debug/development chat interface is included:

```bash
uv add "haiku.skills[tui]"
```

Point it at a directory of skills for filesystem discovery:

```bash
haiku-skills chat -s ./skills -m openai:gpt-4o
```

Or use entrypoint discovery:

```bash
haiku-skills chat --use-entrypoints -m openai:gpt-4o
```

Filter to specific skills by name:

```bash
haiku-skills chat --use-entrypoints -k web -k code-execution -m openai:gpt-4o
```

## License

MIT
