# haiku.skills

[![Tests](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml/badge.svg)](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/ggozad/haiku.skills/graph/badge.svg)](https://codecov.io/gh/ggozad/haiku.skills)

Skill-powered AI agents implementing the [Agent Skills specification](https://agentskills.io/specification) with [pydantic-ai](https://ai.pydantic.dev/).

## How it works

`SkillToolset` is a pydantic-ai `FunctionToolset` that you attach to your own agent. By default, it exposes a single `execute_skill` tool. When the agent calls it, a **focused sub-agent** spins up with only that skill's instructions and tools — then returns the result. The main agent never sees the skill's internal tools, so its tool space stays clean no matter how many skills you load.

Alternatively, `SkillToolset(use_subagents=False)` exposes skill tools directly to the main agent — no sub-agent LLM loops, lower latency, and the agent retains tool results in its conversation context.

## Features

- **Two execution modes** — Sub-agent delegation (default) for isolation, or direct tool access for speed and context retention
- **Filesystem skills** — Load [SKILL.md](https://agentskills.io/specification) directories with scripts in Python, JavaScript, TypeScript, or shell
- **Entrypoint skills** — Install skill packages with typed in-process tools, per-skill state, and zero-config discovery
- **Per-skill state** — Pydantic state models tracked per namespace; state changes emit `StateDeltaEvent` (JSON Patch) for the [AG-UI protocol](https://docs.ag-ui.com)
- **MCP integration** — Wrap any MCP server (stdio, SSE, streamable HTTP) as a skill
- **Signing and verification** — Identity-based skill signing via [sigstore](https://www.sigstore.dev/)

## Quick start

```bash
uv add haiku.skills
```

```python
from pathlib import Path
from pydantic_ai import Agent
from haiku.skills import SkillToolset, build_system_prompt

toolset = SkillToolset(skill_paths=[Path("./skills")])
agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    instructions=build_system_prompt(toolset.skill_catalog),
    toolsets=[toolset],
)

result = await agent.run("Analyze this dataset.")
print(result.output)
```

## Documentation

Full documentation at [ggozad.github.io/haiku.skills](https://ggozad.github.io/haiku.skills/).

## License

MIT
