# Custom dependencies

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

See [Lifespan](lifespan.md) for a common pairing: a custom deps class whose fields are populated by a lifespan context manager.
