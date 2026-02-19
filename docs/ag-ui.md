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
