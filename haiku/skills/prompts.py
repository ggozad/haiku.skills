DEFAULT_PREAMBLE = "You are a helpful assistant with access to specialized skills."

_MAIN_AGENT_PROMPT = """\
{preamble}

## Available skills

{skill_catalog}

## Instructions

- For general conversation or questions that don't need skills, respond directly
- Use execute_skill to delegate work to a skill. \
Include everything the skill needs in the request
- For multi-step tasks, call skills sequentially — pass results from earlier \
calls into later requests
- Skills cannot see each other's results unless you pass them explicitly\
"""

_MAIN_AGENT_PROMPT_WITH_TASKS = """\
{preamble}

## Available skills

{skill_catalog}

## Instructions

- For general conversation or questions that don't need skills, respond directly
- Use execute_skill to delegate work to a skill. \
Include everything the skill needs in the request
- Skills cannot see each other's results unless you pass them explicitly

## Multi-step orchestration

For complex requests that require multiple skills:

1. Decompose the request into tasks using `create_task`, specifying \
dependencies between them
2. Use `list_tasks` to review the plan
3. Work through tasks in dependency order — call `execute_skill` for each, \
then `update_task` with the result
4. Pass results from completed tasks into subsequent skill requests

For simple single-skill requests, call `execute_skill` directly without \
task overhead.\
"""


def build_system_prompt(
    skill_catalog: str,
    *,
    preamble: str = DEFAULT_PREAMBLE,
    with_tasks: bool = False,
) -> str:
    """Build the main agent system prompt from a skill catalog."""
    template = _MAIN_AGENT_PROMPT_WITH_TASKS if with_tasks else _MAIN_AGENT_PROMPT
    return template.format(preamble=preamble, skill_catalog=skill_catalog)


SKILL_PROMPT = """\
You are a focused execution agent. Complete the following task using the \
skills and instructions provided.

## Task

{task_description}

## Skill instructions

{skill_instructions}

{resource_section}{scripts_section}\
## Guidelines

- Follow the skill instructions carefully
- Stay focused on the specific task described above
- Provide a clear, complete result\
"""
