#!/usr/bin/env python3
"""
Production Cloud-Hosted Dementia MCP Server

Production-grade HTTP wrapper with:
- Structured logging (structlog)
- Prometheus metrics
- Bearer token authentication
- Correlation ID tracking
"""

import os
import json
import time
import traceback
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Dict, Any

# Import existing MCP server
from claude_mcp_hybrid import mcp

# Import production infrastructure
from src.logging_config import configure_logging, get_logger
from src.metrics import (
    track_tool_execution,
    active_connections,
    get_metrics_text,
    tool_invocations,
    request_size_bytes,
    response_size_bytes
)
from src.middleware.auth import (
    BearerTokenAuth,
    CorrelationIdMiddleware,
    get_current_user,
    get_current_project
)

# Configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
VERSION = "4.3.0"

# Configure structured logging
configure_logging(environment=ENVIRONMENT, log_level=LOG_LEVEL)
logger = get_logger(__name__)

# ============================================================================
# LIFECYCLE EVENTS
# ============================================================================

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler (startup/shutdown)."""
    # Startup
    active_connections.inc()
    logger.info("server_startup",
                version=VERSION,
                environment=ENVIRONMENT,
                log_level=LOG_LEVEL)

    yield

    # Shutdown
    active_connections.dec()
    logger.info("server_shutdown", version=VERSION)

# Initialize FastAPI with lifespan and middleware
app = FastAPI(title="Dementia MCP Cloud", version=VERSION, lifespan=lifespan)

# Add correlation ID middleware (must be first)
app.add_middleware(CorrelationIdMiddleware)

# Initialize bearer token auth
bearer_auth = BearerTokenAuth()

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
    """Health check for DigitalOcean (unauthenticated)."""
    return {
        "status": "healthy",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/metrics")
async def metrics_endpoint(credentials = Depends(bearer_auth)):
    """Prometheus metrics endpoint (authenticated)."""
    data, content_type = get_metrics_text()
    return Response(content=data, media_type=content_type)

@app.get("/tools")
async def list_tools(
    request: Request,
    credentials = Depends(bearer_auth)
):
    """List available MCP tools (authenticated)."""
    user_id = get_current_user(credentials) if credentials else "anonymous"
    correlation_id = request.state.correlation_id

    logger.info("list_tools_start",
                user_id=user_id,
                correlation_id=correlation_id)

    # Get tools from FastMCP tool manager
    tools_list = await mcp.list_tools()

    tools = []
    for tool in tools_list:
        tools.append({
            "name": tool.name,
            "description": tool.description or "No description"
        })

    logger.info("list_tools_success",
                user_id=user_id,
                tool_count=len(tools),
                correlation_id=correlation_id)

    return {"tools": tools, "count": len(tools)}

@app.post("/execute")
async def execute_tool(
    request: Request,
    body: ExecuteRequest,
    credentials = Depends(bearer_auth)
):
    """Execute MCP tool and return result (authenticated)."""
    start_time = time.time()

    # Extract context
    user_id = get_current_user(credentials) if credentials else "anonymous"
    project_id = get_current_project(request)
    correlation_id = request.state.correlation_id

    # Track request size
    request_body = await request.body()
    request_size_bytes.observe(len(request_body))

    logger.info("tool_execute_start",
                tool=body.tool,
                user_id=user_id,
                project_id=project_id,
                correlation_id=correlation_id,
                arguments=body.arguments)

    try:
        # Execute tool via FastMCP
        result = await mcp.call_tool(body.tool, body.arguments)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Update Prometheus metrics
        tool_invocations.labels(tool=body.tool, status="success").inc()

        # Convert MCP result to JSON-serializable format
        # FastMCP returns list of TextContent or other MCP types
        if isinstance(result, list):
            # Extract text from TextContent objects
            serialized_result = []
            for item in result:
                if hasattr(item, 'text'):
                    # Parse JSON if possible
                    try:
                        serialized_result.append(json.loads(item.text))
                    except:
                        serialized_result.append(item.text)
                elif hasattr(item, 'model_dump'):
                    serialized_result.append(item.model_dump())
                else:
                    serialized_result.append(str(item))
            result = serialized_result[0] if len(serialized_result) == 1 else serialized_result
        elif isinstance(result, str):
            # Try to parse JSON strings
            try:
                result = json.loads(result)
            except:
                pass  # Keep as string if not JSON
        elif hasattr(result, 'text'):
            # Single TextContent object
            try:
                result = json.loads(result.text)
            except:
                result = result.text
        elif hasattr(result, 'model_dump'):
            result = result.model_dump()

        response_data = {
            "success": True,
            "tool": body.tool,
            "result": result,
            "latency_ms": round(latency_ms, 2)
        }

        # Track response size with fallback for any remaining non-serializable objects
        try:
            response_json = json.dumps(response_data)
        except TypeError as e:
            # Fallback: convert entire result to string if still not serializable
            logger.warning("json_serialization_fallback", error=str(e), result_type=str(type(result)))
            response_data["result"] = str(result)
            response_json = json.dumps(response_data)
        response_size_bytes.observe(len(response_json))

        logger.info("tool_execute_success",
                    tool=body.tool,
                    user_id=user_id,
                    project_id=project_id,
                    correlation_id=correlation_id,
                    latency_ms=round(latency_ms, 2))

        return response_data

    except Exception as e:
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Update Prometheus metrics
        tool_invocations.labels(tool=body.tool, status="error").inc()

        # Log detailed error with structured logging
        logger.error("tool_execute_error",
                     tool=body.tool,
                     user_id=user_id,
                     project_id=project_id,
                     correlation_id=correlation_id,
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

    logger.info("server_main_start",
                port=port,
                version=VERSION,
                environment=ENVIRONMENT)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_config=None  # Disable uvicorn's default logging, use structlog
    )
