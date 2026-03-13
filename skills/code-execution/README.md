# code-execution

Sandboxed Python code execution skill for [haiku.skills](https://github.com/ggozad/haiku.skills) using [pydantic-monty](https://github.com/pydantic/pydantic-monty).

Code runs in a minimal sandboxed interpreter with no file or network access. See the SKILL.md for full sandbox limitations.

## Tools

- **run_code** — Execute Python code in the sandbox and return the output

## Installation

```bash
uv add haiku-skills-code-execution
```
