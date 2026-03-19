# Signing and verification

haiku.skills supports identity-based signing via [sigstore](https://www.sigstore.dev/). You decide which OIDC identities (email addresses, GitHub Actions workflows) you trust, and sigstore's transparency log proves the signature is authentic. No key management required.

## Installation

Signing requires the `signing` extra:

```bash
uv add "haiku.skills[signing]"
```

Or with pip:

```bash
pip install "haiku.skills[signing]"
```

Without this extra, skills load normally. Signing is entirely optional.

## Signing a skill

From the CLI:

```bash
haiku-skills sign ./skills/my-skill
```

Or programmatically:

```python
from pathlib import Path
from haiku.skills import sign_skill

sign_skill(Path("./skills/my-skill"))
```

This triggers an OIDC browser flow to authenticate your identity, then writes `SKILL.sigstore` into the skill directory. In CI environments with ambient OIDC credentials (e.g. GitHub Actions), the browser flow is skipped automatically.

### What gets signed

The hash covers all files in the skill directory except:

- `SKILL.sigstore` (the bundle itself)
- `__pycache__/` directories and `.pyc`/`.pyo` files
- `node_modules/` directories
- Hidden files and directories (starting with `.`)
- Files matching `.gitignore` patterns (walked up from the skill directory to the repository root)

Files are hashed in sorted order by relative path for determinism.

## Verifying skills

From the CLI:

```bash
haiku-skills verify ./skills/my-skill \
    -i author@example.com --issuer https://accounts.google.com
```

Programmatically, pass trusted identities to `SkillRegistry` or `discover()`:

```python
from pathlib import Path
from haiku.skills import SkillRegistry, TrustedIdentity

identities = [
    TrustedIdentity(
        identity="author@example.com",
        issuer="https://accounts.google.com",
    ),
]

registry = SkillRegistry(trusted_identities=identities)
errors = registry.discover(paths=[Path("./skills")])

for name in registry.names:
    skill = registry.get(name)
    print(f"{skill.metadata.name}: verified={skill.verified}")
```

The lower-level `verify_skill` function can also be used directly:

```python
from haiku.skills import TrustedIdentity, verify_skill

# Full verification (identity + integrity)
verify_skill(path, [TrustedIdentity(identity="...", issuer="...")])

# Integrity only
verify_skill(path, unsafe=True)
```

### Verification policy

| Scenario | Result |
|----------|--------|
| No trusted identities provided | Skill loads, `verified=False` |
| Identities provided, no `SKILL.sigstore` | Skill loads, `verified=False` |
| Identities provided, valid bundle | Skill loads, `verified=True` |
| Identities provided, invalid bundle | `SkillValidationError` (skill rejected) |

## GitHub Actions integration

Sigstore supports ambient OIDC credentials in GitHub Actions, no secrets needed. This workflow signs skills on push to main:

```yaml
name: Sign Skills
on:
  push:
    branches: [main]
    paths:
      - 'skills/**/SKILL.md'
      - 'skills/**/scripts/**'

permissions:
  id-token: write   # Required for sigstore OIDC
  contents: write    # Required to commit .sigstore bundles

jobs:
  sign:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5

      - run: uv sync --extra signing

      - name: Sign changed skills
        run: |
          for skill_dir in skills/*/; do
            if [ -f "$skill_dir/SKILL.md" ]; then
              uv run haiku-skills sign "$skill_dir"
            fi
          done

      - name: Commit signatures
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add skills/**/SKILL.sigstore
          git diff --cached --quiet || git commit -m "Sign skills [skip ci]"
          git push
```

The GitHub Actions OIDC identity will look like:

- **Identity**: `https://github.com/your-org/your-repo/.github/workflows/sign.yml@refs/heads/main`
- **Issuer**: `https://token.actions.githubusercontent.com`

Consumers verify against that workflow identity:

```python
TrustedIdentity(
    identity="https://github.com/your-org/your-repo/.github/workflows/sign.yml@refs/heads/main",
    issuer="https://token.actions.githubusercontent.com",
)
```

## FAQ

**What if I don't use signing?**
Unsigned skills load normally with `verified=False`.

**What about entrypoint and MCP skills?**
Signing currently applies to filesystem-discovered skills only. Entrypoint skills are verified by your package manager. MCP skills connect to running servers where signing doesn't apply.

**What happens if a signed skill is modified?**
The directory hash will no longer match the bundle, and verification will fail with a `SkillValidationError`. The skill will not load when trusted identities are configured.
