from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import RunContext

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


def run_code(ctx: RunContext[SkillRunDeps], code: str) -> str:
    """Execute Python code and return the output.

    Args:
        code: The Python code to execute.
    """
    from haiku_skills_code_execution.scripts.run_code import main

    result = main(code)

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, CodeState):
        # Parse the formatted output to extract stdout and result
        stdout = ""
        result_value = None
        success = True

        lines = result.split("\n")
        i = 0
        # Skip the code block
        while i < len(lines) and not (
            lines[i].startswith("stdout:")
            or lines[i].startswith("result:")
            or "no output" in lines[i].lower()
        ):
            i += 1

        if i < len(lines) and lines[i].startswith("stdout:"):
            stdout_parts = [lines[i][len("stdout:") :].strip()]
            i += 1
            while i < len(lines) and not lines[i].startswith("result:"):
                stdout_parts.append(lines[i])
                i += 1
            stdout = "\n".join(stdout_parts).strip()

        if i < len(lines) and lines[i].startswith("result:"):
            result_value = lines[i][len("result:") :].strip()

        ctx.deps.state.executions.append(
            Execution(
                code=code,
                stdout=stdout,
                result=result_value,
                success=success,
            )
        )

    return result


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
