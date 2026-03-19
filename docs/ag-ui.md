# AG-UI protocol

haiku.skills supports the [AG-UI protocol](https://docs.ag-ui.com) for communicating state changes to frontend clients.

Skills can declare per-namespace state models — see the [Tutorial](tutorial.md#adding-state) for a walkthrough and [Skills reference](skills.md#per-skill-state) for the full API.

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

## Real-time sub-agent events

When `execute_skill` delegates to a sub-agent, the sub-agent's internal tool calls (search, fetch, etc.) are emitted as `ActivitySnapshotEvent` messages with activity types `skill_tool_call` and `skill_tool_result`.

`run_agui_stream()` merges main-agent events with these activity events into a single real-time stream:

```python
from pydantic_ai.ag_ui import AGUIAdapter
from haiku.skills import SkillToolset, run_agui_stream

toolset = SkillToolset(skills=[skill])
agent = Agent(model, instructions=..., toolsets=[toolset])
adapter = AGUIAdapter(agent=agent, run_input=run_input)

async with run_agui_stream(toolset, adapter) as stream:
    async for event in stream:
        # Main-agent events (text, tool calls) and
        # sub-agent activity events arrive here in real-time
        ...
```

The `async with` context manager ensures proper cleanup of the background adapter task, even if the consumer exits early.

## Custom events

Skill tools can emit arbitrary AG-UI events (e.g. `CustomEvent` for progress reporting or domain-specific data) via the `emit` callback on `SkillRunDeps`:

```python
from ag_ui.core import CustomEvent
from pydantic_ai import RunContext
from haiku.skills import SkillRunDeps

def my_tool(ctx: RunContext[SkillRunDeps]) -> str:
    """A tool that emits progress events."""
    ctx.deps.emit(CustomEvent(name="progress", value={"step": 1, "total": 3}))
    # ... do work ...
    ctx.deps.emit(CustomEvent(name="progress", value={"step": 2, "total": 3}))
    return "done"
```

Any `BaseEvent` subclass can be emitted — not just `CustomEvent`. For example, a tool could emit a `StateDeltaEvent` directly.

When using `run_agui_stream()`, emitted events are flushed through the event sink at tool-call boundaries for near-real-time delivery. Without streaming (the batched path), they appear in `ToolReturn.metadata` alongside `ActivitySnapshotEvent` and `StateDeltaEvent`.

For HTTP endpoints, wrap the context manager inside an async generator:

```python
async def stream_chat(request):
    adapter = AGUIAdapter(agent=agent, run_input=run_input, accept=accept)

    async def event_stream():
        async with run_agui_stream(toolset, adapter, deps=SkillDeps()) as stream:
            async for chunk in adapter.encode_stream(stream):
                yield chunk

    return StreamingResponse(event_stream(), media_type=accept)
```

!!! note
    `adapter.run_stream()` still works without `run_agui_stream` — sub-agent activity events will arrive in batch via `ToolReturn.metadata` instead of streaming in real-time.

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
