import atexit
import os
import time
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel
from pydantic_ai_backends import ConsoleToolset
from pydantic_ai_backends.backends.docker import DockerSandbox
from pydantic_ai_backends.types import EditResult, ExecuteResponse, WriteResult

from haiku.skills.models import Skill
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps

IDLE_TIMEOUT_DEFAULT = 3600
IMAGE_DEFAULT = "haiku-skills-sandbox:latest"

MAX_EXECUTIONS = 50
MAX_FILE_OPERATIONS = 50
MAX_OUTPUT_CHARS = 500

_sandboxes: dict[str, DockerSandbox] = {}
_last_active: dict[str, float] = {}
_timeouts: dict[str, int] = {}


def _default_idle_timeout() -> int:
    env = os.environ.get("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT")
    return int(env) if env else IDLE_TIMEOUT_DEFAULT


def _cleanup_stale() -> None:
    now = time.monotonic()
    default_timeout = _default_idle_timeout()
    stale = [
        sid
        for sid, t in _last_active.items()
        if now - t > _timeouts.get(sid, default_timeout)
    ]
    for sid in stale:
        sandbox = _sandboxes.pop(sid, None)
        _last_active.pop(sid, None)
        _timeouts.pop(sid, None)
        if sandbox:
            try:
                sandbox.stop()
            except Exception:
                pass


def _cleanup_sandboxes() -> None:
    for sandbox in _sandboxes.values():
        try:
            sandbox.stop()
        except Exception:
            pass
    _sandboxes.clear()
    _last_active.clear()
    _timeouts.clear()


atexit.register(_cleanup_sandboxes)


class Execution(BaseModel):
    command: str
    exit_code: int | None = None
    output: str = ""
    truncated: bool = False


class FileOperation(BaseModel):
    operation: Literal["read", "write", "edit"]
    path: str


class SandboxState(BaseModel):
    session_id: str | None = None
    executions: list[Execution] = []
    file_operations: list[FileOperation] = []


class InstrumentedSandbox:
    """Wraps a sandbox backend to record executions and file operations in state."""

    def __init__(self, backend: DockerSandbox, state: SandboxState) -> None:
        self._backend = backend
        self._state = state

    @property
    def id(self) -> str:
        return self._backend.id

    @property
    def session_id(self) -> str:
        return self._backend.session_id

    def execute(self, command: str, timeout: int | None = None) -> ExecuteResponse:
        result = self._backend.execute(command, timeout)
        self._state.executions.append(
            Execution(
                command=command,
                exit_code=result.exit_code,
                output=result.output[:MAX_OUTPUT_CHARS],
                truncated=result.truncated,
            )
        )
        if len(self._state.executions) > MAX_EXECUTIONS:
            self._state.executions = self._state.executions[-MAX_EXECUTIONS:]
        return result

    def read(self, path: str, offset: int = 0, limit: int = 2000) -> str:
        result = self._backend.read(path, offset=offset, limit=limit)
        self._state.file_operations.append(FileOperation(operation="read", path=path))
        self._trim_file_operations()
        return result

    def write(self, path: str, content: str | bytes) -> WriteResult:
        result = self._backend.write(path, content)
        if result.error is None:
            self._state.file_operations.append(
                FileOperation(operation="write", path=path)
            )
            self._trim_file_operations()
        return result

    def edit(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = self._backend.edit(
            path, old_string, new_string, replace_all=replace_all
        )
        if result.error is None:
            self._state.file_operations.append(
                FileOperation(operation="edit", path=path)
            )
            self._trim_file_operations()
        return result

    def _trim_file_operations(self) -> None:
        if len(self._state.file_operations) > MAX_FILE_OPERATIONS:
            self._state.file_operations = self._state.file_operations[
                -MAX_FILE_OPERATIONS:
            ]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)


def _resolve_image() -> str:
    env = os.environ.get("HAIKU_SKILLS_SANDBOX_IMAGE")
    return env if env else IMAGE_DEFAULT


def _get_sandbox(
    state: SandboxState | None,
    workspace: Path | None = None,
    image: str | None = None,
    idle_timeout: int | None = None,
) -> DockerSandbox:
    _cleanup_stale()

    if state and state.session_id and state.session_id in _sandboxes:
        _last_active[state.session_id] = time.monotonic()
        return _sandboxes[state.session_id]

    session_id = str(uuid4())
    volumes = {str(workspace): "/workspace"} if workspace else None
    sandbox = DockerSandbox(
        image=image or _resolve_image(),
        session_id=session_id,
        volumes=volumes,
    )
    _sandboxes[session_id] = sandbox
    _last_active[session_id] = time.monotonic()
    if idle_timeout is not None:
        _timeouts[session_id] = idle_timeout
    if state:
        state.session_id = session_id
    return sandbox


def create_skill(
    workspace: Path | None = None,
    idle_timeout: int | None = None,
    image: str | None = None,
) -> Skill:
    if workspace is None:
        env = os.environ.get("HAIKU_SKILLS_SANDBOX_WORKSPACE")
        if env:
            workspace = Path(env)

    from dataclasses import dataclass, field

    @dataclass
    class SandboxRunDeps(SkillRunDeps):
        backend: DockerSandbox | InstrumentedSandbox = field(init=False)

        def __post_init__(self) -> None:
            state = self.state if isinstance(self.state, SandboxState) else None
            raw_backend = _get_sandbox(state, workspace, image, idle_timeout)
            if state is not None:
                self.backend = InstrumentedSandbox(raw_backend, state)
            else:
                self.backend = raw_backend

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
