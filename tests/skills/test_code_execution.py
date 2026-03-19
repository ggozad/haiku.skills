"""Tests for the code execution skill package."""

import io
import runpy

import pytest
from pydantic_ai.models.test import TestModel

from haiku.skills.models import SkillSource

from .conftest import SKILLS_ROOT, make_ctx


class TestCreateSkill:
    def test_create_skill(self):
        from haiku_skills_code_execution import create_skill

        skill = create_skill()
        assert skill.metadata.name == "codeexecution"
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "codeexecution"
        assert len(skill.tools) == 1


class TestBuildExternalFunctions:
    def test_returns_dict_with_llm_key(self):
        from haiku_skills_code_execution import _build_external_functions

        model = TestModel(custom_output_text="hello")
        fns = _build_external_functions(model)
        assert "llm" in fns
        assert callable(fns["llm"])

    @pytest.mark.anyio
    async def test_llm_calls_agent_and_returns_output(self):
        from haiku_skills_code_execution import _build_external_functions

        model = TestModel(custom_output_text="Paris")
        fns = _build_external_functions(model)
        result = await fns["llm"]("What is the capital of France?")
        assert result == "Paris"

    @pytest.mark.anyio
    async def test_llm_returns_error_string_on_failure(self, monkeypatch):
        from haiku_skills_code_execution import _build_external_functions

        model = TestModel(custom_output_text="unused")

        # Make Agent.run raise an exception
        async def broken_run(*args, **kwargs):
            raise RuntimeError("model unavailable")

        from pydantic_ai import Agent

        monkeypatch.setattr(Agent, "run", broken_run)

        fns = _build_external_functions(model)
        result = await fns["llm"]("anything")
        assert "Error" in result
        assert "model unavailable" in result


class TestExecuteCode:
    @pytest.mark.anyio
    async def test_basic_expression(self):
        from haiku_skills_code_execution import _execute_code

        stdout, result, success = await _execute_code("1 + 1", {})
        assert stdout == ""
        assert result == "2"
        assert success is True

    @pytest.mark.anyio
    async def test_print_output(self):
        from haiku_skills_code_execution import _execute_code

        stdout, result, success = await _execute_code("print('hello')", {})
        assert "hello" in stdout
        assert result is None
        assert success is True

    @pytest.mark.anyio
    async def test_no_output(self):
        from haiku_skills_code_execution import _execute_code

        stdout, result, success = await _execute_code("x = 1", {})
        assert stdout == ""
        assert result is None
        assert success is True

    @pytest.mark.anyio
    async def test_monty_error(self):
        from haiku_skills_code_execution import _execute_code

        stdout, result, success = await _execute_code("1 / 0", {})
        assert "Error" in (stdout or "")
        assert result is None
        assert success is False


class TestFormatOutput:
    def test_stdout_and_result(self):
        from haiku_skills_code_execution import _format_output

        output = _format_output("x = 1\nprint(x)\nx", "1\n", "1")
        assert "```python" in output
        assert "x = 1" in output
        assert "stdout:" in output
        assert "result: 1" in output

    def test_result_only(self):
        from haiku_skills_code_execution import _format_output

        output = _format_output("1 + 1", "", "2")
        assert "```python" in output
        assert "result: 2" in output
        assert "stdout:" not in output

    def test_no_output(self):
        from haiku_skills_code_execution import _format_output

        output = _format_output("x = 1", "", None)
        assert "no output" in output.lower()

    def test_stdout_only(self):
        from haiku_skills_code_execution import _format_output

        output = _format_output("print('hi')", "hi\n", None)
        assert "stdout:" in output
        assert "result:" not in output


class TestRunCodeAsync:
    @pytest.mark.anyio
    async def test_basic_execution(self):
        from haiku_skills_code_execution import run_code

        model = TestModel()
        ctx = make_ctx(model=model)
        result = await run_code(ctx, "print('hello')")
        assert "hello" in result

    @pytest.mark.anyio
    async def test_result_value(self):
        from haiku_skills_code_execution import run_code

        model = TestModel()
        ctx = make_ctx(model=model)
        result = await run_code(ctx, "1 + 1")
        assert "result: 2" in result

    @pytest.mark.anyio
    async def test_no_output(self):
        from haiku_skills_code_execution import run_code

        model = TestModel()
        ctx = make_ctx(model=model)
        result = await run_code(ctx, "x = 1")
        assert "no output" in result.lower()

    @pytest.mark.anyio
    async def test_with_state(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        model = TestModel()
        ctx = make_ctx(state=state, model=model)
        result = await run_code(ctx, "print(1 + 1)")
        assert "2" in result
        assert len(state.executions) == 1
        assert state.executions[0].code == "print(1 + 1)"
        assert state.executions[0].success is True

    @pytest.mark.anyio
    async def test_with_state_result_value(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        model = TestModel()
        ctx = make_ctx(state=state, model=model)
        result = await run_code(ctx, "1 + 1")
        assert "result: 2" in result
        assert len(state.executions) == 1
        assert state.executions[0].result == "2"

    @pytest.mark.anyio
    async def test_without_state(self):
        from haiku_skills_code_execution import run_code

        model = TestModel()
        ctx = make_ctx(model=model)
        ctx.deps = None
        result = await run_code(ctx, "1 + 1")
        assert "result: 2" in result

    @pytest.mark.anyio
    async def test_with_llm(self):
        from haiku_skills_code_execution import run_code

        model = TestModel(custom_output_text="Paris")
        ctx = make_ctx(model=model)
        result = await run_code(ctx, "x = await llm('capital of France')\nprint(x)")
        assert "Paris" in result

    @pytest.mark.anyio
    async def test_error_handling(self):
        from haiku_skills_code_execution import run_code

        model = TestModel()
        ctx = make_ctx(model=model)
        result = await run_code(ctx, "1 / 0")
        assert "Error" in result

    @pytest.mark.anyio
    async def test_with_state_error(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        model = TestModel()
        ctx = make_ctx(state=state, model=model)
        result = await run_code(ctx, "1 / 0")
        assert "Error" in result
        assert len(state.executions) == 1
        assert state.executions[0].success is False


class TestScriptRunCode:
    """Tests for the standalone scripts/run_code.py (unchanged)."""

    def test_run_code_with_output(self):
        from haiku_skills_code_execution.codeexecution.scripts.run_code import main

        result = main("print(1 + 1)")
        assert "```python" in result
        assert "print(1 + 1)" in result
        assert "2" in result

    def test_run_code_with_result(self):
        from haiku_skills_code_execution.codeexecution.scripts.run_code import main

        result = main("1 + 1")
        assert "result: 2" in result

    def test_run_code_no_output(self):
        from haiku_skills_code_execution.codeexecution.scripts.run_code import main

        result = main("x = 1")
        assert "no output" in result.lower()

    def test_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("sys.argv", ["run_code.py", "--code", "1 + 1"])
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = (
            SKILLS_ROOT
            / "code-execution"
            / "haiku_skills_code_execution"
            / "codeexecution"
            / "scripts"
            / "run_code.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        assert "result" in captured.getvalue()
