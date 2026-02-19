# Development

## Setup

```bash
git clone https://github.com/ggozad/haiku.skills.git
cd haiku.skills
uv sync --all-extras
```

## Running tests

```bash
uv run pytest
```

With coverage (100% is required):

```bash
uv run pytest --cov
```

## VCR integration tests

Integration tests are recorded against Ollama and replayed from cassettes:

```bash
# Run from cassettes (default)
uv run pytest tests/test_integration.py

# Record new cassettes
uv run pytest tests/test_integration.py --record-mode=new_episodes
```

## Linting and formatting

```bash
uv run ruff check
uv run ruff format --check
```

## Type checking

```bash
uv run ty check
```

## Building docs

```bash
uv run mkdocs build --strict
uv run mkdocs serve  # Preview at http://127.0.0.1:8000
```
