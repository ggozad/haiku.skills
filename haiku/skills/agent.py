import asyncio
import inspect
import json
import os
import shlex
import sys
from collections.abc import AsyncIterable, Awaitable, Callable
from pathlib import Path
from typing import Any

from ag_ui.core import (
    ActivitySnapshotEvent,
    BaseEvent,
    EventType,
)
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, Tool, ToolReturn, UsageLimits
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    RetryPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import FunctionToolset

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


def _events_to_activity(skill_name: str, events: list[Any]) -> list[BaseEvent]:
    """Convert pydantic-ai tool events to AG-UI ActivitySnapshotEvents.

    Args:
        skill_name: Skill name used to prefix message IDs.
        events: List of FunctionToolCallEvent/FunctionToolResultEvent.
    """
    result: list[BaseEvent] = []
    for event in events:
        if isinstance(event, FunctionToolCallEvent):
            args = event.part.args
            args_str = args if isinstance(args, str) else json.dumps(args or {})
            result.append(
                ActivitySnapshotEvent(
                    type=EventType.ACTIVITY_SNAPSHOT,
                    activity_type="skill_tool_call",
                    message_id=f"{skill_name}:{event.tool_call_id}",
                    replace=False,
                    content={
                        "skill": skill_name,
                        "tool_name": event.part.tool_name,
                        "tool_call_id": event.tool_call_id,
                        "args": args_str,
                    },
                )
            )
        elif isinstance(event, FunctionToolResultEvent):
            result.append(
                ActivitySnapshotEvent(
                    type=EventType.ACTIVITY_SNAPSHOT,
                    activity_type="skill_tool_result",
                    message_id=f"{skill_name}:{event.tool_call_id}",
                    replace=True,
                    content={
                        "skill": skill_name,
                        "tool_name": event.result.tool_name,
                        "tool_call_id": event.tool_call_id,
                        "result": event.result.model_response()
                        if isinstance(event.result, RetryPromptPart)
                        else event.result.model_response_str(),
                    },
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


def _discover_scripts(skill: Skill) -> list[str]:
    """List available scripts for a skill, as relative paths."""
    if not skill.path or not (skill.path / "scripts").is_dir():
        return []
    return sorted(
        str(f.relative_to(skill.path))
        for f in (skill.path / "scripts").rglob("*")
        if f.is_file()
        and f.name != "__init__.py"
        and (f.suffix in SCRIPT_RUNNERS or os.access(f, os.X_OK))
    )


SCRIPT_TIMEOUT_DEFAULT = 120.0


def _create_run_script(
    skill: Skill, timeout: float | None = None
) -> Callable[..., Any]:
    """Create a run_script tool bound to a specific skill."""
    assert skill.path is not None
    scripts_dir = (skill.path / "scripts").resolve()
    resolved_timeout = (
        timeout
        if timeout is not None
        else float(
            os.environ.get("HAIKU_SKILLS_SCRIPT_TIMEOUT", SCRIPT_TIMEOUT_DEFAULT)
        )
    )

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
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=resolved_timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"Script {script} timed out after {resolved_timeout}s")
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
) -> tuple[str, list[Any], list[BaseEvent]]:
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
        script_files = _discover_scripts(skill)
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
    emitted_events: list[BaseEvent] = []
    skill_name = skill.metadata.name

    def emit(event: BaseEvent) -> None:
        emitted_events.append(event)

    async def event_handler(
        ctx: RunContext[SkillRunDeps],
        events: AsyncIterable[AgentStreamEvent],
    ) -> None:
        async for event in events:
            if isinstance(event, (FunctionToolCallEvent, FunctionToolResultEvent)):
                if event_sink is not None:
                    for agui_event in _events_to_activity(skill_name, [event]):
                        await event_sink(agui_event)
                else:
                    collected_events.append(event)
            # Flush emitted events at tool-call boundaries
            if event_sink is not None:
                while emitted_events:
                    await event_sink(emitted_events.pop(0))

    deps = SkillRunDeps(state=state, emit=emit)
    agent = Agent[SkillRunDeps, str](
        model,
        system_prompt=system_prompt,
        tools=tools,
        toolsets=skill.toolsets or None,
    )
    model_settings = (
        ModelSettings(thinking=skill.thinking) if skill.thinking is not None else None
    )
    result = await agent.run(
        request,
        deps=deps,
        usage_limits=UsageLimits(request_limit=20),
        event_stream_handler=event_handler,
        model_settings=model_settings,
    )
    text = result.output
    return text, collected_events, emitted_events


class SkillToolset(FunctionToolset[Any]):
    """A toolset that exposes skills as tools for a pydantic-ai Agent."""

    def __init__(
        self,
        *,
        skills: list[Skill] | None = None,
        skill_paths: list[Path] | None = None,
        use_entrypoints: bool = False,
        skill_model: str | Model | None = None,
        use_subagents: bool = True,
    ) -> None:
        super().__init__()
        self._registry = SkillRegistry()
        self._namespaces: dict[str, BaseModel] = {}
        self._last_restored_state: dict[str, Any] | None = None
        self._skill_model = skill_model
        self._use_subagents = use_subagents
        self._skill_tool_cache: dict[str, dict[str, Tool]] = {}
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

    async def for_run(self, ctx: RunContext[Any]) -> "SkillToolset":
        """Restore AG-UI state from deps before the run starts.

        Uses identity check (``is``) so we restore once per AG-UI request
        (each request creates a new dict) but not redundantly within a run.
        """
        deps = ctx.deps
        if deps is not None and hasattr(deps, "state"):
            state = deps.state
            if (
                isinstance(state, dict)
                and state
                and state is not self._last_restored_state
            ):
                self._last_restored_state = state
                self.restore_state_snapshot(state)
        return self

    @property
    def use_subagents(self) -> bool:
        return self._use_subagents

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

    def _get_skill_tool_map(self, skill_name: str) -> dict[str, Tool]:
        """Get cached Tool instances for a skill's in-process tools."""
        if skill_name in self._skill_tool_cache:
            return self._skill_tool_cache[skill_name]
        skill = self._registry.get(skill_name)
        if skill is None:
            return {}
        result: dict[str, Tool] = {}
        for tool_or_callable in skill.tools:
            tool = (
                tool_or_callable
                if isinstance(tool_or_callable, Tool)
                else Tool(tool_or_callable)
            )
            result[tool.tool_def.name] = tool
        self._skill_tool_cache[skill_name] = result
        return result

    def _state_snapshot(
        self, skill: Skill
    ) -> tuple[str | None, BaseModel | None, dict[str, Any] | None]:
        """Capture state before a tool/skill execution."""
        namespace = skill.state_namespace
        state = self._namespaces.get(namespace) if namespace else None
        old_snapshot = (
            {namespace: state.model_dump(mode="json")} if namespace and state else None
        )
        return namespace, state, old_snapshot

    def _wrap_result(
        self,
        result: Any,
        namespace: str | None,
        state: BaseModel | None,
        old_snapshot: dict[str, Any] | None,
        metadata: list[BaseEvent],
    ) -> Any:
        """Append state delta to metadata and wrap in ToolReturn if needed."""
        if old_snapshot is not None and namespace and state:
            new_snapshot = {namespace: state.model_dump(mode="json")}
            delta = compute_state_delta(old_snapshot, new_snapshot)
            if delta is not None:
                metadata.append(delta)
        if metadata:
            return ToolReturn(return_value=result, metadata=metadata)
        return result

    def _register_tools(self) -> None:
        if self._use_subagents:
            self._register_subagent_tools()
        else:
            self._register_direct_tools()

    def _register_subagent_tools(self) -> None:
        registry = self._registry

        @self.tool
        async def execute_skill(
            ctx: RunContext[Any], skill_name: str, request: str
        ) -> str | ToolReturn:
            """Execute a skill by name.

            Skills are isolated agents — they cannot see the conversation or
            prior skill results. The request MUST contain all information the
            skill needs to complete its task.

            Args:
                skill_name: The exact name of the skill to use.
                request: Self-contained description including all data and
                    context the skill needs. Never reference external context.
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

            namespace, state, old_snapshot = self._state_snapshot(skill)
            event_sink = self._event_sink

            try:
                result, collected_events, emitted_events = await _run_skill(
                    skill_model, skill, request, state=state, event_sink=event_sink
                )
            except Exception as e:
                return f"Error: {e}"

            metadata: list[BaseEvent] = []
            if not event_sink:
                metadata.extend(
                    _events_to_activity(skill.metadata.name, collected_events)
                )
                metadata.extend(emitted_events)

            return self._wrap_result(result, namespace, state, old_snapshot, metadata)

    def _register_direct_tools(self) -> None:
        registry = self._registry

        @self.tool
        async def query_skill(ctx: RunContext[Any], skill_name: str) -> str:
            """Get details about a skill: instructions, available tools, and resources.

            Args:
                skill_name: The exact name of the skill to query.
            """
            skill = registry.get(skill_name)
            if skill is None:
                return f"Error: Skill '{skill_name}' not found in registry"

            sections: list[str] = []

            if skill.instructions:
                sections.append(f"## Instructions\n\n{skill.instructions}")

            tool_lines: list[str] = []
            for tool in self._get_skill_tool_map(skill_name).values():
                td = tool.tool_def
                desc = f" — {td.description}" if td.description else ""
                tool_lines.append(
                    f"- **{td.name}**{desc}\n"
                    f"  Schema: {json.dumps(td.parameters_json_schema)}"
                )

            for ts in skill.toolsets:
                ts_tools = await ts.get_tools(ctx)
                for name, ts_tool in ts_tools.items():
                    td = ts_tool.tool_def
                    desc = f" — {td.description}" if td.description else ""
                    tool_lines.append(
                        f"- **{name}**{desc}\n"
                        f"  Schema: {json.dumps(td.parameters_json_schema)}"
                    )

            if tool_lines:
                sections.append("## Tools\n\n" + "\n".join(tool_lines))

            script_files = _discover_scripts(skill)
            if script_files:
                script_list = "\n".join(f"- {s}" for s in script_files)
                sections.append(f"## Scripts\n\n{script_list}")

            if skill.resources:
                resource_list = "\n".join(f"- {r}" for r in skill.resources)
                sections.append(f"## Resources\n\n{resource_list}")

            return "\n\n".join(sections) if sections else "No details available."

        @self.tool
        async def execute_skill_tool(
            ctx: RunContext[Any],
            skill_name: str,
            tool_name: str,
            arguments: dict[str, Any],
        ) -> Any:
            """Call a specific tool from a skill.

            Use query_skill first to discover available tools and their schemas.

            Args:
                skill_name: The exact name of the skill.
                tool_name: The exact name of the tool to call.
                arguments: Tool arguments matching the tool's parameter schema.
            """
            skill = registry.get(skill_name)
            if skill is None:
                return f"Error: Skill '{skill_name}' not found in registry"

            namespace, state, old_snapshot = self._state_snapshot(skill)

            emitted_events: list[BaseEvent] = []

            def emit(event: BaseEvent) -> None:
                emitted_events.append(event)

            deps = SkillRunDeps(state=state, emit=emit)
            skill_ctx = RunContext(
                deps=deps,
                model=ctx.model,
                usage=ctx.usage,
                prompt=ctx.prompt,
                run_step=ctx.run_step,
            )

            try:
                result = await self._call_skill_tool(
                    skill, tool_name, arguments, skill_ctx
                )
            except Exception as e:
                return f"Error: {e}"

            metadata: list[BaseEvent] = []
            event_sink = self._event_sink
            if event_sink is not None:
                for ev in emitted_events:
                    await event_sink(ev)
            else:
                metadata.extend(emitted_events)

            return self._wrap_result(result, namespace, state, old_snapshot, metadata)

        @self.tool
        async def read_skill_resource(
            ctx: RunContext[Any], skill_name: str, path: str
        ) -> str:
            """Read a resource file from a skill's directory.

            Use query_skill first to discover available resources.

            Args:
                skill_name: The exact name of the skill.
                path: Relative path to the resource file.
            """
            skill = registry.get(skill_name)
            if skill is None:
                return f"Error: Skill '{skill_name}' not found in registry"
            if skill.path is None:
                return f"Error: Skill '{skill_name}' has no path"
            reader = _create_read_resource(skill)
            try:
                return await reader(path=path)
            except ValueError as e:
                return f"Error: {e}"

        @self.tool
        async def run_skill_script(
            ctx: RunContext[Any],
            skill_name: str,
            script: str,
            arguments: str = "",
        ) -> str:
            """Execute a script from a skill's scripts/ directory.

            Use query_skill first to discover available scripts.

            Args:
                skill_name: The exact name of the skill.
                script: Relative path to the script (e.g. 'scripts/extract.py').
                arguments: Command-line arguments for the script.
            """
            skill = registry.get(skill_name)
            if skill is None:
                return f"Error: Skill '{skill_name}' not found in registry"
            if skill.path is None or not (skill.path / "scripts").is_dir():
                return f"Error: Skill '{skill_name}' has no scripts"
            runner = _create_run_script(skill)
            try:
                return await runner(script=script, arguments=arguments)
            except (ValueError, RuntimeError) as e:
                return f"Error: {e}"

    async def _call_skill_tool(
        self,
        skill: Skill,
        tool_name: str,
        args: dict[str, Any],
        ctx: RunContext[SkillRunDeps],
    ) -> Any:
        """Call a tool by name from a skill's tools or toolsets."""
        tool_map = self._get_skill_tool_map(skill.metadata.name)
        if tool_name in tool_map:
            tool = tool_map[tool_name]
            func = tool.function
            if tool.takes_ctx:
                result = func(ctx, **args)
            else:
                result = func(**args)
            if inspect.isawaitable(result):
                result = await result
            return result

        for ts in skill.toolsets:
            ts_tools = await ts.get_tools(ctx)
            if tool_name in ts_tools:
                return await ts.call_tool(tool_name, args, ctx, ts_tools[tool_name])

        raise ValueError(
            f"Tool '{tool_name}' not found in skill '{skill.metadata.name}'"
        )


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
