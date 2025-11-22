#!/usr/bin/env python3
"""
ULTRA-MINIMAL MCP Server for Custom Connector Testing

PHASE 0: Absolute Bare Minimum
- Standalone FastMCP server (no imports from claude_mcp_hybrid_sessions)
- 3 simple test tools
- NO database
- NO auth/OAuth
- NO middleware
- NO session management
- NO dependencies on existing codebase

Goal: Verify Custom Connector can discover tools with pure FastMCP
"""

import os
from mcp.server.fastmcp import FastMCP

# Create standalone FastMCP server
mcp = FastMCP("test-server")

@mcp.tool()
def test_echo(message: str) -> str:
    """Echo a message back."""
    return f"Echo: {message}"

@mcp.tool()
def test_add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp.tool()
def test_hello(name: str = "World") -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

# Get FastMCP's Starlette app
app = mcp.streamable_http_app()

print("=" * 60)
print("ULTRA-MINIMAL MCP SERVER - PHASE 0")
print("=" * 60)
print("Standalone FastMCP with 3 test tools:")
print("  - test_echo")
print("  - test_add")
print("  - test_hello")
print("NO database, NO auth, NO middleware")
print("=" * 60)

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv('PORT', 8080))

    print(f"\nStarting server on port {port}...")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
