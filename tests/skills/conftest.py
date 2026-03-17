import io
import runpy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic_ai import RunContext

from haiku.skills.state import SkillRunDeps

SKILLS_ROOT = Path(__file__).parent.parent.parent / "skills"


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "ignore_localhost": False,
        "filter_headers": ["authorization", "x-api-key", "x-subscription-token"],
        "decode_compressed_response": True,
    }


def make_ctx(state=None):
    """Create a mock RunContext with SkillRunDeps."""
    ctx = MagicMock(spec=RunContext)
    ctx.deps = SkillRunDeps(state=state)
    return ctx


def run_script(script_path: Path, argv: list[str]) -> str:
    """Run a script via runpy and capture stdout."""
    import sys

    captured = io.StringIO()
    old_argv = sys.argv
    old_stdout = sys.stdout
    try:
        sys.argv = argv
        sys.stdout = captured
        runpy.run_path(str(script_path), run_name="__main__")
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
    return captured.getvalue()
