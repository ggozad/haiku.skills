from unittest.mock import MagicMock

from pydantic_ai import RunContext
from pydantic_ai.models import Model

from haiku.skills.state import SkillRunDeps


def make_ctx(state=None, model: Model | None = None):
    """Create a mock RunContext with SkillRunDeps."""
    ctx = MagicMock(spec=RunContext)
    ctx.deps = SkillRunDeps(state=state)
    if model is not None:
        ctx.model = model
    return ctx
