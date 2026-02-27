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


def build_system_prompt(
    skill_catalog: str,
    *,
    preamble: str = DEFAULT_PREAMBLE,
) -> str:
    """Build the main agent system prompt from a skill catalog."""
    return _MAIN_AGENT_PROMPT.format(preamble=preamble, skill_catalog=skill_catalog)


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
