# CLI

haiku.skills provides a `haiku-skills` command-line interface.

## `validate`

Validate skill directories against the [Agent Skills specification](https://agentskills.io/specification) using the reference implementation:

```bash
haiku-skills validate ./skills/web ./skills/calculator
```

Prints `VALID` or `INVALID` with error details for each path. Exits with code 1 if any skill is invalid.

## `sign`

Sign a skill directory with [sigstore](https://www.sigstore.dev/):

```bash
haiku-skills sign ./skills/my-skill
```

Writes a `SKILL.sigstore` bundle alongside the skill's `SKILL.md`. Each bundle carries exactly one signer; signing again overwrites the previous bundle. See [Signing and verification](signing.md) for details.

## `verify`

Verify a signed skill directory against trusted identities:

```bash
haiku-skills verify ./skills/my-skill \
    -i author@example.com --issuer https://accounts.google.com
```

Multiple identities can be provided (each `--identity`/`-i` needs a corresponding `--issuer`). Verification succeeds if the bundle's signer matches **any** of them:

```bash
haiku-skills verify ./skills/my-skill \
    -i author@example.com --issuer https://accounts.google.com \
    -i https://github.com/org/repo/.github/workflows/sign.yml@refs/heads/main \
    --issuer https://token.actions.githubusercontent.com
```

To verify cryptographic integrity without checking signer identity, pass `--unsafe`:

```bash
haiku-skills verify ./skills/my-skill --unsafe
```

Prints `VERIFIED` (or `INTEGRITY OK` with `--unsafe`) on success, `FAILED` on failure, and exits with code 1 on failure.

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

If any skill directories have validation errors, they are printed as warnings to stderr while valid skills are still listed.

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

The chat TUI uses the AG-UI protocol adapter for event streaming, making it useful for debugging skills with [per-skill state](skills.md#per-skill-state):

- **State deltas** are displayed inline as JSON Patch operations whenever a skill modifies state
- **Full state snapshot** is available via the "View state" modal in the command palette

## Environment variables

| Variable | Description |
|---|---|
| `HAIKU_SKILLS_MODEL` | Default main agent model for `chat` (fallback when `-m` is not provided, defaults to `ollama:gpt-oss`) |
| `HAIKU_SKILL_MODEL` | Model to use for skill sub-agents (overridden by `--skill-model` or per-skill `model` in SKILL.md) |
| `HAIKU_SKILLS_PATHS` | Colon-separated skill directory paths (fallback when `-s` is not provided) |
| `HAIKU_SKILLS_USE_ENTRYPOINTS` | Set to `1`, `true`, or `yes` to enable entrypoint discovery by default |
