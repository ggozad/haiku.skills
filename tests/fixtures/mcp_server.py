"""Minimal MCP server for integration testing."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("test-server")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@server.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    server.run(transport="stdio")
