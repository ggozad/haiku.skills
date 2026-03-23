# Skills reference

## Two kinds of skills

haiku.skills supports two distinct skill types:

**Filesystem skills** are directories following the [Agent Skills specification](https://agentskills.io/specification). They contain a `SKILL.md` file and optional `scripts/`, `references/`, and `assets/` directories. The sub-agent gets a `run_script` tool to execute scripts as subprocesses. Portable and shareable — no Python packaging required.

**Entrypoint skills** are Python packages that provide typed tools running in-process. They support per-skill state, standard dependency management, and zero-config discovery via Python entrypoints. All [example skills](example-skills.md) that ship with haiku.skills are entrypoint packages.

## SKILL.md format

Both skill types use a `SKILL.md` file for metadata and instructions, following the [Agent Skills specification](https://agentskills.io/specification). The file uses YAML frontmatter and markdown:

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

### Signing

Skills can be signed with [sigstore](https://www.sigstore.dev/) for identity-based verification. See [Signing and verification](signing.md) for details.

Validate a skill directory against the spec:

```bash
haiku-skills validate ./my-skill
```

## Script tools (filesystem skills)

Filesystem skills can include executable scripts in a `scripts/` directory. The sub-agent receives a `run_script` tool that executes them as subprocesses — the sub-agent itself has no direct filesystem access.

Scripts should use named flags (`--flag value`) and support `--help`, following the [Agent Skills script conventions](https://agentskills.io/skill-creation/using-scripts).

### Script resolution

The `run_script` tool expects a relative path under `scripts/` (e.g. `scripts/extract.py`). Paths that escape the `scripts/` directory are rejected. The execution method depends on the file extension:

| Extension | Executor |
|-----------|----------|
| `.py`     | Current Python interpreter (`sys.executable`) |
| `.sh`     | `bash` |
| `.js`     | `node` |
| `.ts`     | `npx tsx` |
| Other     | Run as executable directly |

The skill directory is prepended to `PYTHONPATH`, so Python scripts can import sibling modules.

## In-process tools (entrypoint skills)

Entrypoint skills provide typed Python functions as tools. These run in the same process and can access per-skill state:

```python
from haiku.skills import Skill, SkillToolset, build_system_prompt
from pydantic_ai import Agent


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


skill = Skill(
    metadata=SkillMetadata(
        name="calculator",
        description="Perform mathematical calculations.",
    ),
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
    instructions="...",
    tools=[...],
    model="openai:gpt-4o",  # this skill always uses gpt-4o
)
```

The resolution order is: skill `model` > `SkillToolset.skill_model` > pydantic-ai default.

## Toolsets

For `AbstractToolset` instances (e.g. MCP toolsets), use the `toolsets` parameter instead of `tools`. See the [Tutorial — MCP skills](tutorial.md#mcp-skills) section for details.

## Resources

Filesystem skills automatically discover resource files — any non-script, non-Python file in the skill directory. The sub-agent receives a `read_resource` tool to read them on demand:

- Resolved paths must stay within the skill directory (traversal defense).
- Files must be text — binary files raise an error.

## Per-skill state

Entrypoint skills can declare a Pydantic state model. State is passed to tool functions via `RunContext[SkillRunDeps]` and tracked per namespace on the toolset:

```python
from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills import Skill, SkillMetadata, SkillRunDeps, SkillToolset


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
    instructions="Use the add tool to add numbers.",
    tools=[add],
    state_type=CalculatorState,
    state_namespace="calculator",
)

toolset = SkillToolset(skills=[skill])
print(toolset.build_state_snapshot())  # {"calculator": {"history": []}}
```

When `execute_skill` runs a skill whose tools modify state, the toolset computes a JSON Patch delta and returns it as a `StateDeltaEvent` — compatible with the [AG-UI protocol](https://docs.ag-ui.com). See [AG-UI protocol](ag-ui.md) for details.

### Introspecting state

Use `state_metadata()` to inspect a skill's state configuration without running it:

```python
meta = skill.state_metadata()
# StateMetadata(namespace="calculator", type=<class 'CalculatorState'>, schema={...})
```

Returns `None` for skills without state.
