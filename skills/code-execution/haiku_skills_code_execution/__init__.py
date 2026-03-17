from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_monty import Monty, MontyError, run_monty_async

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps


class Execution(BaseModel):
    code: str
    stdout: str
    result: str | None
    success: bool


class CodeState(BaseModel):
    executions: list[Execution] = []


def _build_external_functions(model: Model) -> dict[str, Callable[..., Any]]:
    """Build the external functions dict for the Monty sandbox."""

    async def llm(prompt: str) -> str:
        """One-shot LLM call."""
        try:
            agent: Agent[None, str] = Agent(model)
            result = await agent.run(prompt)
            return result.output
        except Exception as e:
            return f"Error: {e}"

    return {"llm": llm}


async def _execute_code(
    code: str, external_functions: dict[str, Callable[..., Any]]
) -> tuple[str, str | None]:
    """Execute code in the Monty sandbox.

    Returns (stdout, result_repr).
    """
    output_lines: list[str] = []

    def print_callback(_stream: str, text: str) -> None:
        output_lines.append(text)

    try:
        result = await run_monty_async(
            Monty(code),
            external_functions=external_functions,
            print_callback=print_callback,
        )
    except MontyError as e:
        output_lines.append(f"Error: {e}")
        return "\n".join(output_lines), None

    stdout = "\n".join(output_lines)
    result_repr = repr(result) if result is not None else None
    return stdout, result_repr


def _format_output(code: str, stdout: str, result: str | None) -> str:
    """Format execution output as markdown."""
    parts = [f"```python\n{code}\n```"]
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if result is not None:
        parts.append(f"result: {result}")
    if not stdout and result is None:
        parts.append("Code executed successfully (no output).")
    return "\n".join(parts)


async def run_code(ctx: RunContext[SkillRunDeps], code: str) -> str:
    """Execute Python code and return the output.

    Args:
        code: The Python code to execute.
    """
    external_fns = _build_external_functions(ctx.model)
    stdout, result = await _execute_code(code, external_fns)
    output = _format_output(code, stdout, result)

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, CodeState):
        success = "Error:" not in (stdout or "")
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
    skill_dir = Path(__file__).parent / "code-execution"
    metadata, instructions = parse_skill_md(skill_dir / "SKILL.md")

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=skill_dir,
        instructions=instructions,
        tools=[run_code],
        state_type=CodeState,
        state_namespace="code-execution",
    )
