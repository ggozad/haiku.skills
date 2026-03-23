# haiku.skills

Skill-powered AI agents implementing the [Agent Skills specification](https://agentskills.io/specification) with [pydantic-ai](https://ai.pydantic.dev/).

## How it works

`SkillToolset` is a pydantic-ai `FunctionToolset` that you attach to your own agent. It exposes a single `execute_skill` tool. When the agent calls it, a **focused sub-agent** spins up with only that skill's instructions and tools — then returns the result. The main agent never sees the skill's internal tools, so its tool space stays clean no matter how many skills you load.

This sub-agent architecture means each skill runs in isolation with its own system prompt, tools, and token budget. Skills don't interfere with each other, tool descriptions don't compete for attention, and failures in one skill can't confuse another.

## Features

- **Sub-agent execution** — Each skill runs in its own agent with dedicated instructions and tools
- **Filesystem skills** — Load [SKILL.md](https://agentskills.io/specification) directories with scripts in Python, JavaScript, TypeScript, or shell
- **Entrypoint skills** — Install skill packages with typed in-process tools, per-skill state, and zero-config discovery
- **Per-skill state** — Pydantic state models tracked per namespace; state changes emit `StateDeltaEvent` (JSON Patch) for the [AG-UI protocol](https://docs.ag-ui.com)
- **MCP integration** — Wrap any MCP server (stdio, SSE, streamable HTTP) as a skill
- **Signing and verification** — Identity-based skill signing via [sigstore](https://www.sigstore.dev/)

## Quick install

```bash
uv add haiku.skills
```

## Documentation

- [Installation](installation.md) — Install with optional extras
- [Tutorial](tutorial.md) — From filesystem skills to entrypoint packages, step by step
- [Skills reference](skills.md) — SKILL.md format, tools, state, and script resolution
- [Signing](signing.md) — Identity-based signing and verification
- [CLI](cli.md) — Command-line interface reference
- [AG-UI protocol](ag-ui.md) — State deltas and the AG-UI protocol
- [Example skills](example-skills.md) — Built-in skill packages as reference implementations
- [Development](development.md) — Contributing, testing, and tooling
