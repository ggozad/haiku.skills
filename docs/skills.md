# Skills reference

## Two kinds of skills

haiku.skills supports two distinct skill types:

**Filesystem skills** are directories following the [Agent Skills specification](https://agentskills.io/specification). They contain a `SKILL.md` file and optional `scripts/`, `references/`, and `assets/` directories. Scripts are executed as subprocesses via the `run_script` tool (sub-agent mode) or `run_skill_script` tool (direct mode). Portable and shareable — no Python packaging required.

**Entrypoint skills** are Python packages that provide typed tools running in-process. They support per-skill state, standard dependency management, and zero-config discovery via Python entrypoints. All [example skills](example-skills.md) that ship with haiku.skills are entrypoint packages.

## SKILL.md format

Both skill types use a `SKILL.md` file for metadata and instructions, following the [Agent Skills specification](https://agentskills.io/specification). The file uses YAML frontmatter and markdown:

```markdown
---
name: my-skill
description: A brief description of what the skill does.
---

# My Skill

Detailed instructions go here. In sub-agent mode, this content becomes
the sub-agent's system prompt. In direct mode, it is returned by query_skill.
```

### Frontmatter fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Skill name (1-64 chars, lowercase alphanumeric + hyphens). Must match the directory name for filesystem skills. |
| `description` | string | yes | What the skill does (1-1024 chars). Shown to the main agent in the skill catalog. |
| `license` | string | no | License identifier (e.g. `"MIT"`, `"Apache-2.0"`). |
| `compatibility` | string | no | Compatibility notes (max 500 chars). |
| `metadata` | map | no | Arbitrary key-value pairs (`string: string`). |
| `allowed-tools` | list or string | no | Tool names the agent may use. Accepts a YAML list or a space-separated string (`"search fetch"`). |

Unknown fields are rejected.

### Signing

Skills can be signed with [sigstore](https://www.sigstore.dev/) for identity-based verification. See [Signing and verification](signing.md) for details.

Validate a skill directory against the spec:

```bash
haiku-skills validate ./my-skill
```

## Script tools (filesystem skills)

Filesystem skills can include executable scripts in a `scripts/` directory. In sub-agent mode, the sub-agent receives a `run_script` tool. In direct mode, the main agent uses `run_skill_script`. Both execute scripts as subprocesses.

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

## Reconfiguring entrypoint skills

Entrypoint skills discovered via `SkillToolset(use_entrypoints=True)` store their factory function. Call `reconfigure(**kwargs)` to re-invoke the factory with new arguments, replacing tools, state, and model while preserving metadata. This is useful when a skill's factory accepts optional parameters (e.g. config, database path) that the entry point loader doesn't pass:

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(use_entrypoints=True)
skill = toolset.registry.get("my-rag-skill")
skill.reconfigure(config=my_config, db_path=my_db_path)
```

`reconfigure()` re-invokes the factory with the given keyword arguments and replaces the skill's tools, state, and model in place. Metadata, instructions, and source are preserved — the skill keeps its identity in the registry.

This only works for entrypoint skills — filesystem and MCP skills have no factory and will raise `RuntimeError`.

## Per-skill model override (sub-agent mode)

In sub-agent mode, individual skills can specify their own model, overriding the `skill_model` set on `SkillToolset`:

```python
skill = Skill(
    metadata=SkillMetadata(name="heavy-reasoning", description="..."),
    instructions="...",
    tools=[...],
    model="openai:gpt-4o",  # this skill always uses gpt-4o
)
```

The resolution order is: skill `model` > `SkillToolset.skill_model` > pydantic-ai default.

In direct mode, skill tools run in the main agent's context, so these model overrides have no effect.

## Toolsets

For `AbstractToolset` instances (e.g. MCP toolsets), use the `toolsets` parameter instead of `tools`. See the [Tutorial — MCP skills](tutorial.md#mcp-skills) section for details.

## Resources

Skills automatically discover resource files — any non-script, non-Python file in the skill directory. For filesystem skills, resources are discovered during path scanning. For entrypoint skills, set `path` in the factory and resources are discovered automatically. In sub-agent mode, the sub-agent receives a `read_resource` tool; in direct mode, the main agent uses `read_skill_resource`.

- Resolved paths must stay within the skill directory (traversal defense).
- Files must be text — binary files raise an error.

## Extras

Skills can carry arbitrary non-tool data via `extras`. This is useful for exposing utility functions or other resources that the consuming app needs but that aren't agent tools:

```python
def calculate_calories(ingredient: str, grams: float) -> float:
    ...

skill = Skill(
    metadata=SkillMetadata(name="recipes", description="Recipe search."),
    instructions="...",
    tools=[...],
    extras={"calculate_calories": calculate_calories},
)
```

The app discovers skills via [entrypoints](tutorial.md#entrypoint-skills) and accesses extras by name:

```python
from haiku.skills.discovery import discover_from_entrypoints

skills = {s.metadata.name: s for s in discover_from_entrypoints()}
skill = skills["recipes"]
calories = skill.extras["calculate_calories"]("flour", 200)
```

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

When a skill's tools modify state, the toolset computes a JSON Patch delta and returns it as a `StateDeltaEvent` — compatible with the [AG-UI protocol](https://docs.ag-ui.com). This works in both sub-agent and direct mode. See [AG-UI protocol](ag-ui.md) for details.

### Introspecting state

Use `state_metadata()` to inspect a skill's state configuration without running it:

```python
meta = skill.state_metadata()
# StateMetadata(namespace="calculator", type=<class 'CalculatorState'>, schema={...})
```

Returns `None` for skills without state.

## Custom deps (advanced)

By default, skill sub-agents receive `SkillRunDeps` — a dataclass with `state` and `emit`. Skills that integrate external toolsets requiring additional context on the deps object can declare a `deps_type` — any class that satisfies `SkillRunDepsProtocol` (must have `state: BaseModel | None` and `emit: Callable`) and accepts `state` and `emit` as constructor arguments.

The simplest approach is to subclass `SkillRunDeps`:

```python
from dataclasses import dataclass, field

from haiku.skills import Skill, SkillMetadata, SkillRunDeps


@dataclass
class MyDeps(SkillRunDeps):                # inherits state + emit
    connection: object = field(init=False)

    def __post_init__(self):
        self.connection = open_connection()


skill = Skill(
    metadata=SkillMetadata(name="my-skill", description="Uses a custom connection."),
    instructions="...",
    toolsets=[my_external_toolset],
    deps_type=MyDeps,
)
```

Inheritance is not required — any class satisfying `SkillRunDepsProtocol` works, as long as its constructor accepts `state` and `emit` keyword arguments.

When `deps_type` is set, the skill sub-agent is created with `MyDeps(state=state, emit=emit)` instead of `SkillRunDeps(state=state, emit=emit)`. Any additional attributes are available to toolset tools via `ctx.deps`.
