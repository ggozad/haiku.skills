# Lifespan

A skill's **lifespan** is an async context manager that wraps one skill invocation — i.e. one run of the sub-agent. Use it to allocate resources the skill's tools will share across tool calls and dispose of them cleanly when the invocation ends, including on exceptions.

Typical use cases:

- Open a database or API client once and reuse it across tool calls (avoid per-call connect/disconnect).
- Scope a per-invocation counter, cache, or sandbox to the run (prevents leaks across invocations).
- Acquire a lock, register a subscription, or start a background worker that must be torn down when the skill is done.

## Defining a lifespan

The lifespan is a factory — a callable that receives the skill's `deps` and returns an async context manager. Setup happens before `yield`; teardown in `finally` after. The yielded value is ignored by the framework; store per-invocation state on `deps` directly.

Pair a lifespan with `deps_type=` so tools get typed access:

```python
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from ag_ui.core import BaseEvent
from pydantic import BaseModel
from pydantic_ai import RunContext
from haiku.skills import Skill, SkillMetadata


@dataclass
class MyDeps:
    state: BaseModel | None = None
    emit: Callable[[BaseEvent], None] = field(default=lambda _: None)
    db: MyClient | None = None
    calls: int = 0


@asynccontextmanager
async def lifespan(deps: MyDeps):
    deps.db = await MyClient.connect(url="...")
    try:
        yield
    finally:
        await deps.db.close()


def search(ctx: RunContext[MyDeps], query: str) -> str:
    """Search the database."""
    assert ctx.deps.db is not None
    ctx.deps.calls += 1
    return ctx.deps.db.query(query)


skill = Skill(
    metadata=SkillMetadata(name="search", description="Searches the DB."),
    instructions="Use the search tool to answer questions.",
    tools=[search],
    deps_type=MyDeps,
    lifespan=lifespan,
)
```

Every call to the skill's sub-agent enters the CM once, runs the agent (which may call `search` multiple times — they all see the same `db` and the same `calls` counter), and exits the CM once. The next invocation gets a fresh `MyDeps` instance and a new `db`.

Any dataclass with `state` and `emit` satisfies `SkillRunDepsProtocol` — add whatever fields your lifespan and tools need.

## Without a custom deps class

A lifespan can do useful work without a custom deps class — for example, acquire a lock, emit events, or modify `deps.state`:

```python
@asynccontextmanager
async def lifespan(deps):
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()

skill = Skill(
    metadata=SkillMetadata(name="guarded", description="Takes a lock."),
    instructions="Do guarded work.",
    tools=[...],
    lifespan=lifespan,
)
```

## Exception handling

`async with` semantics are preserved: if any tool raises, the CM's `__aexit__` receives the exception and can clean up. The exception then propagates out of the skill run.

```python
@asynccontextmanager
async def lifespan(deps: MyDeps):
    conn = await pool.acquire()
    try:
        yield
    finally:
        await pool.release(conn)  # always runs, even on tool errors
```

## Per-invocation isolation

Every call to the skill constructs a fresh `deps` instance and enters a fresh CM. Two concurrent or sequential invocations of the same skill do not share state unless you deliberately capture something in the factory's closure.

## Scope

The lifespan fires in **sub-agent mode** (the default for `SkillToolset`), where `execute_skill` delegates each request to the skill's sub-agent. It does **not** fire in direct-tool mode (`SkillToolset(use_subagents=False)`), because that path exposes individual tools on the outer agent and has no well-defined invocation boundary. If you need per-call resources in direct mode, manage them inside the tool function.

!!! note
    `SkillToolset` emits a `UserWarning` at construction time if you register a skill with a `lifespan` while in direct-tool mode, so the silent no-op doesn't catch you off-guard.
