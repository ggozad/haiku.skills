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

Now load it with `SkillToolset` to verify discovery works — no API key needed:

```python
from pathlib import Path
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./my-skill")])
print(toolset.skill_catalog)
# {'my-skill': 'Helps with data analysis tasks.'}
```

`SkillToolset` discovers skills from the given paths and exposes a single `execute_skill` tool. `build_system_prompt` generates a system prompt listing the available skills. When the agent decides to use a skill, a focused sub-agent handles the request with that skill's instructions and tools.

Wire it into a pydantic-ai `Agent` to run it:

```python
from pydantic_ai import Agent
from haiku.skills import build_system_prompt

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

`skill_paths` accepts both **parent directories** (all immediate subdirectories containing `SKILL.md` are discovered) and **skill directories** (directories that directly contain `SKILL.md`). The directory name must match the skill name in the frontmatter.

!!! note
    When a skill directory has validation errors (bad frontmatter, name mismatch, etc.), the error is collected and discovery continues with the remaining directories. Non-existent paths are also collected as errors rather than aborting. The CLI prints these errors as warnings to stderr.

!!! tip "Customizing the system prompt"
    `build_system_prompt` accepts an optional `preamble` keyword argument to replace the default opening line (`"You are a helpful assistant with access to specialized skills."`):

    ```python
    instructions = build_system_prompt(
        toolset.skill_catalog,
        preamble="You are a data science assistant.",
    )
    ```

## Adding script tools

Filesystem skills automatically pick up **script tools** from a `scripts/` subdirectory. Add a Python script with a `main()` function:

```
my-skill/
├── SKILL.md
└── scripts/
    └── calculate.py
```

**`scripts/calculate.py`:**

```python
"""Perform basic arithmetic."""

def main(expression: str) -> str:
    """Evaluate a math expression.

    Args:
        expression: A math expression like '2 + 3 * 4'.
    """
    result = eval(expression)  # noqa: S307
    return str(result)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate math.")
    parser.add_argument("--expression", required=True, help="Math expression.")
    args = parser.parse_args()
    print(main(args.expression))
```

Python scripts with a `main()` function get AST-parsed into typed pydantic-ai `Tool` objects automatically — no configuration needed. The `__main__` block with argparse lets the script also run standalone (`python calculate.py --expression '1+1'`).

Update the `SKILL.md` instructions to reference the new tool:

```markdown
---
name: my-skill
description: Helps with data analysis tasks.
---

# My Skill

You help users analyze data. Use the `calculate` script tool for arithmetic.
```

!!! tip "Script dependencies"
    Scripts that need external packages can declare [PEP 723](https://peps.python.org/pep-0723/) inline dependencies, installed automatically via `uv run`:

    ```python
    # /// script
    # dependencies = ["pandas"]
    # ///
    ```

See [Skills — Script tools](skills.md#script-tools) for the full resolution table, `run_script`, and `PYTHONPATH` details.

## Adding resources

Skills can expose files for the sub-agent to read on demand. Add a reference file and declare it in the frontmatter:

```
my-skill/
├── SKILL.md
├── scripts/
│   └── calculate.py
└── data/
    └── formulas.txt
```

```markdown
---
name: my-skill
description: Helps with data analysis tasks.
resources:
  - data/formulas.txt
---

# My Skill

You help users analyze data. Use the `calculate` script tool for arithmetic.
Read `data/formulas.txt` with the `read_resource` tool when you need reference formulas.
```

The sub-agent receives a `read_resource` tool that can read any file listed in `resources`. Only declared paths are accessible — other paths are rejected. See [Skills — Resources](skills.md#resources) for details.

## Turning it into an entrypoint skill

Filesystem skills are great for quick iteration, but they're limited to script tools (run as subprocesses) and have no access to per-skill state or AG-UI events. Entrypoint skills unlock the full feature set:

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
    Skills passed via `skills=` take priority over entrypoint-discovered skills. If a manually provided skill has the same name as an entrypoint skill, the entrypoint is silently skipped. This lets you override an entrypoint skill with a custom configuration — for example, passing custom parameters to a factory:

    ```python
    custom_skill = create_my_skill(db_path="/custom/path")
    toolset = SkillToolset(skills=[custom_skill], use_entrypoints=True)
    ```

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
    # Guard: deps and state are only populated when run via SkillToolset
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

When `execute_skill` runs a skill whose tools modify state, the toolset computes a JSON Patch delta and returns it as a `StateDeltaEvent` — compatible with the [AG-UI protocol](ag-ui.md). If you're building a web frontend, see [AG-UI protocol](ag-ui.md) for how to stream state deltas to clients, round-trip state across requests, and emit custom events from skill tools.

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
