"""Tests for the sandbox skill package."""

import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from haiku.skills.models import Skill
from haiku.skills.state import SkillRunDeps, SkillRunDepsProtocol


class StubSandbox:
    """Stub for DockerSandbox that exposes the SessionManager protocol."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self._alive = True
        self._last_activity = time.time()
        self.start_called = 0
        self.stop_called = 0

    def start(self) -> None:
        self.start_called += 1

    def stop(self) -> None:
        self.stop_called += 1
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive


def _make_factory(*sandboxes: StubSandbox):
    """Side_effect callable that returns each provided stub once, then raises."""
    iterator = iter(sandboxes)

    def factory(**kwargs: Any) -> StubSandbox:
        box = next(iterator)
        box.kwargs = kwargs
        return box

    return factory


async def _run_lifespan(skill: Skill, state: Any = None) -> Any:
    """Construct deps and drive the skill's lifespan, returning populated deps."""
    assert skill.deps_type is not None
    assert skill.lifespan is not None
    deps = skill.deps_type(state=state, emit=lambda _: None)
    async with skill.lifespan(deps):
        pass
    return deps


class TestCreateSkill:
    def test_create_skill(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill()
        assert skill.metadata.name == "sandbox"
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "sandbox"
        assert len(skill.toolsets) >= 1
        assert skill.deps_type is not None
        assert skill.lifespan is not None
        assert skill.path is not None

    def test_create_skill_with_workspace(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill(workspace=Path("/tmp/data"))
        assert skill.metadata.name == "sandbox"

    def test_deps_type_is_skill_run_deps_subclass(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill()
        assert skill.deps_type is not None
        assert issubclass(skill.deps_type, SkillRunDeps)

    async def test_workspace_from_env(self, monkeypatch):
        from haiku_skills_sandbox import SandboxState, create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_WORKSPACE", "/env/data")
        skill = create_skill()
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            await _run_lifespan(skill, state=state)

        assert stub.kwargs["volumes"] == {"/env/data": "/workspace"}

    async def test_explicit_workspace_overrides_env(self, monkeypatch):
        from haiku_skills_sandbox import SandboxState, create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_WORKSPACE", "/env/data")
        skill = create_skill(workspace=Path("/explicit"))
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            await _run_lifespan(skill, state=state)

        assert stub.kwargs["volumes"] == {"/explicit": "/workspace"}


class TestSandboxState:
    def test_default_session_id_is_none(self):
        from haiku_skills_sandbox import SandboxState

        state = SandboxState()
        assert state.session_id is None

    def test_session_id_settable(self):
        from haiku_skills_sandbox import SandboxState

        state = SandboxState(session_id="abc-123")
        assert state.session_id == "abc-123"


class TestSessionBinding:
    async def test_creates_new_sandbox_when_no_session(self):
        from haiku_skills_sandbox import SandboxState, create_skill

        skill = create_skill()
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            deps = await _run_lifespan(skill, state=state)

        assert state.session_id is not None
        assert deps.backend is stub
        assert stub.start_called == 1

    async def test_reuses_existing_sandbox(self):
        from haiku_skills_sandbox import SandboxState, create_skill

        skill = create_skill()
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            deps1 = await _run_lifespan(skill, state=state)
            deps2 = await _run_lifespan(skill, state=state)

        assert deps1.backend is deps2.backend
        # Only one DockerSandbox should have been constructed.
        assert stub.start_called == 1

    async def test_dead_sandbox_is_replaced(self):
        from haiku_skills_sandbox import SandboxState, create_skill

        skill = create_skill()
        state = SandboxState()
        old, new = StubSandbox(), StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox",
            side_effect=_make_factory(old, new),
        ):
            await _run_lifespan(skill, state=state)
            # Simulate container death.
            old._alive = False
            deps = await _run_lifespan(skill, state=state)

        assert deps.backend is new


class TestIdleCleanup:
    async def test_stale_sandbox_is_stopped_and_replaced(self):
        from haiku_skills_sandbox import SandboxState, create_skill

        skill = create_skill(idle_timeout=10)
        state = SandboxState()
        old, new = StubSandbox(), StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox",
            side_effect=_make_factory(old, new),
        ):
            await _run_lifespan(skill, state=state)
            # Force the old sandbox past its idle window.
            old._last_activity = time.time() - 9999
            deps = await _run_lifespan(skill, state=state)

        assert old.stop_called == 1
        assert deps.backend is new

    async def test_active_sandbox_is_reused(self):
        from haiku_skills_sandbox import SandboxState, create_skill

        skill = create_skill()
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            deps1 = await _run_lifespan(skill, state=state)
            deps2 = await _run_lifespan(skill, state=state)

        assert deps1.backend is deps2.backend
        assert stub.stop_called == 0

    def test_default_timeout_from_env(self, monkeypatch):
        import haiku_skills_sandbox

        assert (
            haiku_skills_sandbox._default_idle_timeout()
            == haiku_skills_sandbox.IDLE_TIMEOUT_DEFAULT
        )

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT", "120")
        assert haiku_skills_sandbox._default_idle_timeout() == 120

    async def test_per_skill_timeout_overrides_env(self, monkeypatch):
        from haiku_skills_sandbox import SandboxState, create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT", "9999")
        skill = create_skill(idle_timeout=10)
        state = SandboxState()
        old, new = StubSandbox(), StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox",
            side_effect=_make_factory(old, new),
        ):
            await _run_lifespan(skill, state=state)
            # Idle beyond per-skill timeout (10s) but within env (9999s).
            old._last_activity = time.time() - 20
            await _run_lifespan(skill, state=state)

        # Per-skill timeout wins.
        assert old.stop_called == 1


class TestImage:
    def test_default_image(self):
        from haiku_skills_sandbox import IMAGE_DEFAULT, _resolve_image

        assert _resolve_image() == IMAGE_DEFAULT

    def test_image_from_env(self, monkeypatch):
        from haiku_skills_sandbox import _resolve_image

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IMAGE", "custom:v1")
        assert _resolve_image() == "custom:v1"

    async def test_image_from_create_skill(self):
        from haiku_skills_sandbox import SandboxState, create_skill

        skill = create_skill(image="my-image:latest")
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            await _run_lifespan(skill, state=state)

        assert stub.kwargs["image"] == "my-image:latest"

    async def test_create_skill_image_overrides_env(self, monkeypatch):
        from haiku_skills_sandbox import SandboxState, create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IMAGE", "env-image:v1")
        skill = create_skill(image="explicit:v2")
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            await _run_lifespan(skill, state=state)

        assert stub.kwargs["image"] == "explicit:v2"


class TestShutdown:
    def test_create_skill_registers_manager(self):
        from haiku_skills_sandbox import _active_managers, create_skill

        before = len(_active_managers)
        create_skill()
        assert len(_active_managers) == before + 1

    def test_shutdown_all_releases_sessions(self):
        from haiku_skills_sandbox import _active_managers, _shutdown_all
        from pydantic_ai_backends import SessionManager

        stub = StubSandbox()
        manager = SessionManager(sandbox_factory=lambda _sid: stub)
        # Seed an active session without driving the lifespan (avoids running
        # an event loop, which would block _shutdown_all's asyncio.run()).
        manager._sessions["sid"] = stub
        _active_managers.append(manager)

        _shutdown_all()

        assert stub.stop_called == 1
        assert _active_managers == []

    def test_shutdown_ignores_errors(self):
        from haiku_skills_sandbox import _active_managers, _shutdown_all
        from pydantic_ai_backends import SessionManager

        class BrokenManager(SessionManager):
            async def shutdown(self) -> int:
                raise RuntimeError("boom")

        _active_managers.append(BrokenManager())
        _shutdown_all()  # must not raise
        assert _active_managers == []


class TestSandboxRunDeps:
    def test_satisfies_protocol(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill()
        assert skill.deps_type is not None

        deps = skill.deps_type(state=None, emit=lambda _: None)
        assert isinstance(deps, SkillRunDepsProtocol)
        assert deps.backend is None

    async def test_lifespan_populates_backend(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            deps = await _run_lifespan(skill)

        assert deps.backend is stub

    async def test_workspace_captured_in_closure(self):
        from haiku_skills_sandbox import SandboxState, create_skill

        skill = create_skill(workspace=Path("/my/data"))
        state = SandboxState()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            await _run_lifespan(skill, state=state)

        assert stub.kwargs["volumes"] == {"/my/data": "/workspace"}

    async def test_lifespan_without_state_does_not_raise(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill()
        stub = StubSandbox()

        with patch(
            "haiku_skills_sandbox.DockerSandbox", side_effect=_make_factory(stub)
        ):
            await _run_lifespan(skill)
