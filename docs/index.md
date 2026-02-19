# haiku.skills

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
- **Script tools** — Python scripts in `scripts/` with a `main()` function, discovered and executed via `uv run`
- **MCP integration** — Wrap any MCP server (stdio, SSE, streamable HTTP) as a skill

## Quick install

```bash
uv add haiku.skills
```

## Documentation

- [Installation](installation.md) — Install with optional extras
- [Quick start](quickstart.md) — Create a skill and use SkillToolset
- [Skills](skills.md) — SKILL.md format, tools, state, and script tools
- [Skill sources](skill-sources.md) — Filesystem, entrypoints, and MCP integration
- [Examples](examples.md) — Practical examples for each source type
- [CLI](cli.md) — Command-line interface reference
- [AG-UI protocol](ag-ui.md) — State deltas and the AG-UI protocol
- [Development](development.md) — Contributing, testing, and tooling
