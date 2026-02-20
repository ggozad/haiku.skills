from dataclasses import dataclass, field
from typing import Any

import jsonpatch
from ag_ui.core import EventType, StateDeltaEvent
from pydantic import BaseModel


@dataclass
class SkillRunDeps:
    """Dependencies passed to skill sub-agent tools via RunContext."""

    state: BaseModel | None = None


@dataclass
class SkillDeps:
    """Agent-level dependencies for AG-UI state round-tripping.

    Satisfies pydantic-ai's ``StateHandler`` protocol with a ``dict``
    state, matching the namespace snapshot shape that ``SkillToolset``
    expects.
    """

    state: dict[str, Any] = field(default_factory=dict)


def compute_state_delta(
    old: dict[str, Any],
    new: dict[str, Any],
) -> StateDeltaEvent | None:
    """Compute a JSON Patch delta between old and new state snapshots.

    Args:
        old: Previous state snapshot (namespace -> serialized state).
        new: Current state snapshot (namespace -> serialized state).

    Returns:
        StateDeltaEvent if there are changes, None otherwise.
    """
    patch = jsonpatch.make_patch(old, new)
    if not patch.patch:
        return None
    return StateDeltaEvent(type=EventType.STATE_DELTA, delta=patch.patch)
