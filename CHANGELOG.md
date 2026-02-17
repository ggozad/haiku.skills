# Changelog

## [Unreleased]

### Added

- **`haiku-skills list` command**: List discovered skills with name and description, supports `-s`/`--skill-path` and `--use-entrypoints`
- **`--skill` / `-k` option for `chat`**: Filter which skills to activate by name (repeatable)
- **RAG skill package** (`haiku-skills-rag`): Search, retrieve and analyze documents via haiku.rag with tools for hybrid search, document listing/retrieval, QA with citations, and code-execution analysis
- **Web skill package** (`haiku-skills-web`): Web search via Brave Search API and page content extraction via trafilatura (replaces `haiku-skills-brave-search`)

### Removed

- **Brave Search skill package** (`haiku-skills-brave-search`): Replaced by `haiku-skills-web`

## [0.1.0] - 2026-02-16

### Added

- **Core framework**: Skill-powered AI agents implementing the [Agent Skills specification](https://agentskills.io/specification) with pydantic-ai
- **Skill model**: Pydantic v2 models for skills, metadata, and tasks with full validation
- **SKILL.md parser**: YAML frontmatter + markdown body parsing following the Agent Skills spec
- **Skill discovery**: Filesystem scanning (directories containing SKILL.md) and Python entrypoint-based plugin discovery
- **SkillRegistry**: Central registry for skill discovery, loading, lookup, and activation
- **Progressive disclosure**: Three-level progressive disclosure — metadata at startup, instructions on activation, resources on demand
- **Sub-agent delegation**: Each skill runs in a focused sub-agent with its own system prompt and tools via `execute_skill`
- **SkillToolset**: `FunctionToolset` integration that exposes skills as tools for any pydantic-ai `Agent`
- **Script tools**: Python scripts in `scripts/` with `main()` function get AST-parsed into typed pydantic-ai `Tool` objects with automatic parameter schema extraction, executed via `uv run`
- **Resource reading**: Skills can expose files (references, assets, templates) as resources; sub-agents read them on demand via `read_resource` tool with path validation and traversal defense
- **MCP integration**: `skill_from_mcp()` maps MCP servers directly to skills
- **Chat TUI**: Terminal-based chat interface using Textual
- **Distributable skill packages**: Workspace members for brave-search, image-generation, and code-execution skills

[Unreleased]: https://github.com/ggozad/haiku.skills/compare/0.1.0...HEAD
[0.1.0]: https://github.com/ggozad/haiku.skills/releases/tag/0.1.0
