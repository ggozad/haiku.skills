# Signing and verification

haiku.skills supports identity-based signing via [sigstore](https://www.sigstore.dev/), the Linux Foundation's open-source signing framework. Signing lets consumers verify that a skill was published by a trusted identity.

## How it works

**Signing** (author-side):

1. Compute a deterministic SHA-256 hash of the skill directory contents
2. Sign the hash via sigstore using OIDC identity (browser login or CI ambient credentials)
3. Store the sigstore bundle as `SKILL.sigstore` alongside `SKILL.md`

**Verification** (consumer-side):

1. Recompute the directory hash
2. Verify the `SKILL.sigstore` bundle against a list of trusted identities
3. If valid, the skill loads with `verified=True`

The trust model is identity-based: you decide which OIDC identities (email addresses, GitHub Actions workflows) you trust, and sigstore's transparency log proves the signature is authentic.

## Installation

Signing requires the `signing` extra:

```bash
uv add "haiku.skills[signing]"
```

Or with pip:

```bash
pip install "haiku.skills[signing]"
```

Without this extra, skills load normally — signing and verification are entirely optional.

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

Or configure trusted identities when creating a registry:

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

for skill in registry.list():
    print(f"{skill.metadata.name}: verified={skill.verified}")
```

You can also pass `trusted_identities` directly to `discover()`:

```python
registry = SkillRegistry()
errors = registry.discover(
    paths=[Path("./skills")],
    trusted_identities=identities,
)
```

Or use the lower-level `verify_skill` function:

```python
from pathlib import Path
from haiku.skills import TrustedIdentity, verify_skill

result = verify_skill(
    Path("./skills/my-skill"),
    [TrustedIdentity(identity="author@example.com", issuer="https://accounts.google.com")],
)
```

To verify cryptographic integrity only (signature, certificate chain, transparency log) without constraining the signer identity, pass `unsafe=True`:

```python
result = verify_skill(Path("./skills/my-skill"), unsafe=True)
```

### Verification policy

| Scenario | Result |
|----------|--------|
| No trusted identities provided | Skill loads, `verified=False` |
| Identities provided, no `SKILL.sigstore` | Skill loads, `verified=False` |
| Identities provided, valid bundle | Skill loads, `verified=True` |
| Identities provided, invalid bundle | `SkillValidationError` — skill rejected |

## GitHub Actions integration

Sigstore supports ambient OIDC credentials in GitHub Actions — no secrets needed. This workflow signs skills automatically on push:

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
              uv run python -c "
          from haiku.skills.signing import sign_skill
          from pathlib import Path
          sign_skill(Path('$skill_dir'))
          "
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
Everything works exactly as before. Signing is opt-in — unsigned skills load normally with `verified=False`.

**What about entrypoint and MCP skills?**
Signing currently applies to filesystem-discovered skills only. Entrypoint skills are verified by your package manager. MCP skills connect to running servers where signing doesn't apply.

**What happens if a signed skill is modified?**
The directory hash will no longer match the bundle, and verification will fail with a `SkillValidationError`. The skill will not load when trusted identities are configured.
