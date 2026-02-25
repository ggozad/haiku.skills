# haiku.skills

[![Tests](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml/badge.svg)](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/ggozad/haiku.skills/graph/badge.svg)](https://codecov.io/gh/ggozad/haiku.skills)

Skill-powered AI agents implementing the [Agent Skills specification](https://agentskills.io/specification) with [pydantic-ai](https://ai.pydantic.dev/).

## How it works

`SkillToolset` is a pydantic-ai `FunctionToolset` that you attach to your own agent. It exposes a single `execute_skill` tool. When the agent calls it, a **focused sub-agent** spins up with only that skill's instructions and tools — then returns the result. The main agent never sees the skill's internal tools, so its tool space stays clean no matter how many skills you load.

This sub-agent architecture means each skill runs in isolation with its own system prompt, tools, and token budget. Skills don't interfere with each other, tool descriptions don't compete for attention, and failures in one skill can't confuse another.

## Features

- **Sub-agent execution** — Each skill runs in its own agent with dedicated instructions and tools
- **Skill discovery** — Scan filesystem paths for [SKILL.md](https://agentskills.io/specification) directories or load from Python entrypoints
- **In-process tools** — Attach pydantic-ai `Tool` functions or `AbstractToolset` instances to skills
- **Per-skill state** — Skills declare a Pydantic state model and namespace; state is passed to tools via `RunContext` and tracked on the toolset
- **AG-UI protocol** — State changes emit `StateDeltaEvent` (JSON Patch), compatible with the [AG-UI protocol](https://docs.ag-ui.com)
- **Script tools** — Python, JavaScript, TypeScript, and shell scripts in `scripts/`; Python scripts with a `main()` function are AST-parsed for typed tool schemas and executed via `uv run` with [PEP 723](https://peps.python.org/pep-0723/) dependency support
- **MCP integration** — Wrap any MCP server (stdio, SSE, streamable HTTP) as a skill

## Quick start

```bash
uv add haiku.skills
```

```python
from pathlib import Path
from pydantic_ai import Agent
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./skills")])
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=toolset.system_prompt,
    toolsets=[toolset],
)

result = await agent.run("Analyze this dataset.")
print(result.output)
```

## Documentation

Full documentation at [ggozad.github.io/haiku.skills](https://ggozad.github.io/haiku.skills/).

## License

MIT
