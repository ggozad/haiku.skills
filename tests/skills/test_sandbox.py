"""Tests for the sandbox skill package."""

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from pydantic_ai_backends.types import EditResult, ExecuteResponse, WriteResult

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

    def test_default_timeout_from_env(self, monkeypatch):
        import haiku_skills_sandbox

        assert (
            haiku_skills_sandbox._default_idle_timeout()
            == haiku_skills_sandbox.IDLE_TIMEOUT_DEFAULT
        )

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT", "120")
        assert haiku_skills_sandbox._default_idle_timeout() == 120

    def test_per_sandbox_timeout_via_create_skill(self):
        import time

        from haiku_skills_sandbox import (
            SandboxState,
            _last_active,
            _sandboxes,
            _timeouts,
            create_skill,
        )

        _sandboxes.clear()
        _last_active.clear()
        _timeouts.clear()

        skill = create_skill(idle_timeout=10)
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            old_sandbox = MagicMock()
            new_sandbox = MagicMock()
            MockSandbox.side_effect = [old_sandbox, new_sandbox]

            skill.deps_type(state=state, emit=lambda _: None)
            session_id = state.session_id
            assert session_id is not None
            assert _timeouts[session_id] == 10

            # Simulate idle beyond the per-sandbox timeout
            _last_active[session_id] = time.monotonic() - 20

            skill.deps_type(state=state, emit=lambda _: None)

        old_sandbox.stop.assert_called_once()

    def test_per_sandbox_timeout_overrides_env(self, monkeypatch):
        import time

        from haiku_skills_sandbox import (
            SandboxState,
            _last_active,
            _sandboxes,
            _timeouts,
            create_skill,
        )

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT", "9999")
        _sandboxes.clear()
        _last_active.clear()
        _timeouts.clear()

        skill = create_skill(idle_timeout=10)
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            old_sandbox = MagicMock()
            new_sandbox = MagicMock()
            MockSandbox.side_effect = [old_sandbox, new_sandbox]

            skill.deps_type(state=state, emit=lambda _: None)
            session_id = state.session_id
            assert session_id is not None

            # Idle beyond per-sandbox timeout (10s) but within env timeout (9999s)
            _last_active[session_id] = time.monotonic() - 20

            skill.deps_type(state=state, emit=lambda _: None)

        # Per-sandbox timeout wins — sandbox is cleaned up
        old_sandbox.stop.assert_called_once()


class TestImage:
    def test_default_image(self):
        from haiku_skills_sandbox import IMAGE_DEFAULT, _resolve_image

        assert _resolve_image() == IMAGE_DEFAULT

    def test_image_from_env(self, monkeypatch):
        from haiku_skills_sandbox import _resolve_image

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IMAGE", "custom:v1")
        assert _resolve_image() == "custom:v1"

    def test_image_from_create_skill(self):
        from haiku_skills_sandbox import SandboxState, _sandboxes, create_skill

        _sandboxes.clear()
        skill = create_skill(image="my-image:latest")
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            skill.deps_type(state=state, emit=lambda _: None)

        call_kwargs = MockSandbox.call_args[1]
        assert call_kwargs["image"] == "my-image:latest"

    def test_create_skill_image_overrides_env(self, monkeypatch):
        from haiku_skills_sandbox import SandboxState, _sandboxes, create_skill

        monkeypatch.setenv("HAIKU_SKILLS_SANDBOX_IMAGE", "env-image:v1")
        _sandboxes.clear()
        skill = create_skill(image="explicit:v2")
        assert skill.deps_type is not None
        state = SandboxState()

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            skill.deps_type(state=state, emit=lambda _: None)

        call_kwargs = MockSandbox.call_args[1]
        assert call_kwargs["image"] == "explicit:v2"


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
            InstrumentedSandbox,
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

        # Both wrap the same underlying backend
        assert isinstance(deps1.backend, InstrumentedSandbox)
        assert isinstance(deps2.backend, InstrumentedSandbox)
        assert deps1.backend._backend is deps2.backend._backend

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


class TestExecution:
    def test_defaults(self):
        from haiku_skills_sandbox import Execution

        e = Execution(command="ls")
        assert e.command == "ls"
        assert e.exit_code is None
        assert e.output == ""
        assert e.truncated is False

    def test_full_construction(self):
        from haiku_skills_sandbox import Execution

        e = Execution(command="echo hi", exit_code=0, output="hi\n", truncated=False)
        assert e.command == "echo hi"
        assert e.exit_code == 0
        assert e.output == "hi\n"
        assert e.truncated is False


class TestFileOperation:
    def test_read(self):
        from haiku_skills_sandbox import FileOperation

        op = FileOperation(operation="read", path="/tmp/f.txt")
        assert op.operation == "read"
        assert op.path == "/tmp/f.txt"

    def test_write(self):
        from haiku_skills_sandbox import FileOperation

        op = FileOperation(operation="write", path="/tmp/f.txt")
        assert op.operation == "write"

    def test_edit(self):
        from haiku_skills_sandbox import FileOperation

        op = FileOperation(operation="edit", path="/tmp/f.txt")
        assert op.operation == "edit"


class TestSandboxStateEnhanced:
    def test_default_lists_are_empty(self):
        from haiku_skills_sandbox import SandboxState

        state = SandboxState()
        assert state.executions == []
        assert state.file_operations == []

    def test_serialization_round_trip(self):
        from haiku_skills_sandbox import Execution, FileOperation, SandboxState

        state = SandboxState(
            session_id="abc",
            executions=[Execution(command="ls", exit_code=0, output="foo")],
            file_operations=[FileOperation(operation="write", path="/tmp/x")],
        )
        data = state.model_dump(mode="json")
        restored = SandboxState.model_validate(data)
        assert restored == state


class TestInstrumentedSandbox:
    def _make(self, state=None):
        from haiku_skills_sandbox import InstrumentedSandbox, SandboxState

        backend = MagicMock()
        if state is None:
            state = SandboxState(session_id="test-session")
        return InstrumentedSandbox(backend, state), backend, state

    def test_execute_records_to_state(self):
        wrapper, backend, state = self._make()
        backend.execute.return_value = ExecuteResponse(
            output="hello", exit_code=0, truncated=False
        )

        result = wrapper.execute("echo hello")

        assert result.output == "hello"
        assert result.exit_code == 0
        assert len(state.executions) == 1
        assert state.executions[0].command == "echo hello"
        assert state.executions[0].exit_code == 0
        assert state.executions[0].output == "hello"
        assert state.executions[0].truncated is False

    def test_execute_truncates_output_in_state(self):
        from haiku_skills_sandbox import MAX_OUTPUT_CHARS

        wrapper, backend, state = self._make()
        long_output = "x" * (MAX_OUTPUT_CHARS + 100)
        backend.execute.return_value = ExecuteResponse(
            output=long_output, exit_code=0, truncated=False
        )

        result = wrapper.execute("cat bigfile")

        # Original result is untouched
        assert len(result.output) == MAX_OUTPUT_CHARS + 100
        # State copy is truncated
        assert len(state.executions[0].output) == MAX_OUTPUT_CHARS

    def test_execute_caps_list_at_max(self):
        from haiku_skills_sandbox import MAX_EXECUTIONS, Execution, SandboxState

        state = SandboxState(
            session_id="s",
            executions=[Execution(command=f"cmd-{i}") for i in range(MAX_EXECUTIONS)],
        )
        wrapper, backend, _ = self._make(state=state)
        backend.execute.return_value = ExecuteResponse(
            output="", exit_code=0, truncated=False
        )

        wrapper.execute("new-cmd")

        assert len(state.executions) == MAX_EXECUTIONS
        assert state.executions[0].command == "cmd-1"  # oldest dropped
        assert state.executions[-1].command == "new-cmd"

    def test_read_records_file_operation(self):
        wrapper, backend, state = self._make()
        backend.read.return_value = "file content"

        result = wrapper.read("/tmp/f.txt")

        assert result == "file content"
        assert len(state.file_operations) == 1
        assert state.file_operations[0].operation == "read"
        assert state.file_operations[0].path == "/tmp/f.txt"

    def test_read_passes_args(self):
        wrapper, backend, state = self._make()
        backend.read.return_value = "line"

        wrapper.read("/f.txt", offset=5, limit=10)

        backend.read.assert_called_once_with("/f.txt", offset=5, limit=10)

    def test_write_records_on_success(self):
        wrapper, backend, state = self._make()
        backend.write.return_value = WriteResult(path="/tmp/f.txt", error=None)

        result = wrapper.write("/tmp/f.txt", "content")

        assert result.path == "/tmp/f.txt"
        assert len(state.file_operations) == 1
        assert state.file_operations[0].operation == "write"
        assert state.file_operations[0].path == "/tmp/f.txt"

    def test_write_does_not_record_on_error(self):
        wrapper, backend, state = self._make()
        backend.write.return_value = WriteResult(path=None, error="permission denied")

        result = wrapper.write("/tmp/f.txt", "content")

        assert result.error == "permission denied"
        assert len(state.file_operations) == 0

    def test_edit_records_on_success(self):
        wrapper, backend, state = self._make()
        backend.edit.return_value = EditResult(
            path="/tmp/f.txt", error=None, occurrences=1
        )

        result = wrapper.edit("/tmp/f.txt", "old", "new")

        assert result.path == "/tmp/f.txt"
        assert len(state.file_operations) == 1
        assert state.file_operations[0].operation == "edit"
        assert state.file_operations[0].path == "/tmp/f.txt"

    def test_edit_does_not_record_on_error(self):
        wrapper, backend, state = self._make()
        backend.edit.return_value = EditResult(
            path=None, error="not found", occurrences=None
        )

        wrapper.edit("/tmp/f.txt", "old", "new")

        assert len(state.file_operations) == 0

    def test_edit_passes_replace_all(self):
        wrapper, backend, state = self._make()
        backend.edit.return_value = EditResult(path="/f.txt", error=None, occurrences=3)

        wrapper.edit("/f.txt", "a", "b", replace_all=True)

        backend.edit.assert_called_once_with("/f.txt", "a", "b", replace_all=True)

    def test_file_operations_caps_at_max(self):
        from haiku_skills_sandbox import (
            MAX_FILE_OPERATIONS,
            FileOperation,
            SandboxState,
        )

        state = SandboxState(
            session_id="s",
            file_operations=[
                FileOperation(operation="read", path=f"/f-{i}")
                for i in range(MAX_FILE_OPERATIONS)
            ],
        )
        wrapper, backend, _ = self._make(state=state)
        backend.read.return_value = "content"

        wrapper.read("/new-file")

        assert len(state.file_operations) == MAX_FILE_OPERATIONS
        assert state.file_operations[0].path == "/f-1"  # oldest dropped
        assert state.file_operations[-1].path == "/new-file"

    def test_getattr_delegates(self):
        wrapper, backend, _ = self._make()
        backend.ls_info.return_value = ["file1"]

        result = wrapper.ls_info("/tmp")

        backend.ls_info.assert_called_once_with("/tmp")
        assert result == ["file1"]

    def test_id_property(self):
        wrapper, backend, _ = self._make()
        type(backend).id = PropertyMock(return_value="container-123")

        assert wrapper.id == "container-123"

    def test_session_id_property(self):
        wrapper, backend, _ = self._make()
        type(backend).session_id = PropertyMock(return_value="sess-456")

        assert wrapper.session_id == "sess-456"


class TestSandboxRunDepsInstrumented:
    def test_uses_instrumented_backend_with_state(self):
        from haiku_skills_sandbox import (
            InstrumentedSandbox,
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

            deps = skill.deps_type(state=state, emit=lambda _: None)

        assert isinstance(deps.backend, InstrumentedSandbox)

    def test_uses_raw_backend_without_state(self):
        from haiku_skills_sandbox import InstrumentedSandbox, _sandboxes, create_skill

        _sandboxes.clear()
        skill = create_skill()
        assert skill.deps_type is not None

        with patch("haiku_skills_sandbox.DockerSandbox") as MockSandbox:
            mock_instance = MagicMock()
            MockSandbox.return_value = mock_instance

            deps = skill.deps_type(state=None, emit=lambda _: None)

        assert not isinstance(deps.backend, InstrumentedSandbox)
        assert deps.backend is mock_instance
