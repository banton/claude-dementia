#!/usr/bin/env python3
"""
MINIMAL MCP Server for Debugging Custom Connector Tool Visibility

PHASE 0: Absolute Minimum
- FastMCP only
- NO middleware
- NO auth
- NO session management
- NO custom routes
- NO CORS
- NO logging

Goal: Verify Custom Connector can discover tools with pure FastMCP
"""

import os
from claude_mcp_hybrid_sessions import mcp

# PHASE 0: Pure FastMCP - NO MIDDLEWARE AT ALL
print("=" * 60)
print("MINIMAL MCP SERVER - PHASE 0")
print("=" * 60)
print("FastMCP only - NO middleware, NO auth, NO routes")
print("Testing if Custom Connector can discover tools")
print("=" * 60)

# Get FastMCP's Starlette app (already has /mcp routes and lifespan)
app = mcp.streamable_http_app()

print(f"Routes registered: {len(app.routes)}")
for r in app.routes:
    if hasattr(r, 'path'):
        print(f"  - {r.path}")

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv('PORT', 8080))

    print(f"\nStarting server on port {port}...")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_config=None
    )
