import asyncio
import os
import shlex
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, ToolReturn, UsageLimits
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models import Model
from pydantic_ai.toolsets import FunctionToolset, ToolsetTool

from haiku.skills.models import Skill
from haiku.skills.prompts import MAIN_AGENT_PROMPT, SKILL_PROMPT
from haiku.skills.registry import SkillRegistry
from haiku.skills.state import SkillRunDeps, compute_state_delta


def resolve_model(model: str) -> Model:
    """Resolve a model string to a pydantic-ai Model.

    For ``ollama:`` prefixed strings, uses ``OLLAMA_BASE_URL`` env var
    if set, otherwise defaults to ``http://127.0.0.1:11434/v1``.
    """
    if model.startswith("ollama:"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
        return OpenAIChatModel(
            model.removeprefix("ollama:"),
            provider=OllamaProvider(base_url=base_url),
        )
    from pydantic_ai.models import infer_model

    return infer_model(model)


def _last_tool_result(messages: list[ModelMessage]) -> str | None:
    """Extract the content of the last tool return from messages."""
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, ToolReturnPart):
                    return part.model_response_str()
    return None


def _create_read_resource(skill: Skill) -> Callable[..., Any]:
    """Create a read_resource tool bound to a specific skill."""
    assert skill.path is not None

    async def read_resource(path: str) -> str:
        """Read a resource file from the skill directory.

        Args:
            path: Relative path to the resource file.
        """
        if path not in skill.resources:
            raise ValueError(f"'{path}' is not an available resource")
        resolved = (skill.path / path).resolve()  # type: ignore[operator]
        if not resolved.is_relative_to(skill.path.resolve()):  # type: ignore[union-attr]
            raise ValueError(f"'{path}' is not an available resource")
        try:
            return resolved.read_text()
        except UnicodeDecodeError:
            raise ValueError(f"'{path}' is not a text file")

    return read_resource


def _create_run_script(skill: Skill) -> Callable[..., Any]:
    """Create a run_script tool bound to a specific skill."""
    assert skill.path is not None
    scripts_dir = (skill.path / "scripts").resolve()

    async def run_script(script: str, arguments: str = "") -> str:
        """Execute a script from the skill's scripts/ directory.

        Args:
            script: Relative path to the script (e.g. 'scripts/extract.py').
            arguments: Command-line arguments for the script.
        """
        resolved = (skill.path / script).resolve()  # type: ignore[operator]
        if not resolved.is_relative_to(scripts_dir):
            raise ValueError(f"'{script}' is not under scripts/")
        if not resolved.exists():
            raise ValueError(f"Script '{script}' not found")
        args = shlex.split(arguments) if arguments else []
        if resolved.suffix == ".py":
            cmd = [sys.executable, str(resolved), *args]
        elif resolved.suffix == ".sh":
            cmd = ["bash", str(resolved), *args]
        else:
            cmd = [str(resolved), *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(skill.path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Script {script} failed (exit {proc.returncode}): "
                f"{stderr.decode().strip()}"
            )
        return stdout.decode()

    return run_script


async def _run_skill(
    model: str | Model,
    skill: Skill,
    request: str,
    state: BaseModel | None = None,
) -> str:
    instructions = skill.instructions or "No specific instructions."
    resource_section = ""
    scripts_section = ""
    tools = list(skill.tools)
    if skill.resources:
        resource_list = "\n".join(f"- {r}" for r in skill.resources)
        resource_section = (
            f"## Available resources\n\n"
            f"{resource_list}\n\n"
            f"Use the `read_resource` tool to read any of these files.\n\n"
        )
        tools.append(_create_read_resource(skill))
    if skill.path and (skill.path / "scripts").is_dir():
        tools.append(_create_run_script(skill))
        script_files = sorted(
            str(f.relative_to(skill.path))
            for f in (skill.path / "scripts").rglob("*")
            if f.is_file() and f.suffix in (".py", ".sh") and f.name != "__init__.py"
        )
        if script_files:
            script_list = "\n".join(f"- {s}" for s in script_files)
            scripts_section = (
                f"## Available scripts\n\n"
                f"{script_list}\n\n"
                f"Use the `run_script` tool to execute any of these scripts.\n\n"
            )
    system_prompt = SKILL_PROMPT.format(
        task_description=request,
        skill_instructions=instructions,
        resource_section=resource_section,
        scripts_section=scripts_section,
    )
    deps = SkillRunDeps(state=state) if state else None
    agent = Agent[SkillRunDeps | None, str](
        model,
        system_prompt=system_prompt,
        tools=tools,
        toolsets=skill.toolsets or None,
    )
    result = await agent.run(
        request,
        deps=deps,
        usage_limits=UsageLimits(request_limit=10),
    )
    return _last_tool_result(result.all_messages()) or result.output


class SkillToolset(FunctionToolset[Any]):
    """A toolset that exposes skills as tools for a pydantic-ai Agent."""

    def __init__(
        self,
        *,
        skills: list[Skill] | None = None,
        skill_paths: list[Path] | None = None,
        use_entrypoints: bool = False,
        skill_model: str | Model | None = None,
    ) -> None:
        super().__init__()
        self._registry = SkillRegistry()
        self._namespaces: dict[str, BaseModel] = {}
        self._last_restored_state: dict[str, Any] | None = None
        self._skill_model = skill_model
        if skill_paths:
            self._registry.discover(paths=skill_paths)
        if use_entrypoints:
            self._registry.discover(use_entrypoints=True)
        for name in self._registry.names:
            skill = self._registry.get(name)
            if skill:
                self._register_skill_state(skill)
        if skills:
            for skill in skills:
                self._registry.register(skill)
                self._register_skill_state(skill)
        self._register_tools()

    def _register_skill_state(self, skill: Skill) -> None:
        """Register the state namespace for a skill."""
        if skill.state_type is None or skill.state_namespace is None:
            return
        namespace = skill.state_namespace
        if namespace in self._namespaces:
            existing = type(self._namespaces[namespace])
            if existing is not skill.state_type:
                raise TypeError(
                    f"Namespace '{namespace}' registered with type "
                    f"{existing.__name__}, cannot re-register with "
                    f"{skill.state_type.__name__}"
                )
        else:
            self._namespaces[namespace] = skill.state_type()

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        # Overridden to restore AG-UI state from deps before returning tools.
        # get_tools() is the only per-run hook with RunContext access in the
        # toolset API — there is no dedicated per-run setup method.
        self._maybe_restore_state(ctx)
        return await super().get_tools(ctx)

    def _maybe_restore_state(self, ctx: RunContext[Any]) -> None:
        """Restore namespace state from deps if it carries AG-UI state.

        Uses identity check (``is``) so we restore once per AG-UI request
        (each request creates a new dict) but not on every model step within
        a single run.
        """
        deps = ctx.deps
        if deps is None or not hasattr(deps, "state"):
            return
        state = deps.state
        if not isinstance(state, dict) or not state:
            return
        if state is self._last_restored_state:
            return
        self._last_restored_state = state
        self.restore_state_snapshot(state)

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def skill_catalog(self) -> str:
        lines: list[str] = []
        for meta in self._registry.list_metadata():
            lines.append(f"- **{meta.name}**: {meta.description}")
        return "\n".join(lines)

    @property
    def system_prompt(self) -> str:
        return MAIN_AGENT_PROMPT.format(skill_catalog=self.skill_catalog)

    @property
    def state_schemas(self) -> dict[str, dict[str, Any]]:
        """JSON Schema per namespace, keyed by namespace string."""
        return {ns: state.model_json_schema() for ns, state in self._namespaces.items()}

    def build_state_snapshot(self) -> dict[str, Any]:
        """Build a snapshot of all namespace states."""
        return {
            ns: state.model_dump(mode="json") for ns, state in self._namespaces.items()
        }

    def restore_state_snapshot(self, data: dict[str, Any]) -> None:
        """Restore namespace states from a snapshot."""
        for ns, state_data in data.items():
            if ns in self._namespaces:
                model_type = type(self._namespaces[ns])
                self._namespaces[ns] = model_type.model_validate(state_data)

    def get_namespace(self, namespace: str) -> BaseModel | None:
        """Get state instance for a namespace."""
        return self._namespaces.get(namespace)

    def _register_tools(self) -> None:
        registry = self._registry

        @self.tool
        async def execute_skill(
            ctx: RunContext[Any], skill_name: str, request: str
        ) -> str | ToolReturn:
            """Execute a skill by name.

            Args:
                skill_name: The exact name of the skill to use.
                request: A clear description of what you need the skill to do.
            """
            skill = registry.get(skill_name)
            if skill is None:
                return f"Error: Skill '{skill_name}' not found in registry"
            model_override = (
                skill.model or self._skill_model or os.environ.get("HAIKU_SKILL_MODEL")
            )
            skill_model: str | Model = (
                resolve_model(model_override)
                if isinstance(model_override, str)
                else model_override or ctx.model
            )

            namespace = skill.state_namespace
            state = self._namespaces.get(namespace) if namespace else None
            old_snapshot = (
                {namespace: state.model_dump(mode="json")}
                if namespace and state
                else None
            )

            try:
                result = await _run_skill(skill_model, skill, request, state=state)
            except Exception as e:
                return f"Error: {e}"

            if old_snapshot is not None and namespace and state:
                new_snapshot = {namespace: state.model_dump(mode="json")}
                delta = compute_state_delta(old_snapshot, new_snapshot)
                if delta is not None:
                    return ToolReturn(return_value=result, metadata=[delta])

            return result
