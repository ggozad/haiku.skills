# Skills

## SKILL.md format

Each skill is defined by a `SKILL.md` file following the [Agent Skills specification](https://agentskills.io/specification). The file uses YAML frontmatter for metadata and markdown for instructions:

```markdown
---
name: my-skill
description: A brief description of what the skill does.
---

# My Skill

Detailed instructions for the sub-agent go here. This content becomes
the system prompt when the skill is executed.
```

The frontmatter supports fields from the Agent Skills spec: `name`, `description`, `license`, `compatibility`, `metadata`, and `allowed-tools`. Unknown fields are rejected.

You can validate a skill directory against the spec with:

```bash
haiku-skills validate ./my-skill
```

## In-process tools

Skills can carry tool functions that run in the same process. These are plain Python callables or pydantic-ai `Tool` objects:

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

## Toolsets

For `AbstractToolset` instances (e.g. MCP toolsets), use the `toolsets` parameter instead of `tools`. See [Skill sources](skill-sources.md#mcp) for MCP integration details.

## Script tools

Skills can include executable scripts in a `scripts/` directory. Python scripts that define a `main()` function with type-annotated parameters get AST-parsed into typed tools:

```python
# /// script
# dependencies = ["pandas"]
# ///
"""Analyze data."""
import sys

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
    data = sys.argv[1]
    operation = sys.argv[2] if len(sys.argv) > 2 else "describe"
    print(main(data, operation))
```

Script tools are automatically discovered on skill loading. Scripts with a `main()` function get AST-parsed into typed pydantic-ai `Tool` objects with automatic parameter schema extraction. Scripts without `main()` are skipped (with a warning) during typed tool discovery.

Additionally, when a skill has a `scripts/` directory, the sub-agent receives a `run_script` tool that can execute any script (`.py`, `.sh`, `.js`, `.ts`, or generic executable) with free-form arguments. This allows the LLM to invoke scripts that don't follow the `main()` convention.

Typed script tools are executed via `uv run`, so [PEP 723](https://peps.python.org/pep-0723/) inline dependency metadata (the `# /// script` block above) is supported — dependencies are installed automatically.

### Script resolution

The `run_script` tool expects a relative path under `scripts/` (e.g. `scripts/extract.py`). Paths that escape the `scripts/` directory are rejected. The execution method depends on the file extension:

| Extension | Executor |
|-----------|----------|
| `.py`     | Current Python interpreter (`sys.executable`) |
| `.sh`     | `bash` |
| `.js`     | `node` |
| `.ts`     | `npx tsx` |
| Other     | Run as executable directly |

Both typed script tools and `run_script` prepend the skill directory to `PYTHONPATH`, so scripts can use package-style sibling imports:

```python
# scripts/utils.py
def helper():
    return "shared logic"

# scripts/main_script.py
from scripts.utils import helper
```

## Resources

Skills can expose files (references, assets, templates) as resources. Sub-agents can read them on demand via the `read_resource` tool with path validation and traversal defense.

## Per-skill state

Skills can declare a Pydantic state model. State is passed to tool functions via `RunContext[SkillRunDeps]` and tracked per namespace on the toolset:

```python
from pydantic import BaseModel
from pydantic_ai import RunContext
from haiku.skills import Skill, SkillMetadata, SkillSource, SkillToolset
from haiku.skills.state import SkillRunDeps

class CalculatorState(BaseModel):
    history: list[str] = []

def add(ctx: RunContext[SkillRunDeps], a: float, b: float) -> float:
    """Add two numbers."""
    result = a + b
    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, CalculatorState):
        ctx.deps.state.history.append(f"{a} + {b} = {result}")
    return result

skill = Skill(
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

toolset = SkillToolset(skills=[skill])

# State is accessible via the toolset
print(toolset.build_state_snapshot())  # {"calculator": {"history": []}}
```

When `execute_skill` runs a skill whose tools modify state, the toolset computes a JSON Patch delta and returns it as a `StateDeltaEvent` — compatible with the [AG-UI protocol](https://docs.ag-ui.com). See [AG-UI protocol](ag-ui.md) for details.
