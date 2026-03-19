# Tutorial

This tutorial walks you through creating a skill from scratch, evolving it step by step from a simple filesystem skill to an entrypoint package with state, then covering MCP integration and mixing sources.

## Your first skill

A skill is a directory containing a `SKILL.md` file with YAML frontmatter and markdown instructions. Create a directory called `my-skill/` with a `SKILL.md` inside:

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

You help users analyze data. When asked to process data, describe
what you would do and provide a summary.
```

The frontmatter fields follow the [Agent Skills specification](https://agentskills.io/specification). The markdown body becomes the sub-agent's system prompt when the skill is executed.

Now wire it up with `SkillToolset`:

```python
from pathlib import Path
from pydantic_ai import Agent
from haiku.skills import SkillToolset, build_system_prompt

toolset = SkillToolset(
    skill_paths=[Path("./my-skill")],
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

`SkillToolset` discovers skills from the given paths and exposes a single `execute_skill` tool. `build_system_prompt` generates a system prompt listing the available skills. When the agent decides to use a skill, a focused sub-agent handles the request with that skill's instructions and tools.

`skill_paths` accepts both **parent directories** (all immediate subdirectories containing `SKILL.md` are discovered) and **skill directories** (directories that directly contain `SKILL.md`). The directory name must match the skill name in the frontmatter.

!!! note
    When a skill directory has validation errors (bad frontmatter, name mismatch, etc.), the error is collected and discovery continues with the remaining directories. The CLI prints these errors as warnings to stderr.

!!! tip "Customizing the system prompt"
    `build_system_prompt` accepts an optional `preamble` keyword argument to replace the default opening line (`"You are a helpful assistant with access to specialized skills."`):

    ```python
    instructions = build_system_prompt(
        toolset.skill_catalog,
        preamble="You are a data science assistant.",
    )
    ```

## Adding script tools

Filesystem skills automatically pick up **script tools** from a `scripts/` subdirectory and **resources** listed in the `resources` frontmatter field — no extra configuration needed.

Add a Python script with a `main()` function:

```
my-skill/
├── SKILL.md
└── scripts/
    └── analyze.py
```

**`scripts/analyze.py`:**

```python
# /// script
# dependencies = ["pandas"]
# ///
"""Analyze data."""

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
    import argparse

    parser = argparse.ArgumentParser(description="Analyze data.")
    parser.add_argument("--data", required=True, help="Input data to analyze.")
    parser.add_argument("--operation", default="describe", help="Analysis operation.")
    args = parser.parse_args()
    print(main(args.data, args.operation))
```

Script tools are automatically discovered when the skill loads — no configuration needed. Python scripts with a `main()` function get AST-parsed into typed pydantic-ai `Tool` objects. The `# /// script` block declares [PEP 723](https://peps.python.org/pep-0723/) inline dependencies, installed automatically via `uv run`.

Update the `SKILL.md` instructions to reference the new tool:

```markdown
---
name: my-skill
description: Helps with data analysis tasks.
---

# My Skill

You help users analyze data. Use the `analyze` script tool to process input.
```

See [Skills — Script tools](skills.md#script-tools) for the full resolution table, `run_script`, and `PYTHONPATH` details.

## Turning it into an entrypoint skill

Filesystem skills are great for quick iteration, but they require the consumer to know the path on disk. Entrypoint skills solve this — they're installed as Python packages and discovered automatically. This gives you:

- **In-process tools with state** — tool functions run in the same process and receive `RunContext[SkillRunDeps]`, so they can read and write per-skill state. Script tools run as subprocesses and have no access to state.
- **Zero-config discovery** — `SkillToolset(use_entrypoints=True)` finds every installed skill package. No paths to manage.
- **Versioning and distribution** — standard Python packaging (`pip install`, `uv add`) with dependency management.

The [example skills](example-skills.md) that ship with haiku.skills (web, gmail, code execution, etc.) are all entrypoint packages — they're good references for how to structure your own.

Create a package with a `pyproject.toml`:

**`pyproject.toml`:**

```toml
[project]
name = "my-skill-package"
version = "0.1.0"
dependencies = ["haiku.skills"]

[project.entry-points."haiku.skills"]
calculator = "my_skill_package:create_skill"
```

The entrypoint must point to a callable that returns a `Skill`:

**`my_skill_package/__init__.py`:**

```python
from haiku.skills import Skill, SkillMetadata, SkillSource

def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

def create_skill() -> Skill:
    return Skill(
        metadata=SkillMetadata(
            name="calculator",
            description="Perform mathematical calculations.",
        ),
        source=SkillSource.ENTRYPOINT,
        instructions="Use the add tool to add numbers.",
        tools=[add],
    )
```

Enable entrypoint discovery when creating a `SkillToolset`:

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(use_entrypoints=True)
```

The CLI also supports entrypoint discovery:

```bash
haiku-skills list --use-entrypoints
haiku-skills chat --use-entrypoints -m openai:gpt-4o
```

!!! note "Priority"
    Skills passed via `skills=` take priority over entrypoint-discovered skills. If a manually provided skill has the same name as an entrypoint skill, the entrypoint is silently skipped. This lets you override an entrypoint skill with a custom configuration.

## Adding state

Skills can declare a Pydantic state model that persists across tool calls. Extend the calculator entrypoint with state:

**`my_skill_package/__init__.py`:**

```python
from pydantic import BaseModel
from pydantic_ai import RunContext
from haiku.skills import Skill, SkillMetadata, SkillRunDeps, SkillSource

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

State is passed to tool functions via `RunContext[SkillRunDeps]` and tracked per namespace on the toolset:

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(skills=[create_skill()])

# State is accessible via the toolset
toolset.build_state_snapshot()    # {"calculator": {"history": []}}
```

Use `state_metadata()` to inspect a skill's state configuration without running it:

```python
meta = skill.state_metadata()
# StateMetadata(namespace="calculator", type=<class 'CalculatorState'>, schema={...})
```

When `execute_skill` runs a skill whose tools modify state, the toolset computes a JSON Patch delta and returns it as a `StateDeltaEvent` — compatible with the [AG-UI protocol](ag-ui.md). See [AG-UI protocol](ag-ui.md) for streaming details and state round-tripping.

## MCP skills

Any [MCP](https://modelcontextprotocol.io/) server can be wrapped as a skill using `skill_from_mcp`. The MCP server's tools are only visible to the sub-agent — the main agent only sees the `execute_skill` tool.

### Stdio servers

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

### SSE and streamable HTTP servers

```python
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP

# SSE
skill = skill_from_mcp(
    MCPServerSSE("http://localhost:8080/sse"),
    name="sse-skill",
    description="Tools via SSE.",
)

# Streamable HTTP
skill = skill_from_mcp(
    MCPServerStreamableHTTP("http://localhost:8080/mcp"),
    name="http-skill",
    description="Tools via streamable HTTP.",
)
```

### Using an MCP skill

```python
from pydantic_ai import Agent
from haiku.skills import SkillToolset, build_system_prompt

toolset = SkillToolset(skills=[skill])
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=build_system_prompt(toolset.skill_catalog),
    toolsets=[toolset],
)
```

## Mixing sources

Combine filesystem, entrypoint, and MCP skills in a single toolset:

```python
from pathlib import Path
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai import Agent
from haiku.skills import SkillToolset, build_system_prompt, skill_from_mcp

mcp_skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
)

toolset = SkillToolset(
    skill_paths=[Path("./skills")],   # Filesystem skills
    use_entrypoints=True,              # Entrypoint skills
    skills=[mcp_skill],                # MCP skills
    skill_model="openai:gpt-4o-mini",  # Model for skill sub-agents
)

agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=build_system_prompt(toolset.skill_catalog),
    toolsets=[toolset],
)
```

## Next steps

See [Example skills](example-skills.md) for the built-in skill packages (web, image generation, code execution, gmail, notifications) — each one demonstrates a different pattern and can be used as a reference implementation.
