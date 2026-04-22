from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_monty import MontyRepl

from haiku.skills.models import Skill
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps


class Execution(BaseModel):
    code: str
    stdout: str
    result: str | None
    success: bool


class CodeState(BaseModel):
    executions: list[Execution] = []


@dataclass
class CodeRunDeps(SkillRunDeps):
    repl: MontyRepl | None = None


@asynccontextmanager
async def code_lifespan(deps: CodeRunDeps):
    deps.repl = MontyRepl()
    if isinstance(deps.state, CodeState):
        deps.state.executions.clear()
    yield


async def run_code(ctx: RunContext[CodeRunDeps], code: str) -> str:
    """Execute Python code and return the output.

    Args:
        code: The Python code to execute.
    """
    from haiku_skills_code_execution.sandbox import (
        _build_external_functions,
        _execute_code,
        _format_output,
    )

    assert ctx.deps is not None and ctx.deps.repl is not None
    external_fns = _build_external_functions(ctx.model)
    stdout, result, success = await _execute_code(ctx.deps.repl, code, external_fns)
    output = _format_output(code, stdout, result)

    if ctx.deps.state and isinstance(ctx.deps.state, CodeState):
        ctx.deps.state.executions.append(
            Execution(
                code=code,
                stdout=stdout,
                result=result,
                success=success,
            )
        )

    return output


def create_skill() -> Skill:
    metadata, instructions = parse_skill_md(Path(__file__).parent / "SKILL.md")

    return Skill(
        metadata=metadata,
        instructions=instructions,
        path=Path(__file__).parent,
        tools=[run_code],
        state_type=CodeState,
        state_namespace="code-execution",
        deps_type=CodeRunDeps,
        lifespan=code_lifespan,
    )
