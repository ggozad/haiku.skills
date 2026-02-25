# Changelog

## [Unreleased]

### Added

- **`skill_model` parameter**: `SkillToolset` accepts `skill_model` to set the model for skill sub-agents (also available as `--skill-model` CLI option)
- **`resolve_model()`**: Resolves model strings with transparent `ollama:` prefix handling (defaults to `http://127.0.0.1:11434/v1` when `OLLAMA_BASE_URL` is unset)
- **`run_script` tool**: Skill sub-agents can execute scripts from the skill's `scripts/` directory via a `run_script` tool, supporting `.py`, `.sh`, and generic executables with path validation

### Changed

- **Script tool execution**: Scripts are now invoked with CLI positional arguments (`sys.argv` + `print()`) instead of JSON on stdin/stdout, matching standard CLI conventions and enabling compatibility with external skill scripts
- **Resilient script discovery**: `discover_script_tools()` now skips scripts without a `main()` function (with a warning) instead of crashing

### Fixed

- **Script failure error reporting**: Script error messages now include stdout when stderr is empty, so usage messages and other stdout-based errors are visible to the sub-agent
- **Script sibling imports**: `run_script` now sets `PYTHONPATH` to the skill directory so scripts can use package-style imports (e.g. `from scripts.utils import ...`)

## [0.4.2] - 2026-02-20

### Added

- **`SkillDeps`**: Minimal dataclass satisfying pydantic-ai's `StateHandler` protocol for type-correct AG-UI state round-tripping (replaces `StateDeps[dict[str, Any]]` recommendation in docs)

## [0.4.1] - 2026-02-20

## [0.4.1] - 2026-02-20

### Fixed

- **AG-UI state restoration**: `SkillToolset` now restores skill namespace state from frontend-provided `deps.state` on each AG-UI request, so state survives server restarts

### Removed

- **RAG skill package** (`haiku-skills-rag`): Moved to [haiku.rag](https://github.com/ggozad/haiku.rag)

## [0.4.0] - 2026-02-19

### Added

- **`haiku-skills validate` command**: Validate skill directories against the Agent Skills specification using `skills-ref`
- **Unknown frontmatter rejection**: `SkillMetadata` now rejects unknown fields (`extra="forbid"`)
- **`skills-ref` dependency**: Reference implementation used for spec-compliant validation

### Changed

- **Distributable skill directory layout**: SKILL.md moved into a subdirectory matching the skill name (e.g. `haiku_skills_web/web/SKILL.md`) so all bundled skills pass directory-name validation

## [0.3.0] - 2026-02-19

### Added

- **`haiku-skills list` command**: List discovered skills with name and description, supports `-s`/`--skill-path` and `--use-entrypoints`
- **`--skill` / `-k` option for `chat`**: Filter which skills to activate by name (repeatable)
- **RAG skill package** (`haiku-skills-rag`): Search, retrieve and analyze documents via haiku.rag with tools for hybrid search, document listing/retrieval, QA with citations, and code-execution analysis
- **Web skill package** (`haiku-skills-web`): Web search via Brave Search API and page content extraction via trafilatura (replaces `haiku-skills-brave-search`)
- **Per-skill state**: Skills can declare a `state_type` (Pydantic `BaseModel`) and `state_namespace`; state is passed to tool functions via `RunContext[SkillRunDeps]` and tracked per namespace on the toolset
- **AG-UI protocol**: `SkillToolset` emits `StateDeltaEvent` (JSON Patch) when skill execution changes state, compatible with the [AG-UI protocol](https://docs.ag-ui.com)
- **State API on `SkillToolset`**: `build_state_snapshot()`, `restore_state_snapshot()`, `get_namespace()`, `state_schemas`
- **In-process tools with state**: Distributable skills (web, image-generation, code-execution, rag) converted from script-based to in-process tool functions that can read and write per-skill state

### Changed

- **Skills fully loaded at discovery**: Instructions, script tools, and resources are loaded when skills are discovered, removing the separate activation step
- **Chat TUI rewritten as AG-UI client**: Uses `AGUIAdapter` event stream instead of polling; inline state delta display and a "View state" modal via the command palette
- **Skill name validation**: Now accepts unicode lowercase alphanumeric characters per the Agent Skills specification (previously ASCII-only)
- **Documentation site**: Published at [ggozad.github.io/haiku.skills](https://ggozad.github.io/haiku.skills/) with MkDocs Material

### Removed

- **Brave Search skill package** (`haiku-skills-brave-search`): Replaced by `haiku-skills-web`
- **`SkillRegistry.activate()`**: Skills are fully loaded at discovery time; progressive disclosure removed
- **`Task` / `TaskStatus`**: Task tracking removed from `SkillToolset`; the AG-UI adapter provides tool call progress via events

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
- **Script tools**: Python scripts in `scripts/` with `main()` function get AST-parsed into typed pydantic-ai `Tool` objects with automatic parameter schema extraction
- **Resource reading**: Skills can expose files (references, assets, templates) as resources; sub-agents read them on demand via `read_resource` tool with path validation and traversal defense
- **MCP integration**: `skill_from_mcp()` maps MCP servers directly to skills
- **Chat TUI**: Terminal-based chat interface using Textual
- **Distributable skill packages**: Workspace members for brave-search, image-generation, and code-execution skills

[Unreleased]: https://github.com/ggozad/haiku.skills/compare/0.4.2...HEAD
[0.4.2]: https://github.com/ggozad/haiku.skills/compare/0.4.1...0.4.2
[0.4.1]: https://github.com/ggozad/haiku.skills/compare/0.4.1...0.4.1
[0.4.1]: https://github.com/ggozad/haiku.skills/compare/0.4.0...0.4.1
[0.4.0]: https://github.com/ggozad/haiku.skills/compare/0.3.0...0.4.0
[0.3.0]: https://github.com/ggozad/haiku.skills/compare/0.1.0...0.3.0
[0.1.0]: https://github.com/ggozad/haiku.skills/releases/tag/0.1.0
