# haiku.skills

[![Tests](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml/badge.svg)](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/ggozad/haiku.skills/graph/badge.svg)](https://codecov.io/gh/ggozad/haiku.skills)

Skill-powered AI agents implementing the [Agent Skills specification](https://agentskills.io/specification) with [pydantic-ai](https://ai.pydantic.dev/).

## Features

- **Skill discovery** — Scan filesystem paths for [SKILL.md](https://agentskills.io/specification) directories or load from Python entrypoints
- **Skill execution** — Main agent delegates to focused sub-agents per skill, with task tracking via observable state
- **Progressive disclosure** — Lightweight metadata at startup, full instructions on activation
- **In-process tools** — Attach pydantic-ai `Tool` functions or `AbstractToolset` instances to skills
- **Script tools** — Python scripts in `scripts/` with a `main()` function, discovered and executed via `uv run`
- **MCP integration** — Wrap any MCP server (stdio, SSE, streamable HTTP) as a skill

## Installation

```bash
uv add haiku.skills
```

Individual skills are available as extras:

```bash
uv add "haiku.skills[brave-search,image-generation,code-execution]"
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

### Creating an agent

```python
from pathlib import Path
from haiku.skills import create_agent
from haiku.skills.models import AgentState

agent = create_agent(
    model="anthropic:claude-sonnet-4-5-20250929",
    skill_paths=[Path("./skills")],
)

state = AgentState()
answer = await agent.run("Analyze this dataset.", state)
```

The agent responds directly to simple messages or uses `execute_skill` to delegate to focused sub-agents when skills are needed.

`AgentState` is observable — poll it to track task progress.

### Conversation history

```python
await agent.run("Hello!")
await agent.run("What did I just say?")  # remembers prior messages

agent.clear_history()  # reset conversation
```

### Skills with tools

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

agent = create_agent(model="anthropic:claude-sonnet-4-5-20250929", skills=[skill])
```

For `AbstractToolset` instances, use the `toolsets` parameter instead.

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
from haiku.skills import create_agent, skill_from_mcp

skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
    instructions="Use these tools when the user asks about...",
)

agent = create_agent(model="anthropic:claude-sonnet-4-5-20250929", skills=[skill])
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
from haiku.skills import SkillRegistry

registry = SkillRegistry()
registry.discover(paths=[Path("./skills")])

print(registry.names)           # Available skill names
print(registry.list_metadata()) # Lightweight metadata

registry.activate("my-skill")   # Loads full instructions on demand
```

## Skill packages

Distributable skills under `skills/`:

- **[brave-search](skills/brave-search)** — Web search via [Brave Search API](https://brave.com/search/api/) (requires `BRAVE_API_KEY`)
- **[image-generation](skills/image-generation)** — Image generation via [Ollama](https://ollama.com/)
- **[code-execution](skills/code-execution)** — Sandboxed Python execution via [pydantic-monty](https://github.com/pydantic/pydantic-monty)

## Chat TUI

A debug/development chat interface is included:

```bash
uv add "haiku.skills[tui]"
```

Point it at a directory of skills for filesystem discovery:

```bash
haiku-skills chat -s ./skills -m openai:gpt-4o
```

Or install bundled skill packages and use entrypoint discovery:

```bash
uv add "haiku.skills[tui,brave-search,image-generation,code-execution]"
haiku-skills chat --use-entrypoints -m openai:gpt-4o
```

## License

MIT
