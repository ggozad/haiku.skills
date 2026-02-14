# haiku.skills

A Python library for building skill-powered AI agents. Implements the [Agent Skills specification](https://agentskills.io/specification) and uses [pydantic-ai](https://ai.pydantic.dev/) for agent creation.

## Features

- **Conversational agent** — Chat directly or delegate to the skill orchestrator when specialized skills are needed
- **Skill discovery** — Scan filesystem paths for [SKILL.md](https://agentskills.io/specification) directories or load skills from Python entrypoints
- **Task decomposition** — The orchestrator decomposes requests into subtasks, spawns dynamic sub-agents with targeted skill subsets, and synthesizes results
- **Progressive disclosure** — Lightweight metadata loaded at startup, full instructions loaded on activation
- **In-process tools** — Attach pydantic-ai `Tool` functions or `AbstractToolset` instances to skills
- **Script tools** — Python scripts in `scripts/` with a `main()` function, automatically discovered and executed via `uv run`
- **MCP integration** — Wrap any MCP server (stdio, SSE, streamable HTTP) as a skill with `skill_from_mcp()`
- **Chat TUI** — Interactive terminal UI powered by [Textual](https://textual.textualize.io/)

## Installation

```bash
uv add haiku.skills
```

For the chat TUI:

```bash
uv add "haiku.skills[tui]"
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
from haiku.skills.models import OrchestratorState

agent = create_agent(
    model="anthropic:claude-sonnet-4-5-20250929",
    skill_paths=[Path("./skills")],
)

state = OrchestratorState()
answer = await agent.run("Analyze this dataset.", state)
print(answer)
```

`create_agent` discovers skills, builds a registry, and returns a `SkillAgent`. The agent can respond directly to simple messages or delegate to the orchestrator when skills are needed. The orchestrator decomposes the request into subtasks, executes each with a targeted sub-agent, and synthesizes the results.

The `OrchestratorState` object is observable — you can poll it to track the orchestrator's phase and task progress.

### Conversation history

The agent maintains conversation history across calls:

```python
state = OrchestratorState()
await agent.run("Hello!", state)
await agent.run("What did I just say?", state)  # remembers prior messages

agent.clear_history()  # reset conversation
```

### Chat TUI

Launch the interactive chat interface:

```bash
haiku-skills chat -s ./skills
```

Options:

| Flag | Description |
|---|---|
| `-m`, `--model` | Model to use (e.g. `openai:gpt-4o`) |
| `-s`, `--skill-path` | Path to directory containing skill subdirectories (repeatable) |
| `--use-entrypoints` | Discover skills from Python entrypoints |

Environment variables (or `.env` file):

| Variable | Description | Default |
|---|---|---|
| `HAIKU_SKILLS_MODEL` | Model to use | `ollama:gpt-oss` |
| `HAIKU_SKILLS_PATHS` | Colon-separated skill paths | — |
| `HAIKU_SKILLS_USE_ENTRYPOINTS` | Enable entrypoint discovery (`1`/`true`/`yes`) | — |
| `LOGFIRE_TOKEN` | [Pydantic Logfire](https://logfire.pydantic.dev/) token for tracing | — |

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

### MCP server skills

Any [MCP](https://modelcontextprotocol.io/) server can be wrapped as a skill using `skill_from_mcp()`:

```python
from pydantic_ai.mcp import MCPServerStdio
from haiku.skills import create_agent, skill_from_mcp

server = MCPServerStdio("uvx", args=["my-mcp-server"])
skill = skill_from_mcp(
    server,
    name="my-mcp-skill",
    description="Tools from my MCP server.",
    instructions="Use these tools when the user asks about...",
)

agent = create_agent(
    model="anthropic:claude-sonnet-4-5-20250929",
    skills=[skill],
)
```

SSE and streamable HTTP servers work the same way:

```python
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP

sse_skill = skill_from_mcp(
    MCPServerSSE("http://localhost:8000/sse"),
    name="sse-skill",
    description="Tools via SSE.",
)

http_skill = skill_from_mcp(
    MCPServerStreamableHTTP("http://localhost:8000/mcp"),
    name="http-skill",
    description="Tools via streamable HTTP.",
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
