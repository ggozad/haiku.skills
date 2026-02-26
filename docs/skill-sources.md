# Skill sources

Skills can come from three sources: **filesystem** directories, Python **entrypoints**, and **MCP** servers. You can combine all three in a single `SkillToolset`:

```python
from pathlib import Path
from pydantic_ai.mcp import MCPServerStdio
from haiku.skills import SkillToolset, skill_from_mcp

mcp_skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
)

toolset = SkillToolset(
    skill_paths=[Path("./skills")],   # Filesystem
    use_entrypoints=True,              # Entrypoints
    skills=[mcp_skill],                # MCP (or any programmatic skill)
)
```

## Filesystem

A filesystem skill is a directory containing a `SKILL.md` file. `SkillToolset` scans the paths you provide and discovers all skill directories:

```python
from pathlib import Path
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./skills")])
```

If you point to a parent directory, all immediate subdirectories containing a `SKILL.md` are discovered. The directory name is used as the skill name (unless overridden in the frontmatter).

Filesystem skills automatically pick up:

- **Script tools** — Python scripts in a `scripts/` subdirectory (see [Skills — Script tools](skills.md#script-tools))
- **Resources** — Files listed in the `resources` frontmatter field (see [Skills — Resources](skills.md#resources))

## Entrypoints

Packages can expose skills via Python entrypoints, enabling automatic discovery without filesystem paths.

### Declaring entrypoints

Add an entry to the `haiku.skills` entrypoint group in your `pyproject.toml`:

```toml
[project.entry-points."haiku.skills"]
my-skill = "my_package.skills:create_my_skill"
```

The entrypoint must point to a callable that returns a `Skill`:

```python
from haiku.skills import Skill, SkillMetadata, SkillSource

def create_my_skill() -> Skill:
    return Skill(
        metadata=SkillMetadata(name="my-skill", description="Data analysis."),
        source=SkillSource.ENTRYPOINT,
        instructions="# My Skill\n\nInstructions here...",
    )
```

### Discovering entrypoint skills

Enable entrypoint discovery when creating a `SkillToolset`:

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(use_entrypoints=True)
```

The CLI also supports entrypoint discovery:

```bash
haiku-skills list --use-entrypoints
haiku-skills chat --use-entrypoints -m openai:gpt-4o
```

### Priority

Skills passed via `skills=` take priority over entrypoint-discovered skills. If a manually provided skill has the same name as an entrypoint skill, the entrypoint is silently skipped. This lets you override an entrypoint skill with a custom configuration:

```python
from haiku.skills import SkillToolset

custom_skill = create_my_skill(db_path="/custom/path")
toolset = SkillToolset(
    skills=[custom_skill],
    use_entrypoints=True,  # entrypoint for "my-skill" is skipped
)
```

## MCP

Any [MCP](https://modelcontextprotocol.io/) server can be wrapped as a skill using `skill_from_mcp`.

### Stdio servers

```python
from pydantic_ai.mcp import MCPServerStdio
from haiku.skills import skill_from_mcp

skill = skill_from_mcp(
    MCPServerStdio("uvx", args=["my-mcp-server"]),
    name="my-mcp-skill",
    description="Tools from my MCP server.",
    instructions="Use these tools when the user asks about...",
)
```

### SSE and streamable HTTP servers

```python
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP

# SSE
skill = skill_from_mcp(
    MCPServerSSE("http://localhost:8080/sse"),
    name="sse-skill",
    description="Tools via SSE.",
)

# Streamable HTTP
skill = skill_from_mcp(
    MCPServerStreamableHTTP("http://localhost:8080/mcp"),
    name="http-skill",
    description="Tools via streamable HTTP.",
)
```

### How it works

`skill_from_mcp` creates a `Skill` with the MCP server's toolset attached. When the skill is executed, the sub-agent connects to the MCP server and uses its tools directly. The MCP server's tools are only visible to the sub-agent — the main agent only sees the `execute_skill` tool.
