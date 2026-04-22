"""Execute Python code safely in a sandboxed environment."""

from collections.abc import Callable
from typing import Any

from pydantic_monty import MontyError, MontyRepl, run_repl_async


def _build_external_functions(model: Any) -> dict[str, Callable[..., Any]]:
    """Build the external functions dict for the Monty sandbox."""
    from pydantic_ai import Agent

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
    repl: MontyRepl,
    code: str,
    external_functions: dict[str, Callable[..., Any]] | None = None,
) -> tuple[str, str | None, bool]:
    """Execute code in a persistent Monty REPL.

    Args:
        repl: REPL session whose heap and namespace persist across calls.
        code: The Python code to execute.
        external_functions: Functions available inside the sandbox.

    Returns:
        Tuple of (stdout, result_repr, success).
    """
    output_lines: list[str] = []

    def print_callback(_stream: str, text: str) -> None:
        output_lines.append(text)

    try:
        result = await run_repl_async(
            repl,
            code,
            external_functions=external_functions or {},
            print_callback=print_callback,
        )
    except MontyError as e:
        output_lines.append(f"Error: {e}")
        return "\n".join(output_lines), None, False

    stdout = "\n".join(output_lines)
    result_repr = repr(result) if result is not None else None
    return stdout, result_repr, True


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
