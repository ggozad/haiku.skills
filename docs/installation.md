# Installation

## Basic

```bash
uv add haiku.skills
```

Or with pip:

```bash
pip install haiku.skills
```

## Extras

### Chat TUI

A debug/development chat interface built with [Textual](https://textual.textualize.io/):

```bash
uv add "haiku.skills[tui]"
```

### Signing

Identity-based skill signing and verification via [sigstore](https://www.sigstore.dev/):

```bash
uv add "haiku.skills[signing]"
```

See [Signing and verification](signing.md) for details.

## Requirements

- Python 3.12+
- [pydantic-ai](https://ai.pydantic.dev/) (installed automatically)
