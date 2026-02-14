from pydantic_ai.mcp import MCPServer

from haiku.skills.models import Skill, SkillMetadata, SkillSource


def skill_from_mcp(
    server: MCPServer,
    *,
    name: str,
    description: str,
    instructions: str | None = None,
    allowed_tools: list[str] | None = None,
) -> Skill:
    """Create a Skill backed by an MCP server."""
    metadata = SkillMetadata(
        name=name,
        description=description,
        allowed_tools=allowed_tools or [],
    )
    return Skill(
        metadata=metadata,
        source=SkillSource.MCP,
        instructions=instructions,
        toolsets=[server],
    )
