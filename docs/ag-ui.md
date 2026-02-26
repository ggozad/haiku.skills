# AG-UI protocol

haiku.skills supports the [AG-UI protocol](https://docs.ag-ui.com) for communicating state changes to frontend clients.

## Installation

```bash
uv add "haiku.skills[ag-ui]"
```

## Per-skill state

Skills can declare a Pydantic state model and a namespace. State is passed to tool functions via `RunContext[SkillRunDeps]` and tracked per namespace on the `SkillToolset`.

```python
from pydantic import BaseModel
from haiku.skills import Skill, SkillMetadata, SkillSource

class MyState(BaseModel):
    items: list[str] = []

skill = Skill(
    metadata=SkillMetadata(name="my-skill", description="..."),
    source=SkillSource.ENTRYPOINT,
    instructions="...",
    state_type=MyState,
    state_namespace="my-skill",
)
```

## State snapshots

The toolset provides methods for working with state:

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(skills=[skill])

# Get a snapshot of all namespaced state
toolset.build_state_snapshot()    # {"my-skill": {"items": []}}

# Restore from a snapshot
toolset.restore_state_snapshot({"my-skill": {"items": ["hello"]}})

# Get a specific namespace
toolset.get_namespace("my-skill") # MyState(items=["hello"])

# Schema information
toolset.state_schemas             # {"my-skill": <JSON schema>}
```

## State schemas

`state_schemas` returns the JSON Schema for each namespace, useful for building typed frontend components or validating state:

```python
toolset.state_schemas
# {
#     "my-skill": {
#         "properties": {
#             "items": {
#                 "default": [],
#                 "items": {"type": "string"},
#                 "title": "Items",
#                 "type": "array",
#             }
#         },
#         "title": "MyState",
#         "type": "object",
#     }
# }
```

Schemas are standard [JSON Schema](https://json-schema.org/) generated from the Pydantic state models. Nested models produce `$defs` references as usual.

!!! note
    The AG-UI protocol does not currently define a standard mechanism for communicating state schemas to clients. `state_schemas` is available on the Python side — how you expose it to frontends (e.g. a dedicated endpoint, initial metadata) is up to your application.

## State deltas

When `execute_skill` runs a skill whose tools modify state, the toolset computes a [JSON Patch](https://jsonpatch.com/) delta between the state before and after execution. This delta is returned as a `StateDeltaEvent`, compatible with the AG-UI protocol.

Frontends can apply these patches incrementally to keep their view of the agent's state in sync without polling or full state transfers.

## State round-tripping

When serving an agent via AG-UI (using `handle_ag_ui_request` or `AGUIAdapter`), the frontend sends state with each request. The adapter injects that state into `deps.state` if the deps object implements pydantic-ai's `StateHandler` protocol. `SkillToolset` then automatically restores per-namespace state from `deps.state` at the start of each run, closing the loop between frontend and backend.

haiku.skills provides `SkillDeps` — a minimal dataclass that satisfies pydantic-ai's `StateHandler` protocol with a `dict` state matching the namespace snapshot shape that `SkillToolset` expects:

```python
from pydantic_ai import Agent
from pydantic_ai.ag_ui import handle_ag_ui_request
from haiku.skills import SkillDeps, SkillToolset, build_system_prompt

toolset = SkillToolset(use_entrypoints=True)
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=build_system_prompt(toolset.skill_catalog),
    toolsets=[toolset],
    deps_type=SkillDeps,
)

# In your FastAPI route:
# return await handle_ag_ui_request(agent, request, deps=SkillDeps())
```

!!! note
    `SkillDeps` operates at the agent level — it carries the full AG-UI state dict (all namespaces) and is managed by the adapter. `SkillRunDeps`, on the other hand, is internal to `SkillToolset`: when a skill sub-agent runs, it receives `SkillRunDeps` containing only that skill's per-namespace state model. You don't need to create `SkillRunDeps` yourself.

!!! tip "Custom dependencies"
    If your agent needs additional dependencies beyond state, create your own dataclass with a `state: dict[str, Any]` field:

    ```python
    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class MyDeps:
        state: dict[str, Any] = field(default_factory=dict)
        db: MyDatabase = ...
    ```

    Any dataclass with a `state` attribute satisfies the `StateHandler` protocol.
