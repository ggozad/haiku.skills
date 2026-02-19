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

The `tui` extra includes `ag-ui-protocol`. The chat TUI uses the AG-UI protocol adapter for event streaming, making it useful for debugging skills with [per-skill state](skills.md#per-skill-state):

- **State deltas** are displayed inline as JSON Patch operations whenever a skill modifies state
- **Full state snapshot** is available via the "View state" modal in the command palette
