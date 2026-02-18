import sys
from pathlib import Path

import pytest
from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

from haiku.skills.mcp import skill_from_mcp
from haiku.skills.models import SkillSource
from haiku.skills.registry import SkillRegistry

FIXTURES = Path(__file__).parent / "fixtures"


class TestSkillFromMCP:
    def test_stdio_server(self):
        server = MCPServerStdio("python", args=["-m", "some_mcp_server"])
        skill = skill_from_mcp(
            server,
            name="stdio-skill",
            description="A stdio skill.",
            instructions="Use this skill for stdio.",
        )
        assert skill.metadata.name == "stdio-skill"
        assert skill.metadata.description == "A stdio skill."
        assert skill.source == SkillSource.MCP
        assert skill.instructions == "Use this skill for stdio."
        assert skill.toolsets == [server]
        assert skill.path is None
        assert skill.tools == []

    def test_sse_server(self):
        server = MCPServerSSE("http://localhost:8000/sse")
        skill = skill_from_mcp(
            server,
            name="sse-skill",
            description="An SSE skill.",
        )
        assert skill.metadata.name == "sse-skill"
        assert skill.metadata.description == "An SSE skill."
        assert skill.source == SkillSource.MCP
        assert skill.toolsets == [server]
        assert skill.instructions is None

    def test_streamable_http_server(self):
        server = MCPServerStreamableHTTP("http://localhost:8000/mcp")
        skill = skill_from_mcp(
            server,
            name="http-skill",
            description="A streamable HTTP skill.",
        )
        assert skill.metadata.name == "http-skill"
        assert skill.metadata.description == "A streamable HTTP skill."
        assert skill.source == SkillSource.MCP
        assert skill.toolsets == [server]

    def test_allowed_tools_passthrough(self):
        server = MCPServerStdio("python", args=["-m", "server"])
        skill = skill_from_mcp(
            server,
            name="filtered-skill",
            description="A skill with allowed tools.",
            allowed_tools=["tool-a", "tool-b"],
        )
        assert skill.metadata.allowed_tools == ["tool-a", "tool-b"]

    def test_default_allowed_tools_empty(self):
        server = MCPServerStdio("python", args=["-m", "server"])
        skill = skill_from_mcp(
            server,
            name="default-skill",
            description="A skill with default allowed tools.",
        )
        assert skill.metadata.allowed_tools == []

    def test_registry_integration(self):
        server = MCPServerStdio("python", args=["-m", "server"])
        skill = skill_from_mcp(
            server,
            name="mcp-skill",
            description="An MCP skill.",
            instructions="Already loaded.",
        )
        registry = SkillRegistry()
        registry.register(skill)
        assert registry.get("mcp-skill") is skill
        assert skill.instructions == "Already loaded."

    def test_invalid_name_rejected(self):
        server = MCPServerStdio("python", args=["-m", "server"])
        with pytest.raises(ValueError, match="lowercase alphanumeric"):
            skill_from_mcp(
                server,
                name="Invalid Name!",
                description="Bad name.",
            )


class TestMCPIntegration:
    """Integration tests that connect to a real MCP server via stdio."""

    def _server(self) -> MCPServerStdio:
        return MCPServerStdio(
            sys.executable,
            args=[str(FIXTURES / "mcp_server.py")],
            timeout=10,
        )

    async def test_list_tools(self):
        server = self._server()
        skill = skill_from_mcp(server, name="math-skill", description="Math tools.")
        assert skill.toolsets[0] is server
        async with server:
            tools = await server.list_tools()
            names = {t.name for t in tools}
            assert "add" in names
            assert "greet" in names

    async def test_call_tool(self):
        server = self._server()
        skill_from_mcp(server, name="math-skill", description="Math tools.")
        async with server:
            result = await server.direct_call_tool("add", {"a": 3, "b": 4})
            assert result == 7

    async def test_call_greet_tool(self):
        server = self._server()
        skill_from_mcp(server, name="greeter", description="Greeting tools.")
        async with server:
            result = await server.direct_call_tool("greet", {"name": "Yiorgis"})
            assert result == "Hello, Yiorgis!"
