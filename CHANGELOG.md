# Changelog

## [Unreleased]

### Added

- **Custom event emission from skill tools**: `SkillRunDeps` now has an `emit` callback that skill tools can use to emit AG-UI `BaseEvent` subclasses (e.g. `CustomEvent`) during execution. Events are flushed through the event sink at tool-call boundaries (real-time path) or returned in `ToolReturn.metadata` (batched path).
- **Gmail skill** (`haiku-skills-gmail`): Search, read, send, reply, draft, and label Gmail emails via the Google Gmail API with OAuth2 authentication
- **Notifications skill** (`haiku-skills-notifications`): Send and receive push notifications via [ntfy.sh](https://ntfy.sh/) — with `send_notification` and `read_notifications` tools, per-skill state tracking, self-hosted server support, and optional bearer token authentication

### Removed

- **Graphiti memory skill** (`haiku-skills-graphiti-memory`): Removed the knowledge graph memory skill and all associated code, tests, and configuration

## [0.8.0] - 2026-03-13

### Changed

- **code-execution skill**: Updated pydantic-monty to >=0.0.8, rewritten SKILL.md sandbox limitations to reflect new capabilities (math, re, os.environ, getattr, dataclass methods, PEP 448 unpacking)
- Sub-agent tool events emitted as `ActivitySnapshotEvent` instead of `ToolCall*` events, fixing AG-UI history replay crashes in conforming clients (CopilotKit/soliplex)

## [0.7.5] - 2026-03-12

### Fixed

- **`_events_to_agui` crash on `RetryPromptPart`**: Handle `RetryPromptPart` results in `FunctionToolResultEvent` by calling `.model_response()` instead of `.model_response_str()` which doesn't exist on retry parts ([#35](https://github.com/ggozad/haiku.skills/issues/35))

## [0.7.4] - 2026-03-06

### Changed

- **Main agent prompt**: Emphasize that skills are isolated agents with no shared context — the main agent must include concrete data when chaining skills and must synthesize skill responses for the user

## [0.7.3] - 2026-03-06

## [0.7.2] - 2026-03-06

### Fixed

- **Missing `openai` extra in core dependency**: `pydantic-ai-slim[mcp]` → `pydantic-ai-slim[mcp,openai]` — most users hit `ImportError: Please install openai` on first use
- **CLI unusable without `[tui]` extra**: `typer` and `python-dotenv` are now lazy-loaded with a friendly error message instead of crashing with `ModuleNotFoundError`

## [0.7.1] - 2026-03-06

### Added

- **Independent skill package publishing**: Skill packages (`haiku-skills-web`, etc.) can now be published to PyPI independently from the core package using `skills-v*` release tags ([#27](https://github.com/ggozad/haiku.skills/issues/27))
- **Bump script updates skill packages**: `bump_version.py` now updates version and `haiku.skills>=` dependency constraint in all `skills/*/pyproject.toml` files
- **Skill package PyPI metadata**: All 4 skill packages now include authors, license, readme, keywords, classifiers, and project URLs
- **Skill package READMEs**: `haiku-skills-web`, `haiku-skills-image-generation`, and `haiku-skills-code-execution` now have READMEs with prerequisites, configuration, tools, and installation instructions

### Fixed

- **Missing core dependencies**: `ag-ui-protocol` and `jsonpatch` moved from optional `[ag-ui]` extra to core dependencies — a clean install of `haiku.skills` no longer fails with `ModuleNotFoundError: No module named 'ag_ui'`
- **graphiti-memory recall returns empty results**: Switch `recall()` and `forget()` from `client.search()` to `client.search_()` with BM25 + cosine + BFS graph traversal, RRF reranking, and `sim_min_score=0.0` so cosine always returns candidates for BFS to expand on
- **graphiti-memory cross-encoder crash**: `_build_cross_encoder()` now passes an `AsyncOpenAI` client directly to `OpenAIRerankerClient` instead of the graphiti `OpenAIGenericClient` wrapper, which lacked the `.chat` attribute the reranker needs

### Changed

- **`generate_image` returns file path**: The image generation tool now returns the file path directly instead of a markdown image reference
- **Main agent prompt**: Instructs the agent to present skill results exactly as returned, without fabricating or rewriting content

## [0.7.0] - 2026-03-04

### Changed

- **`discover_from_paths` collects all validation errors**: Returns `tuple[list[Skill], list[SkillValidationError]]` instead of raising on the first broken skill — valid skills are still loaded while errors are collected ([#25](https://github.com/ggozad/haiku.skills/issues/25))
- **`SkillRegistry.discover` returns errors**: Returns `list[SkillValidationError]` instead of `None`, propagating errors from `discover_from_paths`
- **CLI prints discovery warnings**: `list` and `chat` commands print validation errors as warnings to stderr instead of aborting

### Added

- **`SkillValidationError`**: `ValueError` subclass with a `.path` attribute, exported from `haiku.skills`
- **`StateMetadata`**: Frozen dataclass with `namespace`, `type`, and `schema` fields, exported from `haiku.skills`
- **`Skill.state_metadata()`**: Returns a `StateMetadata` for skills that declare state; `None` otherwise

## [0.6.0] - 2026-03-03

### Added

- **Real-time sub-agent event streaming**: `run_agui_stream()` merges main-agent and sub-agent AG-UI events into a single stream, so sub-agent tool calls (search, fetch, etc.) appear in real-time instead of batching until `execute_skill` returns

### Changed

- **Sub-agent output**: `_run_skill` now returns the model's final response (`result.output`) instead of the last tool's raw return value — state and structured data are already handled via the snapshot/delta mechanism
- **Event sink on `SkillToolset`**: `_run_skill` accepts an optional `event_sink` callback; when active, sub-agent tool events stream through the sink immediately rather than collecting in batch
- **`SkillRunDeps` simplified**: Removed `_collected_events` field — event collection is now closure-based inside `_run_skill`

## [0.5.2] - 2026-03-02

### Added

- **Graphiti memory skill** (`haiku-skills-graphiti-memory`): Store, recall, and forget memories using a knowledge graph powered by [Graphiti](https://github.com/getzep/graphiti) and [FalkorDB](https://www.falkordb.com/) — with per-skill state tracking

### Changed

- **`SkillMetadata.allowed_tools` accepts strings**: Now accepts both `str` (space-separated) and `list[str]` as input, always stores `list[str]` — eliminates conversion overhead for consumers using the spec's string format ([#19](https://github.com/ggozad/haiku.skills/issues/19))
- **`Skill.model` accepts `Model` instances**: Widened from `str | None` to `str | Model | None` so consumers can pass configured model objects directly ([#20](https://github.com/ggozad/haiku.skills/issues/20))
- **`discover_from_paths` accepts single-skill directories**: Paths that contain `SKILL.md` directly are now treated as skill directories, in addition to parent directories containing skill subdirectories. Dot-directories are skipped during child iteration.

### Fixed

- **Ollama base URL handling**: `resolve_model()` now appends `/v1` to `OLLAMA_BASE_URL` instead of expecting it in the env var, consistent with Ollama's convention
- **Web skill `fetch_page` for non-HTML content**: Pages with non-HTML content types (e.g. plain text, markdown) are now returned directly instead of failing with "could not extract content"

## [0.5.1] - 2026-02-27

### Added

- **`build_system_prompt()` utility**: Standalone function to build the main agent system prompt from a skill catalog, with optional custom preamble — replaces `SkillToolset.system_prompt` property

### Changed

- **Entrypoint skill priority**: Skills passed via `skills=` now take priority over entrypoint-discovered skills — entrypoints with the same name are silently skipped instead of raising a duplicate error
- **Sub-agent request limit**: Increased from 10 to 20 to allow skills with more complex tool chains to complete
- **Chat TUI tool call display**: Tool call widgets now stream argument updates and show richer descriptions (e.g. `execute_skill → web: search for ...`)

### Removed

- **`SkillToolset.system_prompt`**: Use `build_system_prompt(toolset.skill_catalog)` instead

## [0.5.0] - 2026-02-25

### Added

- **`skill_model` parameter**: `SkillToolset` accepts `skill_model` to set the model for skill sub-agents (also available as `--skill-model` CLI option)
- **`resolve_model()`**: Resolves model strings with transparent `ollama:` prefix handling (defaults to `http://127.0.0.1:11434` when `OLLAMA_BASE_URL` is unset)
- **`run_script` tool**: Skill sub-agents can execute scripts from the skill's `scripts/` directory via a `run_script` tool, supporting `.py`, `.sh`, `.js`, `.ts`, and generic executables with path validation
- **JS/TS script support**: `run_script` dispatches `.js` files via `node` and `.ts` files via `npx tsx`; extensible via `SCRIPT_RUNNERS` mapping

### Changed

- **Script tool execution**: Scripts are now invoked with CLI positional arguments (`sys.argv` + `print()`) instead of JSON on stdin/stdout, matching standard CLI conventions and enabling compatibility with external skill scripts
- **Resilient script discovery**: `discover_script_tools()` now skips scripts without a `main()` function (with a warning) instead of crashing

### Fixed

- **Script failure error reporting**: Script error messages now include stdout when stderr is empty, so usage messages and other stdout-based errors are visible to the sub-agent
- **Script sibling imports**: `run_script` and typed script tools now set `PYTHONPATH` to the skill directory so scripts can use package-style imports (e.g. `from scripts.utils import ...`)

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

[Unreleased]: https://github.com/ggozad/haiku.skills/compare/0.8.0...HEAD
[0.8.0]: https://github.com/ggozad/haiku.skills/compare/0.7.5...0.8.0
[0.7.5]: https://github.com/ggozad/haiku.skills/compare/0.7.4...0.7.5
[0.7.4]: https://github.com/ggozad/haiku.skills/compare/0.7.3...0.7.4
[0.7.3]: https://github.com/ggozad/haiku.skills/compare/0.7.2...0.7.3
[0.7.2]: https://github.com/ggozad/haiku.skills/compare/0.7.1...0.7.2
[0.7.1]: https://github.com/ggozad/haiku.skills/compare/0.7.0...0.7.1
[0.7.0]: https://github.com/ggozad/haiku.skills/compare/0.6.0...0.7.0
[0.6.0]: https://github.com/ggozad/haiku.skills/compare/0.5.2...0.6.0
[0.5.2]: https://github.com/ggozad/haiku.skills/compare/0.5.1...0.5.2
[0.5.1]: https://github.com/ggozad/haiku.skills/compare/0.5.0...0.5.1
[0.5.0]: https://github.com/ggozad/haiku.skills/compare/0.4.2...0.5.0
[0.4.2]: https://github.com/ggozad/haiku.skills/compare/0.4.1...0.4.2
[0.4.1]: https://github.com/ggozad/haiku.skills/compare/0.4.1...0.4.1
[0.4.1]: https://github.com/ggozad/haiku.skills/compare/0.4.0...0.4.1
[0.4.0]: https://github.com/ggozad/haiku.skills/compare/0.3.0...0.4.0
[0.3.0]: https://github.com/ggozad/haiku.skills/compare/0.1.0...0.3.0
[0.1.0]: https://github.com/ggozad/haiku.skills/releases/tag/0.1.0
