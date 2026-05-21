import sys
from pathlib import Path

import pytest
from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

from haiku.skills.mcp import skill_from_mcp
from haiku.skills.models import SkillSource
from haiku.skills.registry import SkillRegistry

FIXTURES = Path(__file__).parent / "fixtures"


def _stub_stdio_toolset(
    command: str = "python", args: list[str] | None = None
) -> MCPToolset:
    """Build an MCPToolset wrapping a stdio transport that we never actually start."""
    return MCPToolset(StdioTransport(command=command, args=args or ["-m", "server"]))


class TestSkillFromMCP:
    def test_stdio_server(self):
        toolset = _stub_stdio_toolset(args=["-m", "some_mcp_server"])
        skill = skill_from_mcp(
            toolset,
            name="stdio-skill",
            description="A stdio skill.",
            instructions="Use this skill for stdio.",
        )
        assert skill.metadata.name == "stdio-skill"
        assert skill.metadata.description == "A stdio skill."
        assert skill.source == SkillSource.MCP
        assert skill.instructions == "Use this skill for stdio."
        assert skill.toolsets == [toolset]
        assert skill.path is None
        assert skill.tools == []

    def test_sse_server(self):
        toolset = MCPToolset("http://localhost:8000/sse")
        skill = skill_from_mcp(
            toolset,
            name="sse-skill",
            description="An SSE skill.",
        )
        assert skill.metadata.name == "sse-skill"
        assert skill.metadata.description == "An SSE skill."
        assert skill.source == SkillSource.MCP
        assert skill.toolsets == [toolset]
        assert skill.instructions is None

    def test_streamable_http_server(self):
        toolset = MCPToolset("http://localhost:8000/mcp")
        skill = skill_from_mcp(
            toolset,
            name="http-skill",
            description="A streamable HTTP skill.",
        )
        assert skill.metadata.name == "http-skill"
        assert skill.metadata.description == "A streamable HTTP skill."
        assert skill.source == SkillSource.MCP
        assert skill.toolsets == [toolset]

    def test_allowed_tools_passthrough(self):
        toolset = _stub_stdio_toolset()
        skill = skill_from_mcp(
            toolset,
            name="filtered-skill",
            description="A skill with allowed tools.",
            allowed_tools=["tool-a", "tool-b"],
        )
        assert skill.metadata.allowed_tools == ["tool-a", "tool-b"]

    def test_default_allowed_tools_empty(self):
        toolset = _stub_stdio_toolset()
        skill = skill_from_mcp(
            toolset,
            name="default-skill",
            description="A skill with default allowed tools.",
        )
        assert skill.metadata.allowed_tools == []

    def test_registry_integration(self):
        toolset = _stub_stdio_toolset()
        skill = skill_from_mcp(
            toolset,
            name="mcp-skill",
            description="An MCP skill.",
            instructions="Already loaded.",
        )
        registry = SkillRegistry()
        registry.register(skill)
        assert registry.get("mcp-skill") is skill
        assert skill.instructions == "Already loaded."

    def test_invalid_name_rejected(self):
        toolset = _stub_stdio_toolset()
        with pytest.raises(ValueError, match="lowercase"):
            skill_from_mcp(
                toolset,
                name="Invalid Name!",
                description="Bad name.",
            )


class TestMCPIntegration:
    """Integration tests that connect to a real MCP server via stdio."""

    def _toolset(self) -> MCPToolset:
        return MCPToolset(
            StdioTransport(
                command=sys.executable, args=[str(FIXTURES / "mcp_server.py")]
            ),
            init_timeout=10,
        )

    async def test_list_tools(self):
        toolset = self._toolset()
        skill = skill_from_mcp(toolset, name="math-skill", description="Math tools.")
        assert skill.toolsets[0] is toolset
        async with toolset:
            tools = await toolset.list_tools()
            names = {t.name for t in tools}
            assert "add" in names
            assert "greet" in names

    async def test_call_tool(self):
        toolset = self._toolset()
        skill_from_mcp(toolset, name="math-skill", description="Math tools.")
        async with toolset:
            result = await toolset.direct_call_tool("add", {"a": 3, "b": 4})
            assert result == 7

    async def test_call_greet_tool(self):
        toolset = self._toolset()
        skill_from_mcp(toolset, name="greeter", description="Greeting tools.")
        async with toolset:
            result = await toolset.direct_call_tool("greet", {"name": "Yiorgis"})
            assert result == "Hello, Yiorgis!"
