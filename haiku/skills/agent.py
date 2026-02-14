from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models import Model

from haiku.skills.models import AgentState, Skill, Task, TaskStatus
from haiku.skills.prompts import MAIN_AGENT_PROMPT, SKILL_PROMPT
from haiku.skills.registry import SkillRegistry


def _last_tool_result(messages: list[ModelMessage]) -> str | None:
    """Extract the content of the last tool return from messages."""
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, ToolReturnPart):
                    return part.model_response_str()
    return None


@dataclass
class AgentDeps:
    skill_agent: "SkillAgent"
    state: AgentState


async def _execute_skill(
    ctx: RunContext[AgentDeps], skill_name: str, request: str
) -> str:
    """Execute a skill by name.

    Args:
        skill_name: The exact name of the skill to use (from the available skills list).
        request: A clear description of what you need the skill to do.
    """
    state = ctx.deps.state
    task_id = str(len(state.tasks) + 1)
    task = Task(id=task_id, description=request, skill=skill_name)
    state.tasks.append(task)
    task.status = TaskStatus.IN_PROGRESS

    try:
        result = await ctx.deps.skill_agent._run_skill(skill_name, request)
        task.status = TaskStatus.COMPLETED
        task.result = result
        return result
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)
        return f"Error: {e}"


class SkillAgent:
    def __init__(self, model: Model, registry: SkillRegistry) -> None:
        self._model = model
        self._registry = registry
        catalog = self._build_skill_catalog()
        prompt = MAIN_AGENT_PROMPT.format(skill_catalog=catalog)
        self._agent = Agent[AgentDeps, str](
            model,
            system_prompt=prompt,
            tools=[_execute_skill],
            deps_type=AgentDeps,
        )
        self._history: list[ModelMessage] = []

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def skills(self) -> list[str]:
        return self._registry.names

    @property
    def history(self) -> list[ModelMessage]:
        return self._history

    def clear_history(self) -> None:
        self._history = []

    async def run(self, prompt: str, state: AgentState | None = None) -> str:
        if state is None:
            state = AgentState()
        deps = AgentDeps(skill_agent=self, state=state)
        result = await self._agent.run(prompt, deps=deps, message_history=self._history)
        self._history = list(result.all_messages())
        return result.output

    async def _run_skill(self, skill_name: str, request: str) -> str:
        skill = self._registry.get(skill_name)
        if skill is None:
            raise KeyError(f"Skill '{skill_name}' not found in registry")
        self._registry.activate(skill_name)

        instructions = skill.instructions or "No specific instructions."
        system_prompt = SKILL_PROMPT.format(
            task_description=request,
            skill_instructions=instructions,
        )
        agent = Agent[None, str](
            self._model,
            system_prompt=system_prompt,
            tools=skill.tools,
            toolsets=skill.toolsets or None,
        )
        result = await agent.run(
            request,
            usage_limits=UsageLimits(request_limit=10),
        )
        return _last_tool_result(result.all_messages()) or result.output

    def _build_skill_catalog(self) -> str:
        lines: list[str] = []
        for meta in self._registry.list_metadata():
            lines.append(f"- **{meta.name}**: {meta.description}")
        return "\n".join(lines)


def create_agent(
    model: Model,
    skills: list[Skill] | None = None,
    skill_paths: list[Path] | None = None,
    use_entrypoints: bool = False,
) -> SkillAgent:
    """Create a skill-powered agent."""
    registry = SkillRegistry()
    if skill_paths:
        registry.discover(paths=skill_paths)
    if use_entrypoints:
        registry.discover(use_entrypoints=True)
    if skills:
        for skill in skills:
            registry.register(skill)
    return SkillAgent(model=model, registry=registry)
