import atexit
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from pydantic_ai_backends import ConsoleToolset
from pydantic_ai_backends.backends.docker import DockerSandbox

from haiku.skills.models import Skill
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps

_sandboxes: dict[str, DockerSandbox] = {}


def _cleanup_sandboxes() -> None:
    for sandbox in _sandboxes.values():
        try:
            sandbox.stop()
        except Exception:
            pass
    _sandboxes.clear()


atexit.register(_cleanup_sandboxes)


class SandboxState(BaseModel):
    session_id: str | None = None


def _get_sandbox(
    state: SandboxState | None, workspace: Path | None = None
) -> DockerSandbox:
    if state and state.session_id and state.session_id in _sandboxes:
        return _sandboxes[state.session_id]
    session_id = str(uuid4())
    volumes = {str(workspace): "/workspace"} if workspace else None
    sandbox = DockerSandbox(
        image="haiku-sandbox:latest",
        session_id=session_id,
        volumes=volumes,
    )
    _sandboxes[session_id] = sandbox
    if state:
        state.session_id = session_id
    return sandbox


def create_skill(workspace: Path | None = None) -> Skill:
    if workspace is None:
        env = os.environ.get("HAIKU_SANDBOX_WORKSPACE")
        if env:
            workspace = Path(env)

    from dataclasses import dataclass, field

    @dataclass
    class SandboxRunDeps(SkillRunDeps):
        backend: DockerSandbox = field(init=False)

        def __post_init__(self) -> None:
            state = self.state if isinstance(self.state, SandboxState) else None
            self.backend = _get_sandbox(state, workspace)

    metadata, instructions = parse_skill_md(Path(__file__).parent / "SKILL.md")
    return Skill(
        metadata=metadata,
        instructions=instructions,
        path=Path(__file__).parent,
        toolsets=[ConsoleToolset(require_execute_approval=False)],
        state_type=SandboxState,
        state_namespace="sandbox",
        deps_type=SandboxRunDeps,
    )
