"""Tests for the sandbox skill package."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from haiku.skills.state import SkillRunDeps, SkillRunDepsProtocol


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

    def test_workspace_from_env(self, monkeypatch):
        from haiku_skills_sandbox import SandboxState, _sandboxes, create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_WORKSPACE", "/env/data")
        _sandboxes.clear()
        skill = create_skill()
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            skill.deps_type(state=state, emit=lambda _: None)

        call_kwargs = MockSandbox.call_args[1]
        assert call_kwargs["volumes"] == {"/env/data": "/workspace"}

    def test_explicit_workspace_overrides_env(self, monkeypatch):
        from haiku_skills_sandbox import SandboxState, _sandboxes, create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_WORKSPACE", "/env/data")
        _sandboxes.clear()
        skill = create_skill(workspace=Path("/explicit"))
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            skill.deps_type(state=state, emit=lambda _: None)

        call_kwargs = MockSandbox.call_args[1]
        assert call_kwargs["volumes"] == {"/explicit": "/workspace"}


class TestSandboxState:
    def test_default_session_id_is_none(self):
        from haiku_skills_sandbox import SandboxState

        state = SandboxState()
        assert state.session_id is None

    def test_session_id_settable(self):
        from haiku_skills_sandbox import SandboxState

        state = SandboxState(session_id="abc-123")
        assert state.session_id == "abc-123"


class TestGetSandbox:
    def test_creates_new_sandbox_when_no_session(self):
        from haiku_skills_sandbox import SandboxState, _get_sandbox, _sandboxes

        _sandboxes.clear()
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            result = _get_sandbox(state)

        assert result is mock_instance
        assert state.session_id is not None
        assert state.session_id in _sandboxes
        assert _sandboxes[state.session_id] is mock_instance

    def test_reuses_existing_sandbox_when_session_in_cache(self):
        from haiku_skills_sandbox import SandboxState, _get_sandbox, _sandboxes

        _sandboxes.clear()
        mock_sandbox = MagicMock()
        _sandboxes["existing-id"] = mock_sandbox
        state = SandboxState(session_id="existing-id")

        result = _get_sandbox(state)
        assert result is mock_sandbox

    def test_creates_new_sandbox_on_cache_miss(self):
        from haiku_skills_sandbox import SandboxState, _get_sandbox, _sandboxes

        _sandboxes.clear()
        state = SandboxState(session_id="stale-id")

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            result = _get_sandbox(state)

        assert result is mock_instance
        assert state.session_id != "stale-id"
        assert state.session_id in _sandboxes

    def test_works_with_none_state(self):
        from haiku_skills_sandbox import _get_sandbox, _sandboxes

        _sandboxes.clear()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            result = _get_sandbox(None)

        assert result is mock_instance

    def test_passes_workspace_as_volume(self):
        from haiku_skills_sandbox import SandboxState, _get_sandbox, _sandboxes

        _sandboxes.clear()
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            _get_sandbox(state, workspace=Path("/data/files"))

        MockSandbox.assert_called_once()
        call_kwargs = MockSandbox.call_args[1]
        assert call_kwargs["volumes"] == {"/data/files": "/workspace"}

    def test_no_volumes_without_workspace(self):
        from haiku_skills_sandbox import SandboxState, _get_sandbox, _sandboxes

        _sandboxes.clear()
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            _get_sandbox(state)

        call_kwargs = MockSandbox.call_args[1]
        assert call_kwargs["volumes"] is None


class TestIdleCleanup:
    def test_stale_sandbox_is_stopped_and_replaced(self):
        import time

        from haiku_skills_sandbox import (
            SandboxState,
            _get_sandbox,
            _last_active,
            _sandboxes,
        )

        _sandboxes.clear()
        _last_active.clear()

        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            old_sandbox = MagicMock()
            new_sandbox = MagicMock()
            MockSandbox.side_effect = [old_sandbox, new_sandbox]

            _get_sandbox(state)
            session_id = state.session_id
            assert session_id is not None

            # Simulate idle beyond timeout
            _last_active[session_id] = time.monotonic() - 9999

            result = _get_sandbox(state)

        old_sandbox.stop.assert_called_once()
        assert result is new_sandbox

    def test_active_sandbox_is_reused(self):
        from haiku_skills_sandbox import (
            SandboxState,
            _get_sandbox,
            _last_active,
            _sandboxes,
        )

        _sandboxes.clear()
        _last_active.clear()

        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            first = _get_sandbox(state)
            second = _get_sandbox(state)

        assert first is second
        mock_instance.stop.assert_not_called()

    def test_stale_cleanup_ignores_stop_errors(self):
        import time

        from haiku_skills_sandbox import (
            SandboxState,
            _get_sandbox,
            _last_active,
            _sandboxes,
        )

        _sandboxes.clear()
        _last_active.clear()

        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            old_sandbox = MagicMock()
            old_sandbox.stop.side_effect = RuntimeError("already dead")
            new_sandbox = MagicMock()
            MockSandbox.side_effect = [old_sandbox, new_sandbox]

            _get_sandbox(state)
            assert state.session_id is not None
            _last_active[state.session_id] = time.monotonic() - 9999

            result = _get_sandbox(state)

        assert result is new_sandbox

    def test_timeout_configurable_via_env(self, monkeypatch):
        import haiku_skills_sandbox

        monkeypatch.setattr(haiku_skills_sandbox, "_idle_timeout_override", None)
        assert (
            haiku_skills_sandbox._idle_timeout()
            == haiku_skills_sandbox.IDLE_TIMEOUT_DEFAULT
        )

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT", "120")
        assert haiku_skills_sandbox._idle_timeout() == 120

    def test_timeout_configurable_via_create_skill(self):
        import haiku_skills_sandbox
        from haiku_skills_sandbox import create_skill

        old = haiku_skills_sandbox._idle_timeout_override
        try:
            create_skill(idle_timeout=300)
            assert haiku_skills_sandbox._idle_timeout() == 300
        finally:
            haiku_skills_sandbox._idle_timeout_override = old

    def test_create_skill_override_takes_precedence_over_env(self, monkeypatch):
        import haiku_skills_sandbox
        from haiku_skills_sandbox import create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT", "120")
        old = haiku_skills_sandbox._idle_timeout_override
        try:
            create_skill(idle_timeout=60)
            assert haiku_skills_sandbox._idle_timeout() == 60
        finally:
            haiku_skills_sandbox._idle_timeout_override = old


class TestCleanup:
    def test_cleanup_stops_all_sandboxes(self):
        from haiku_skills_sandbox import _cleanup_sandboxes, _sandboxes

        mock1 = MagicMock()
        mock2 = MagicMock()
        _sandboxes["a"] = mock1
        _sandboxes["b"] = mock2

        _cleanup_sandboxes()

        mock1.stop.assert_called_once()
        mock2.stop.assert_called_once()
        assert _sandboxes == {}

    def test_cleanup_ignores_stop_errors(self):
        from haiku_skills_sandbox import _cleanup_sandboxes, _sandboxes

        mock1 = MagicMock()
        mock1.stop.side_effect = RuntimeError("already dead")
        _sandboxes["a"] = mock1

        _cleanup_sandboxes()
        assert _sandboxes == {}


class TestSandboxRunDeps:
    def test_satisfies_protocol(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill()
        assert skill.deps_type is not None

        assert skill.deps_type is not None
        with patch("haiku_skills_sandbox.DockerSandbox"):
            deps = skill.deps_type(state=None, emit=lambda _: None)

        assert isinstance(deps, SkillRunDepsProtocol)

    def test_has_backend(self):
        from haiku_skills_sandbox import create_skill

        skill = create_skill()
        assert skill.deps_type is not None

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            deps = skill.deps_type(state=None, emit=lambda _: None)

        assert deps.backend is mock_instance

    def test_backend_uses_state_for_session_binding(self):
        from haiku_skills_sandbox import (
            SandboxState,
            _sandboxes,
            create_skill,
        )

        _sandboxes.clear()
        skill = create_skill()
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            deps1 = skill.deps_type(state=state, emit=lambda _: None)
            session_id = state.session_id

        assert session_id is not None
        deps2 = skill.deps_type(state=state, emit=lambda _: None)

        assert deps1.backend is deps2.backend

    def test_workspace_captured_in_closure(self):
        from haiku_skills_sandbox import SandboxState, _sandboxes, create_skill

        _sandboxes.clear()
        skill = create_skill(workspace=Path("/my/data"))
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            skill.deps_type(state=state, emit=lambda _: None)

        call_kwargs = MockSandbox.call_args[1]
        assert call_kwargs["volumes"] == {"/my/data": "/workspace"}
