#!/usr/bin/env python3
"""
Minimal Cloud-Hosted Dementia MCP Server

Ultra-simple HTTP wrapper for existing MCP tools.
Phase 1: Validate remote access works, then iterate.
"""

import os
import json
import time
import sys
import traceback
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional

# Import existing MCP server
from claude_mcp_hybrid import mcp

# Configuration
API_KEY = os.getenv('DEMENTIA_API_KEY')
VERSION = "4.2.0"

app = FastAPI(title="Dementia MCP Cloud", version=VERSION)

# Simple in-memory metrics (resets on restart)
metrics = {
    "requests_total": 0,
    "requests_success": 0,
    "requests_error": 0,
    "tools": {}  # {tool_name: {count, total_ms, errors}}
}

def log(event: str, level: str = "INFO", **kwargs):
    """JSON logger to stdout for DigitalOcean."""
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        **kwargs
    }), file=sys.stdout, flush=True)

# ============================================================================
# AUTH
# ============================================================================

def verify_api_key(authorization: str = Header(None)):
    """Simple bearer token validation."""
    if not API_KEY:
        return  # Auth disabled if no key set

    if not authorization:
        raise HTTPException(401, "Missing Authorization header")

    if not authorization.startswith('Bearer '):
        raise HTTPException(401, "Invalid Authorization format")

    token = authorization.replace('Bearer ', '')
    if token != API_KEY:
        raise HTTPException(401, "Invalid API key")

# ============================================================================
# MODELS
# ============================================================================

class ExecuteRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health():
    """Health check for DigitalOcean."""
    return {
        "status": "healthy",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/metrics")
async def get_metrics(authorization: str = Header(None)):
    """Simple metrics endpoint."""
    verify_api_key(authorization)

    # Calculate averages
    tool_stats = {}
    for tool_name, stats in metrics["tools"].items():
        avg_ms = stats["total_ms"] / stats["count"] if stats["count"] > 0 else 0
        tool_stats[tool_name] = {
            "count": stats["count"],
            "errors": stats["errors"],
            "avg_response_ms": round(avg_ms, 2)
        }

    return {
        "requests_total": metrics["requests_total"],
        "requests_success": metrics["requests_success"],
        "requests_error": metrics["requests_error"],
        "tools": tool_stats
    }

@app.get("/tools")
async def list_tools(authorization: str = Header(None)):
    """List available MCP tools."""
    verify_api_key(authorization)

    # Get tools from FastMCP tool manager
    tools_list = await mcp.list_tools()

    tools = []
    for tool in tools_list:
        tools.append({
            "name": tool.name,
            "description": tool.description or "No description"
        })

    return {"tools": tools, "count": len(tools)}

@app.post("/execute")
async def execute_tool(
    request: Request,
    body: ExecuteRequest,
    authorization: str = Header(None)
):
    """Execute MCP tool and return result."""
    verify_api_key(authorization)
    start_time = time.time()

    # Track request
    metrics["requests_total"] += 1

    # Initialize tool metrics
    if body.tool not in metrics["tools"]:
        metrics["tools"][body.tool] = {"count": 0, "total_ms": 0, "errors": 0}

    log("tool_execute_start", tool=body.tool, arguments=body.arguments)

    try:
        # Execute tool via FastMCP
        result = await mcp.call_tool(body.tool, body.arguments)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Update metrics
        metrics["requests_success"] += 1
        metrics["tools"][body.tool]["count"] += 1
        metrics["tools"][body.tool]["total_ms"] += latency_ms

        # Parse result (MCP tools return JSON strings)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except:
                pass  # Keep as string if not JSON

        log("tool_execute_success",
            tool=body.tool,
            latency_ms=round(latency_ms, 2))

        return {
            "success": True,
            "tool": body.tool,
            "result": result,
            "latency_ms": round(latency_ms, 2)
        }

    except Exception as e:
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Update metrics
        metrics["requests_error"] += 1
        metrics["tools"][body.tool]["errors"] += 1

        # Log detailed error
        log("tool_execute_error",
            level="ERROR",
            tool=body.tool,
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
            latency_ms=round(latency_ms, 2))

        raise HTTPException(500, f"Tool execution failed: {str(e)}")

# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv('PORT', 8080))

    log("server_start",
        port=port,
        version=VERSION,
        auth_enabled=bool(API_KEY))

    uvicorn.run(app, host="0.0.0.0", port=port)
