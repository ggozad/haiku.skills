from typing import Any

from pydantic_ai.toolsets import AbstractToolset

from haiku.skills.models import Skill, SkillMetadata, SkillSource


def skill_from_mcp(
    toolset: AbstractToolset[Any],
    *,
    name: str,
    description: str,
    instructions: str | None = None,
    allowed_tools: list[str] | None = None,
) -> Skill:
    """Create a Skill backed by an MCP toolset.

    `toolset` is typically a `pydantic_ai.mcp.MCPToolset`, but any
    `AbstractToolset` is accepted.
    """
    metadata = SkillMetadata(
        name=name,
        description=description,
        allowed_tools=allowed_tools or [],
    )
    return Skill(
        metadata=metadata,
        source=SkillSource.MCP,
        instructions=instructions,
        toolsets=[toolset],
    )
