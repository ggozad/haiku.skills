# CLI

haiku.skills provides a `haiku-skills` command-line interface.

## `validate`

Validate skill directories against the [Agent Skills specification](https://agentskills.io/specification) using the reference implementation:

```bash
haiku-skills validate ./skills/web ./skills/calculator
```

Prints `VALID` or `INVALID` with error details for each path. Exits with code 1 if any skill is invalid.

## `list`

List discovered skills with name and description:

```bash
# From filesystem paths
haiku-skills list -s ./skills

# From entrypoints
haiku-skills list --use-entrypoints

# Both
haiku-skills list -s ./skills --use-entrypoints
```

## `chat`

A debug/development chat TUI built with [Textual](https://textual.textualize.io/). Requires the `tui` extra:

```bash
uv add "haiku.skills[tui]"
```

Point it at a directory of skills for filesystem discovery:

```bash
haiku-skills chat -s ./skills -m openai:gpt-4o
```

Or use entrypoint discovery:

```bash
haiku-skills chat --use-entrypoints -m openai:gpt-4o
```

Filter to specific skills by name:

```bash
haiku-skills chat --use-entrypoints -k web -k code-execution -m openai:gpt-4o
```

Set the model to use for skill sub-agents (overrides `HAIKU_SKILL_MODEL` env var):

```bash
haiku-skills chat -s ./skills -m openai:gpt-4o --skill-model ollama:llama3
```

Enable task tools for multi-skill orchestration:

```bash
haiku-skills chat --use-entrypoints -m openai:gpt-4o --tasks
```

With `--tasks`, the agent gets `create_task`, `update_task`, and `list_tasks` tools to decompose complex multi-skill requests into tracked steps. Without it (the default), the agent calls skills directly.

The `tui` extra includes `ag-ui-protocol`. The chat TUI uses the AG-UI protocol adapter for event streaming, making it useful for debugging skills with [per-skill state](skills.md#per-skill-state):

- **State deltas** are displayed inline as JSON Patch operations whenever a skill modifies state
- **Full state snapshot** is available via the "View state" modal in the command palette

## Environment variables

| Variable | Description |
|---|---|
| `HAIKU_SKILLS_MODEL` | Default main agent model for `chat` (fallback when `-m` is not provided, defaults to `ollama:gpt-oss`) |
| `HAIKU_SKILL_MODEL` | Model to use for skill sub-agents (overridden by `--skill-model` or per-skill `model` in SKILL.md) |
| `HAIKU_SKILLS_PATHS` | Colon-separated skill directory paths (fallback when `-s` is not provided) |
| `HAIKU_SKILLS_USE_ENTRYPOINTS` | Set to `1`, `true`, or `yes` to enable entrypoint discovery by default |
