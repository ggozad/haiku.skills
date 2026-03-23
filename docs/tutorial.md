# Tutorial

This tutorial walks you through using and creating skills, progressing from loading an existing filesystem skill to building your own entrypoint package with state.

## Filesystem skills

A filesystem skill is a directory following the [Agent Skills specification](https://agentskills.io/specification). At minimum it contains a `SKILL.md` file:

```
my-skill/
├── SKILL.md
└── scripts/
    └── calculate.py
```

Anyone can create and share these — they're just folders. The [Agent Skills](https://agentskills.io/) site has a growing collection, and tools like Claude Code can use them directly.

### Loading a filesystem skill

Point `SkillToolset` at a directory containing skills:

```python
from pathlib import Path
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./skills")])
print(toolset.skill_catalog)
```

`skill_paths` accepts both **parent directories** (all subdirectories containing `SKILL.md` are discovered) and **skill directories** (directories that directly contain `SKILL.md`). The directory name must match the `name` field in the frontmatter.

Wire it into a pydantic-ai `Agent`:

```python
from pydantic_ai import Agent
from haiku.skills import build_system_prompt

toolset = SkillToolset(
    skill_paths=[Path("./skills")],
    skill_model="openai:gpt-4o-mini",   # model for skill sub-agents
)
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=build_system_prompt(toolset.skill_catalog),
    toolsets=[toolset],
)

result = await agent.run("Analyze this dataset.")
print(result.output)
```

`SkillToolset` exposes a single `execute_skill` tool. When the agent calls it, a focused sub-agent spins up with that skill's instructions and tools — then returns the result. The main agent never sees the skill's internal tools.

!!! note
    When a skill directory has validation errors (bad frontmatter, name mismatch, etc.), the error is collected and discovery continues. The CLI prints these as warnings to stderr.

!!! tip "Customizing the system prompt"
    `build_system_prompt` accepts a `preamble` keyword to replace the default opening line:

    ```python
    instructions = build_system_prompt(
        toolset.skill_catalog,
        preamble="You are a data science assistant.",
    )
    ```

### How scripts work

Filesystem skills can include executable scripts in a `scripts/` directory. The sub-agent doesn't have direct filesystem access — instead, it receives a `run_script` tool that executes scripts as subprocesses. Scripts should use `--flag value` arguments and support `--help`, following the [Agent Skills script conventions](https://agentskills.io/skill-creation/using-scripts).

The `run_script` tool resolves the right executor based on file extension:

| Extension | Executor |
|-----------|----------|
| `.py`     | Current Python interpreter |
| `.sh`     | `bash` |
| `.js`     | `node` |
| `.ts`     | `npx tsx` |
| Other     | Run as executable directly |

The skill directory is prepended to `PYTHONPATH`, so Python scripts can import sibling modules.

### Resources

Filesystem skills can also expose files (references, templates, data) as resources. Any non-script, non-Python file in the skill directory is automatically discovered. The sub-agent receives a `read_resource` tool to read these on demand.

### Creating a filesystem skill

Create a `SKILL.md` with YAML frontmatter and markdown instructions:

```markdown
---
name: my-skill
description: Helps with data analysis tasks.
---

# My Skill

You help users analyze data.

## Available Scripts

### `scripts/calculate.py`

Evaluate a math expression.

```
--expression    (required) A math expression like '2 + 3 * 4'.
```
```

Add a script with argparse:

```python
"""Evaluate math expressions."""

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate math.")
    parser.add_argument("--expression", required=True, help="Math expression.")
    args = parser.parse_args()
    print(eval(args.expression))
```

That's it — a spec-compliant skill anyone can use.

## Entrypoint skills

Filesystem skills are portable but limited: scripts run as subprocesses, there's no per-skill state, and dependency management is manual. **Entrypoint skills** are Python packages that provide typed tools running in-process:

- **Typed tools** — plain Python functions with type hints, not subprocess calls
- **Per-skill state** — tools receive `RunContext[SkillRunDeps]` and can read/write a Pydantic state model
- **Zero-config discovery** — `SkillToolset(use_entrypoints=True)` finds every installed skill package
- **Standard packaging** — `pip install` / `uv add` with proper dependency management

The [example skills](example-skills.md) that ship with haiku.skills are all entrypoint packages.

### Creating an entrypoint skill

Create a package with a `pyproject.toml` and an entrypoint:

```toml
[project]
name = "my-skill-package"
version = "0.1.0"
dependencies = ["haiku.skills"]

[project.entry-points."haiku.skills"]
calculator = "my_skill_package:create_skill"
```

The entrypoint must point to a callable that returns a `Skill`:

```python
from pathlib import Path

from haiku.skills import Skill
from haiku.skills.parser import parse_skill_md


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def create_skill() -> Skill:
    metadata, instructions = parse_skill_md(Path(__file__).parent / "SKILL.md")

    return Skill(
        metadata=metadata,
        instructions=instructions,
        tools=[add],
    )
```

Include a `SKILL.md` alongside `__init__.py` for metadata and instructions:

```markdown
---
name: calculator
description: Perform mathematical calculations.
---

# Calculator

Use the **add** tool to add numbers.
```

Enable entrypoint discovery:

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(use_entrypoints=True)
```

The CLI supports it too:

```bash
haiku-skills list --use-entrypoints
haiku-skills chat --use-entrypoints -m openai:gpt-4o
```

!!! note "Priority"
    Skills passed via `skills=` take priority over entrypoint-discovered skills with the same name. This lets you override an installed skill with a custom configuration.

### Adding state

Skills can declare a Pydantic state model that persists across tool calls within a session:

```python
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills import Skill, SkillRunDeps
from haiku.skills.parser import parse_skill_md


class CalculatorState(BaseModel):
    history: list[str] = []


def add(ctx: RunContext[SkillRunDeps], a: float, b: float) -> float:
    """Add two numbers."""
    result = a + b
    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, CalculatorState):
        ctx.deps.state.history.append(f"{a} + {b} = {result}")
    return result


def create_skill() -> Skill:
    metadata, instructions = parse_skill_md(Path(__file__).parent / "SKILL.md")

    return Skill(
        metadata=metadata,
        instructions=instructions,
        tools=[add],
        state_type=CalculatorState,
        state_namespace="calculator",
    )
```

State is tracked per namespace on the toolset:

```python
toolset = SkillToolset(skills=[create_skill()])
toolset.build_state_snapshot()    # {"calculator": {"history": []}}
```

When `execute_skill` runs a skill whose tools modify state, the toolset computes a JSON Patch delta and returns it as a `StateDeltaEvent` — compatible with the [AG-UI protocol](ag-ui.md).

## MCP skills

Any [MCP](https://modelcontextprotocol.io/) server can be wrapped as a skill using `skill_from_mcp`. The MCP server's tools become the sub-agent's tools — the main agent still only sees `execute_skill`.

```python
from pydantic_ai.mcp import MCPServerStdio
from haiku.skills import skill_from_mcp

skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
    instructions="Use these tools when the user asks about...",
    allowed_tools=["search", "fetch"],  # restrict which MCP tools are exposed
)
```

SSE and streamable HTTP servers work the same way:

```python
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP

skill = skill_from_mcp(
    MCPServerSSE("http://localhost:8080/sse"),
    name="sse-skill",
    description="Tools via SSE.",
)

skill = skill_from_mcp(
    MCPServerStreamableHTTP("http://localhost:8080/mcp"),
    name="http-skill",
    description="Tools via streamable HTTP.",
)
```

## Mixing sources

Combine filesystem, entrypoint, and MCP skills in a single toolset:

```python
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

from haiku.skills import SkillToolset, build_system_prompt, skill_from_mcp

mcp_skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
)

toolset = SkillToolset(
    skill_paths=[Path("./skills")],   # filesystem skills
    use_entrypoints=True,              # entrypoint skills
    skills=[mcp_skill],                # MCP skills
    skill_model="openai:gpt-4o-mini",
)

agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=build_system_prompt(toolset.skill_catalog),
    toolsets=[toolset],
)
```

## Next steps

- [Skills reference](skills.md) — SKILL.md format, tools, state, and script resolution
- [Example skills](example-skills.md) — Built-in skill packages as reference implementations
- [AG-UI protocol](ag-ui.md) — Streaming state deltas to web frontends
