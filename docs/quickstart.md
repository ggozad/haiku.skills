# Quick start

## Creating a skill

A skill is a directory containing a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: my-skill
description: Helps with data analysis tasks.
---

# My Skill

Instructions for the agent go here...
```

See the [Agent Skills specification](https://agentskills.io/specification) for the full format.

## Using SkillToolset

```python
from pathlib import Path
from pydantic_ai import Agent
from haiku.skills import SkillToolset

toolset = SkillToolset(
    skill_paths=[Path("./skills")],
    skill_model="openai:gpt-4o-mini",   # optional: model to use for skill sub-agents
)
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=toolset.system_prompt,
    toolsets=[toolset],
)

result = await agent.run("Analyze this dataset.")
print(result.output)
```

`SkillToolset` discovers skills from the given paths, generates a system prompt listing available skills, and exposes a single `execute_skill` tool. When the agent decides to use a skill, a focused sub-agent handles the request with that skill's instructions and tools.
