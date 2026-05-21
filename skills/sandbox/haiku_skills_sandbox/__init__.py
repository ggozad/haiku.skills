import asyncio
import atexit
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from pydantic_ai_backends import ConsoleToolset, SessionManager
from pydantic_ai_backends.backends.docker import DockerSandbox

from haiku.skills.models import Skill
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps

IDLE_TIMEOUT_DEFAULT = 3600
IMAGE_DEFAULT = "haiku-skills-sandbox:latest"


def _default_idle_timeout() -> int:
    env = os.environ.get("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT")
    return int(env) if env else IDLE_TIMEOUT_DEFAULT


def _resolve_image() -> str:
    env = os.environ.get("HAIKU_SKILLS_SANDBOX_IMAGE")
    return env if env else IMAGE_DEFAULT


class SandboxState(BaseModel):
    session_id: str | None = None


_active_managers: list[SessionManager] = []


def _shutdown_all() -> None:
    for manager in _active_managers:
        try:
            asyncio.run(manager.shutdown())
        except Exception:
            pass
    _active_managers.clear()


atexit.register(_shutdown_all)


def create_skill(
    workspace: Path | None = None,
    idle_timeout: int | None = None,
    image: str | None = None,
) -> Skill:
    if workspace is None:
        env = os.environ.get("HAIKU_SKILLS_SANDBOX_WORKSPACE")
        if env:
            workspace = Path(env)

    image_name = image or _resolve_image()
    timeout = idle_timeout if idle_timeout is not None else _default_idle_timeout()
    volumes = {str(workspace): "/workspace"} if workspace else None

    def sandbox_factory(session_id: str) -> DockerSandbox:
        return DockerSandbox(
            image=image_name,
            session_id=session_id,
            volumes=volumes,
        )

    sessions = SessionManager(
        sandbox_factory=sandbox_factory,
        default_idle_timeout=timeout,
    )
    _active_managers.append(sessions)

    @dataclass
    class SandboxRunDeps(SkillRunDeps):
        backend: DockerSandbox | None = None

    @asynccontextmanager
    async def sandbox_lifespan(deps: SandboxRunDeps):
        state = deps.state if isinstance(deps.state, SandboxState) else None
        await sessions.cleanup_idle()
        session_id = state.session_id if state and state.session_id else str(uuid4())
        deps.backend = await sessions.get_or_create(session_id)
        if state:
            state.session_id = session_id
        yield

    metadata, instructions = parse_skill_md(Path(__file__).parent / "SKILL.md")
    return Skill(
        metadata=metadata,
        instructions=instructions,
        path=Path(__file__).parent,
        toolsets=[ConsoleToolset(require_execute_approval=False)],
        state_type=SandboxState,
        state_namespace="sandbox",
        deps_type=SandboxRunDeps,
        lifespan=sandbox_lifespan,
    )
