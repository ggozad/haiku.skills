"""Tests for the code execution skill package."""

from unittest.mock import MagicMock

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel
from pydantic_monty import MontyRepl


def _make_code_ctx(
    state=None,
    model: Model | None = None,
    repl: MontyRepl | None = None,
):
    """Mock RunContext with CodeRunDeps populated (as the lifespan would)."""
    from haiku_skills_code_execution import CodeRunDeps

    ctx = MagicMock(spec=RunContext)
    ctx.deps = CodeRunDeps(state=state, repl=repl if repl is not None else MontyRepl())
    if model is not None:
        ctx.model = model
    return ctx


class TestCreateSkill:
    def test_create_skill(self):
        from haiku_skills_code_execution import create_skill

        skill = create_skill()
        assert skill.metadata.name == "code-execution"
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "code-execution"
        assert len(skill.tools) == 1
        assert skill.deps_type is not None
        assert skill.lifespan is not None
        assert skill.path is not None


class TestBuildExternalFunctions:
    def test_returns_dict_with_llm_key(self):
        from haiku_skills_code_execution.sandbox import (
            _build_external_functions,
        )

        model = TestModel(custom_output_text="hello")
        fns = _build_external_functions(model)
        assert "llm" in fns
        assert callable(fns["llm"])

    @pytest.mark.anyio
    async def test_llm_calls_agent_and_returns_output(self):
        from haiku_skills_code_execution.sandbox import (
            _build_external_functions,
        )

        model = TestModel(custom_output_text="Paris")
        fns = _build_external_functions(model)
        result = await fns["llm"]("What is the capital of France?")
        assert result == "Paris"

    @pytest.mark.anyio
    async def test_llm_returns_error_string_on_failure(self, monkeypatch):
        from haiku_skills_code_execution.sandbox import (
            _build_external_functions,
        )

        model = TestModel(custom_output_text="unused")

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
        from haiku_skills_code_execution.sandbox import _execute_code

        stdout, result, success = await _execute_code(MontyRepl(), "1 + 1")
        assert stdout == ""
        assert result == "2"
        assert success is True

    @pytest.mark.anyio
    async def test_print_output(self):
        from haiku_skills_code_execution.sandbox import _execute_code

        stdout, result, success = await _execute_code(MontyRepl(), "print('hello')")
        assert "hello" in stdout
        assert result is None
        assert success is True

    @pytest.mark.anyio
    async def test_no_output(self):
        from haiku_skills_code_execution.sandbox import _execute_code

        stdout, result, success = await _execute_code(MontyRepl(), "x = 1")
        assert stdout == ""
        assert result is None
        assert success is True

    @pytest.mark.anyio
    async def test_monty_error(self):
        from haiku_skills_code_execution.sandbox import _execute_code

        stdout, result, success = await _execute_code(MontyRepl(), "1 / 0")
        assert "Error" in (stdout or "")
        assert result is None
        assert success is False

    @pytest.mark.anyio
    async def test_with_external_functions(self):
        from haiku_skills_code_execution.sandbox import (
            _build_external_functions,
            _execute_code,
        )

        model = TestModel(custom_output_text="Paris")
        external_fns = _build_external_functions(model)
        stdout, result, success = await _execute_code(
            MontyRepl(), "x = await llm('capital of France')\nprint(x)", external_fns
        )
        assert "Paris" in stdout
        assert success is True

    @pytest.mark.anyio
    async def test_repl_variables_persist_across_calls(self):
        from haiku_skills_code_execution.sandbox import _execute_code

        repl = MontyRepl()
        await _execute_code(repl, "x = 41")
        stdout, result, success = await _execute_code(repl, "x + 1")
        assert success is True
        assert result == "42"


class TestFormatOutput:
    def test_stdout_and_result(self):
        from haiku_skills_code_execution.sandbox import _format_output

        output = _format_output("x = 1\nprint(x)\nx", "1\n", "1")
        assert "```python" in output
        assert "x = 1" in output
        assert "stdout:" in output
        assert "result: 1" in output

    def test_result_only(self):
        from haiku_skills_code_execution.sandbox import _format_output

        output = _format_output("1 + 1", "", "2")
        assert "```python" in output
        assert "result: 2" in output
        assert "stdout:" not in output

    def test_no_output(self):
        from haiku_skills_code_execution.sandbox import _format_output

        output = _format_output("x = 1", "", None)
        assert "no output" in output.lower()

    def test_stdout_only(self):
        from haiku_skills_code_execution.sandbox import _format_output

        output = _format_output("print('hi')", "hi\n", None)
        assert "stdout:" in output
        assert "result:" not in output


class TestRunCodeAsync:
    @pytest.mark.anyio
    async def test_basic_execution(self):
        from haiku_skills_code_execution import run_code

        ctx = _make_code_ctx(model=TestModel())
        result = await run_code(ctx, "print('hello')")
        assert "hello" in result

    @pytest.mark.anyio
    async def test_result_value(self):
        from haiku_skills_code_execution import run_code

        ctx = _make_code_ctx(model=TestModel())
        result = await run_code(ctx, "1 + 1")
        assert "result: 2" in result

    @pytest.mark.anyio
    async def test_no_output(self):
        from haiku_skills_code_execution import run_code

        ctx = _make_code_ctx(model=TestModel())
        result = await run_code(ctx, "x = 1")
        assert "no output" in result.lower()

    @pytest.mark.anyio
    async def test_with_state(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = _make_code_ctx(state=state, model=TestModel())
        result = await run_code(ctx, "print(1 + 1)")
        assert "2" in result
        assert len(state.executions) == 1
        assert state.executions[0].code == "print(1 + 1)"
        assert state.executions[0].success is True

    @pytest.mark.anyio
    async def test_with_state_result_value(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = _make_code_ctx(state=state, model=TestModel())
        result = await run_code(ctx, "1 + 1")
        assert "result: 2" in result
        assert len(state.executions) == 1
        assert state.executions[0].result == "2"

    @pytest.mark.anyio
    async def test_with_llm(self):
        from haiku_skills_code_execution import run_code

        ctx = _make_code_ctx(model=TestModel(custom_output_text="Paris"))
        result = await run_code(ctx, "x = await llm('capital of France')\nprint(x)")
        assert "Paris" in result

    @pytest.mark.anyio
    async def test_error_handling(self):
        from haiku_skills_code_execution import run_code

        ctx = _make_code_ctx(model=TestModel())
        result = await run_code(ctx, "1 / 0")
        assert "Error" in result

    @pytest.mark.anyio
    async def test_with_state_error(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = _make_code_ctx(state=state, model=TestModel())
        result = await run_code(ctx, "1 / 0")
        assert "Error" in result
        assert len(state.executions) == 1
        assert state.executions[0].success is False

    @pytest.mark.anyio
    async def test_variables_persist_across_tool_calls(self):
        from haiku_skills_code_execution import run_code

        ctx = _make_code_ctx(model=TestModel())
        await run_code(ctx, "x = 41")
        result = await run_code(ctx, "x + 1")
        assert "result: 42" in result


class TestCodeLifespan:
    @pytest.mark.anyio
    async def test_lifespan_populates_repl(self):
        from haiku_skills_code_execution import create_skill

        skill = create_skill()
        assert skill.deps_type is not None
        assert skill.lifespan is not None

        deps = skill.deps_type(state=None, emit=lambda _: None)
        assert deps.repl is None
        async with skill.lifespan(deps):
            assert isinstance(deps.repl, MontyRepl)

    @pytest.mark.anyio
    async def test_lifespan_clears_executions(self):
        from haiku_skills_code_execution import CodeState, Execution, create_skill

        skill = create_skill()
        assert skill.deps_type is not None
        assert skill.lifespan is not None

        state = CodeState(
            executions=[Execution(code="x = 1", stdout="", result=None, success=True)]
        )
        deps = skill.deps_type(state=state, emit=lambda _: None)

        async with skill.lifespan(deps):
            assert state.executions == []

    @pytest.mark.anyio
    async def test_lifespan_without_state_does_not_raise(self):
        from haiku_skills_code_execution import create_skill

        skill = create_skill()
        assert skill.deps_type is not None
        assert skill.lifespan is not None

        deps = skill.deps_type(state=None, emit=lambda _: None)
        async with skill.lifespan(deps):
            pass
