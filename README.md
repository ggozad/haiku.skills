# haiku.skills

[![Tests](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml/badge.svg)](https://github.com/ggozad/haiku.skills/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/ggozad/haiku.skills/graph/badge.svg)](https://codecov.io/gh/ggozad/haiku.skills)

A skill system for [pydantic-ai](https://ai.pydantic.dev/) agents, implementing the [Agent Skills specification](https://agentskills.io/specification).

Load skills from [SKILL.md](https://agentskills.io/specification) directories, Python entrypoints, or MCP servers and attach them to your agent as a `SkillsCapability` or `SkillToolset`. Skills run as isolated sub-agents by default, keeping your main agent's tool space clean regardless of how many skills you load.

## Quick start

```bash
uv add haiku.skills
```

```python
from pydantic_ai import Agent
from haiku.skills import SkillsCapability

agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    capabilities=[SkillsCapability(use_entrypoints=True)],
)

result = await agent.run("Analyze this dataset.")
print(result.output)
```

Or with explicit control over the toolset:

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
```

## How it works

Two execution modes:

- **Sub-agent mode** (default): exposes a single `execute_skill` tool. Each invocation spins up a focused sub-agent with only that skill's instructions, tools, and token budget. The main agent never sees skill internals.
- **Direct mode** (`use_subagents=False`): exposes skill tools directly to the main agent. No sub-agent LLM loops, lower latency, and the agent retains tool results in its conversation context.

## Skill sources

Skills are discovered automatically and can come from three sources:

- **Filesystem**: directories containing a [SKILL.md](https://agentskills.io/specification) file with scripts in Python, JavaScript, TypeScript, or shell
- **Entrypoints**: Python packages that register via the `haiku.skills` entry_points group, with typed in-process tools, per-skill Pydantic state, and zero-config discovery
- **MCP servers**: wrap any MCP server as a skill with `skill_from_mcp`

## Additional Features

- **Per-skill state**: Pydantic state models tracked per namespace; state deltas emitted as JSON Patch for the [AG-UI protocol](https://docs.ag-ui.com)
- **AG-UI streaming**: skill tool calls and state changes stream as `ActivitySnapshotEvent` and `StateDeltaEvent` for real-time UIs
- **Signing and verification**: identity-based skill signing via [sigstore](https://www.sigstore.dev/), verified at discovery time
- **CLI**: `haiku-skills list`, `validate`, `sign`, `verify`, and an interactive `chat` TUI

## Built-in skills

The repo ships several skill packages as references and for immediate use:

| Skill | Description |
|-------|-------------|
| `web` | Search (Brave) and fetch web pages with readability extraction |
| `code-execution` | Sandboxed Python execution via Monty |
| `image-generation` | Image generation with `await llm()` support |
| `gmail` | Gmail integration |
| `notifications` | System notifications |

Each is a standalone package: `uv add haiku-skills-web`, `uv add haiku-skills-code-execution`, etc. They register via the `haiku.skills` entrypoints group and are discovered automatically.

## Documentation

Full documentation at [ggozad.github.io/haiku.skills](https://ggozad.github.io/haiku.skills/).

## License

MIT
