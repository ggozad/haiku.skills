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

### AG-UI protocol support

For [AG-UI protocol](https://docs.ag-ui.com) compatibility (state deltas via JSON Patch):

```bash
uv add "haiku.skills[ag-ui]"
```

### Chat TUI

A debug/development chat interface built with [Textual](https://textual.textualize.io/):

```bash
uv add "haiku.skills[tui]"
```

## Requirements

- Python 3.12+
- [pydantic-ai](https://ai.pydantic.dev/) (installed automatically)
