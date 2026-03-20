# Skills reference

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

### Frontmatter fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Skill name (1-64 chars, lowercase alphanumeric + hyphens). Must match the directory name for filesystem skills. |
| `description` | string | yes | What the skill does (1-1024 chars). Shown to the main agent in the skill catalog. |
| `license` | string | no | License identifier (e.g. `"MIT"`, `"Apache-2.0"`). |
| `compatibility` | string | no | Compatibility notes (max 500 chars). |
| `metadata` | map | no | Arbitrary key-value pairs (`string: string`). |
| `allowed-tools` | list or string | no | Tool names the sub-agent may use. Accepts a YAML list or a space-separated string (`"search fetch"`). |

Unknown fields are rejected.

!!! note
    `resources` is also parsed from the frontmatter but stored on the `Skill` model (not `SkillMetadata`). It accepts a list of relative paths to files the sub-agent can read via the `read_resource` tool. See [Resources](#resources) for details.

### Signing

Skills can be signed with [sigstore](https://www.sigstore.dev/) for identity-based verification. See [Signing and verification](signing.md) for the full guide.

You can validate a skill directory against the spec with:

```bash
haiku-skills validate ./my-skill
```

## In-process tools

Skills can carry tool functions that run in the same process. These are plain Python callables or pydantic-ai `Tool` objects:

```python
from haiku.skills import Skill, SkillMetadata, SkillSource, SkillToolset, build_system_prompt
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
    instructions=build_system_prompt(toolset.skill_catalog),
    toolsets=[toolset],
)
```

## Per-skill model override

Individual skills can specify their own model, overriding the `skill_model` set on `SkillToolset`:

```python
skill = Skill(
    metadata=SkillMetadata(name="heavy-reasoning", description="..."),
    source=SkillSource.ENTRYPOINT,
    instructions="...",
    tools=[...],
    model="openai:gpt-4o",  # this skill always uses gpt-4o
)
```

The `model` field accepts a model string, a pydantic-ai `Model` instance, or `None` (use the toolset default). The resolution order is: skill `model` > `SkillToolset.skill_model` > pydantic-ai default.

## Toolsets

For `AbstractToolset` instances (e.g. MCP toolsets), use the `toolsets` parameter instead of `tools`. See the [Tutorial — MCP skills](tutorial.md#mcp-skills) section for MCP integration details.

## Script tools

Skills can include executable scripts in a `scripts/` directory. Python scripts that define a `main()` function with type-annotated parameters get AST-parsed into typed tools:

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

Skills can expose files (references, assets, templates) as resources. Declare them in the `resources` frontmatter field:

```markdown
---
name: my-skill
description: Analyze data using reference material.
resources:
  - data/reference.txt
  - data/schema.json
---
```

When a skill has resources, the sub-agent receives a `read_resource` tool that reads them on demand:

- Only paths listed in `resources` are accessible — the tool rejects anything else.
- Resolved paths must stay within the skill directory (traversal defense).
- Files must be text — binary files raise an error.

## Per-skill state

Skills can declare a Pydantic state model. State is passed to tool functions via `RunContext[SkillRunDeps]` and tracked per namespace on the toolset:

```python
from pydantic import BaseModel
from pydantic_ai import RunContext
from haiku.skills import Skill, SkillMetadata, SkillRunDeps, SkillSource, SkillToolset

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

### Introspecting state

Use `state_metadata()` to inspect a skill's state configuration without running it:

```python
meta = skill.state_metadata()
# StateMetadata(namespace="calculator", type=<class 'CalculatorState'>, schema={...})
```

Returns `None` for skills without state. The `schema` attribute contains the JSON Schema from `model_json_schema()`.
