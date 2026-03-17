"""Tests for the code execution skill package."""

import io
import runpy

import pytest

from haiku.skills.models import SkillSource

from .conftest import SKILLS_ROOT, make_ctx


class TestCodeExecution:
    def test_create_skill(self):
        from haiku_skills_code_execution import create_skill

        skill = create_skill()
        assert skill.metadata.name == "code-execution"
        assert (
            skill.metadata.description
            == "Write and execute Python code to solve tasks."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "code-execution"
        assert len(skill.tools) == 1

    def test_run_code_with_output(self):
        from haiku_skills_code_execution.scripts.run_code import main

        result = main("print(1 + 1)")
        assert "```python" in result
        assert "print(1 + 1)" in result
        assert "2" in result

    def test_run_code_with_result(self):
        from haiku_skills_code_execution.scripts.run_code import main

        result = main("1 + 1")
        assert "result: 2" in result

    def test_run_code_no_output(self):
        from haiku_skills_code_execution.scripts.run_code import main

        result = main("x = 1")
        assert "no output" in result.lower()

    def test_run_code_tool_with_state(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = make_ctx(state)
        result = run_code(ctx, "print(1 + 1)")
        assert "2" in result
        assert len(state.executions) == 1
        assert state.executions[0].code == "print(1 + 1)"
        assert state.executions[0].success is True

    def test_run_code_tool_with_result_value(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = make_ctx(state)
        result = run_code(ctx, "1 + 1")
        assert "result: 2" in result
        assert len(state.executions) == 1
        assert state.executions[0].result == "2"

    def test_run_code_tool_no_output(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = make_ctx(state)
        result = run_code(ctx, "x = 1")
        assert "no output" in result.lower()
        assert len(state.executions) == 1

    def test_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("sys.argv", ["run_code.py", "1 + 1"])
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = (
            SKILLS_ROOT
            / "code-execution"
            / "haiku_skills_code_execution"
            / "scripts"
            / "run_code.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        assert "result" in captured.getvalue()
