# haiku.skills

A Python library for building skill-powered AI agents. Implements the [Agent Skills specification](https://agentskills.io/specification) and uses [pydantic-ai](https://ai.pydantic.dev/) for agent creation.

## Features

- Skill discovery via filesystem paths and Python entrypoints
- MCP server integration (each server maps to one skill)
- Task decomposition with dynamic sub-agents
- Progressive disclosure of skill instructions

## Installation

```bash
uv add haiku.skills
```

## License

MIT
