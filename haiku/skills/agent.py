import asyncio
import json
import os
import shlex
import sys
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from pathlib import Path
from typing import Any

from ag_ui.core import (
    BaseEvent,
    EventType,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, ToolReturn, UsageLimits
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
)
from pydantic_ai.models import Model
from pydantic_ai.toolsets import FunctionToolset, ToolsetTool

from haiku.skills.models import Skill
from haiku.skills.prompts import SKILL_PROMPT
from haiku.skills.registry import SkillRegistry
from haiku.skills.state import SkillRunDeps, compute_state_delta

SCRIPT_RUNNERS: dict[str, tuple[str, ...]] = {
    ".py": (sys.executable,),
    ".sh": ("bash",),
    ".js": ("node",),
    ".ts": ("npx", "tsx"),
}


def resolve_model(model: str) -> Model:
    """Resolve a model string to a pydantic-ai Model.

    For ``ollama:`` prefixed strings, uses ``OLLAMA_BASE_URL`` env var
    if set, otherwise defaults to ``http://127.0.0.1:11434``.
    """
    if model.startswith("ollama:"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        return OpenAIChatModel(
            model.removeprefix("ollama:"),
            provider=OllamaProvider(base_url=f"{base_url}/v1"),
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


def _events_to_agui(skill_name: str, events: list[Any]) -> list[BaseEvent]:
    """Convert pydantic-ai tool events to AG-UI events.

    Args:
        skill_name: Skill name used to prefix tool call IDs.
        events: List of FunctionToolCallEvent/FunctionToolResultEvent.
    """
    result: list[BaseEvent] = []
    for event in events:
        if isinstance(event, FunctionToolCallEvent):
            tool_call_id = f"{skill_name}:{event.tool_call_id}"
            args = event.part.args
            args_str = args if isinstance(args, str) else json.dumps(args or {})
            result.append(
                ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_id=tool_call_id,
                    tool_call_name=event.part.tool_name,
                )
            )
            result.append(
                ToolCallArgsEvent(
                    type=EventType.TOOL_CALL_ARGS,
                    tool_call_id=tool_call_id,
                    delta=args_str,
                )
            )
            result.append(
                ToolCallEndEvent(
                    type=EventType.TOOL_CALL_END,
                    tool_call_id=tool_call_id,
                )
            )
        elif isinstance(event, FunctionToolResultEvent):
            tool_call_id = f"{skill_name}:{event.tool_call_id}"
            result.append(
                ToolCallResultEvent(
                    type=EventType.TOOL_CALL_RESULT,
                    tool_call_id=tool_call_id,
                    message_id=str(uuid.uuid4()),
                    content=event.result.model_response_str(),
                )
            )
    return result


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
        runner = SCRIPT_RUNNERS.get(resolved.suffix, ())
        cmd = [*runner, str(resolved), *args]
        existing = os.environ.get("PYTHONPATH", "")
        pythonpath = (
            f"{skill.path}{os.pathsep}{existing}" if existing else str(skill.path)
        )
        env = {**os.environ, "PYTHONPATH": pythonpath}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(skill.path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            output = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(
                f"Script {script} failed (exit {proc.returncode}): {output}"
            )
        return stdout.decode()

    return run_script


async def _run_skill(
    model: str | Model,
    skill: Skill,
    request: str,
    state: BaseModel | None = None,
    event_sink: Callable[[BaseEvent], Awaitable[None]] | None = None,
) -> tuple[str, list[Any]]:
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
            if f.is_file()
            and f.name != "__init__.py"
            and (f.suffix in SCRIPT_RUNNERS or os.access(f, os.X_OK))
        )
        if script_files:
            script_list = "\n".join(f"- {s}" for s in script_files)
            scripts_section = (
                f"## Available scripts\n\n"
                f"{script_list}\n\n"
                f"Execute scripts with the `run_script` tool "
                f"(not `read_resource` — that is only for resource files).\n\n"
            )
    system_prompt = SKILL_PROMPT.format(
        task_description=request,
        skill_instructions=instructions,
        resource_section=resource_section,
        scripts_section=scripts_section,
    )

    collected_events: list[Any] = []
    skill_name = skill.metadata.name

    async def event_handler(
        ctx: RunContext[SkillRunDeps],
        events: AsyncIterable[AgentStreamEvent],
    ) -> None:
        async for event in events:
            if isinstance(event, (FunctionToolCallEvent, FunctionToolResultEvent)):
                if event_sink is not None:
                    for agui_event in _events_to_agui(skill_name, [event]):
                        await event_sink(agui_event)
                else:
                    collected_events.append(event)

    deps = SkillRunDeps(state=state)
    agent = Agent[SkillRunDeps, str](
        model,
        system_prompt=system_prompt,
        tools=tools,
        toolsets=skill.toolsets or None,
    )
    result = await agent.run(
        request,
        deps=deps,
        usage_limits=UsageLimits(request_limit=20),
        event_stream_handler=event_handler,
    )
    text = _last_tool_result(result.all_messages()) or result.output
    return text, collected_events


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
        self._event_sink: Callable[[BaseEvent], Awaitable[None]] | None = None
        if skills:
            for skill in skills:
                self._registry.register(skill)
        if skill_paths:
            self._registry.discover(paths=skill_paths)
        if use_entrypoints:
            self._registry.discover(use_entrypoints=True)
        for name in self._registry.names:
            skill = self._registry.get(name)
            if skill:
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

            event_sink = self._event_sink

            try:
                result, collected_events = await _run_skill(
                    skill_model, skill, request, state=state, event_sink=event_sink
                )
            except Exception as e:
                return f"Error: {e}"

            metadata: list[BaseEvent] = []
            if not event_sink:
                metadata.extend(_events_to_agui(skill.metadata.name, collected_events))

            if old_snapshot is not None and namespace and state:
                new_snapshot = {namespace: state.model_dump(mode="json")}
                delta = compute_state_delta(old_snapshot, new_snapshot)
                if delta is not None:
                    metadata.append(delta)

            if metadata:
                return ToolReturn(return_value=result, metadata=metadata)
            return result


class AguiEventStream:
    """Merges main-agent and sub-agent AG-UI events into a single stream.

    Use as an async context manager + async iterator::

        async with run_agui_stream(toolset, adapter) as stream:
            async for event in stream:
                ...

    The context manager ensures the event sink is properly cleaned up,
    even if the consumer breaks early.
    """

    def __init__(
        self,
        toolset: SkillToolset,
        adapter: Any,
        **run_kwargs: Any,
    ) -> None:
        self._toolset = toolset
        self._adapter = adapter
        self._run_kwargs = run_kwargs
        self._queue: asyncio.Queue[BaseEvent | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "AguiEventStream":
        async def event_sink(event: BaseEvent) -> None:
            self._queue.put_nowait(event)

        self._toolset._event_sink = event_sink

        async def run_adapter() -> None:
            try:
                async for event in self._adapter.run_stream(**self._run_kwargs):
                    if isinstance(event, BaseEvent):
                        self._queue.put_nowait(event)
            finally:
                self._toolset._event_sink = None
                self._queue.put_nowait(None)

        self._task = asyncio.create_task(run_adapter())
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        self._toolset._event_sink = None
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def __aiter__(self) -> "AguiEventStream":
        return self

    async def __anext__(self) -> BaseEvent:
        event = await self._queue.get()
        if event is None:
            raise StopAsyncIteration
        return event


def run_agui_stream(
    toolset: SkillToolset,
    adapter: Any,
    **run_kwargs: Any,
) -> AguiEventStream:
    """Stream AG-UI events with real-time sub-agent tool events.

    Wraps ``adapter.run_stream()`` and merges main-agent events with
    sub-agent tool events (search, fetch, etc.) that would otherwise
    be batched until ``execute_skill`` returns.

    Use as an async context manager::

        async with run_agui_stream(toolset, adapter) as stream:
            async for event in stream:
                ...

    Args:
        toolset: The SkillToolset whose sub-agents should stream events.
        adapter: An AGUIAdapter instance.
        **run_kwargs: Forwarded to ``adapter.run_stream()``.
    """
    return AguiEventStream(toolset, adapter, **run_kwargs)
