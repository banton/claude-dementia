#!/usr/bin/env python3
"""
Production Cloud-Hosted Dementia MCP Server

Architecture: Uses FastMCP's Starlette app as base, adds custom routes and middleware

Production-grade features:
- Structured logging (structlog)
- Prometheus metrics
- Bearer token authentication
- Correlation ID tracking
- MCP streamable HTTP transport (Claude Desktop compatible)
"""

import os
import json
import time
import asyncio
import traceback
import secrets
from datetime import datetime, timezone
from typing import Dict, Any

# Starlette imports (FastMCP uses Starlette, not FastAPI)
from starlette.routing import Route
from starlette.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Import existing MCP server
from claude_mcp_hybrid import mcp

# Import production infrastructure
from src.logging_config import configure_logging, get_logger
from src.metrics import (
    active_connections,
    get_metrics_text,
    tool_invocations,
    request_size_bytes,
    response_size_bytes
)

# Configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
VERSION = "4.3.0"

# Configure structured logging
configure_logging(environment=ENVIRONMENT, log_level=LOG_LEVEL)
logger = get_logger(__name__)

# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================

class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for MCP endpoints."""

    async def dispatch(self, request, call_next):
        # Only check auth for /mcp/* and /execute, /tools, /metrics paths
        protected_paths = ['/mcp', '/execute', '/tools', '/metrics']

        if any(request.url.path.startswith(path) for path in protected_paths):
            auth_header = request.headers.get("Authorization")

            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid authorization header"}
                )

            token = auth_header.replace("Bearer ", "")
            api_key = os.getenv('DEMENTIA_API_KEY')

            # Constant-time comparison to prevent timing attacks
            if not api_key or not secrets.compare_digest(token, api_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key"}
                )

        # Auth passed (or not needed), continue
        return await call_next(request)

# ============================================================================
# CORRELATION ID MIDDLEWARE
# ============================================================================

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Add correlation ID to every request for tracing."""

    async def dispatch(self, request, call_next):
        correlation_id = request.headers.get('X-Correlation-ID', f'req-{int(time.time() * 1000)}')
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers['X-Correlation-ID'] = correlation_id
        return response

# ============================================================================
# REQUEST LOGGING MIDDLEWARE
# ============================================================================

class MCPRequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log MCP requests and responses for debugging - header-only to avoid breaking StreamableHTTP."""

    async def dispatch(self, request, call_next):
        # Only log /mcp endpoint requests
        if request.url.path.startswith('/mcp'):
            # Log request headers only (don't consume body - breaks StreamableHTTP)
            logger.info("mcp_request_received",
                       method=request.method,
                       path=request.url.path,
                       content_type=request.headers.get('content-type'),
                       content_length=request.headers.get('content-length', 'unknown'),
                       has_auth=bool(request.headers.get('authorization')),
                       correlation_id=getattr(request.state, 'correlation_id', 'unknown'))

        # Process the request
        start_time = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start_time) * 1000

        # Log the response for /mcp endpoint
        if request.url.path.startswith('/mcp'):
            logger.info("mcp_response_sent",
                       status_code=response.status_code,
                       elapsed_ms=round(elapsed_ms, 2),
                       correlation_id=getattr(request.state, 'correlation_id', 'unknown'))

        return response

# ============================================================================
# TIMEOUT MIDDLEWARE
# ============================================================================

class TimeoutMiddleware(BaseHTTPMiddleware):
    """Add timeout to requests to prevent hanging."""

    async def dispatch(self, request, call_next):
        start_time = time.time()
        try:
            # 45 second timeout (longer than client's 30s timeout)
            response = await asyncio.wait_for(
                call_next(request),
                timeout=45.0
            )

            elapsed = time.time() - start_time

            # Warn on slow requests
            if elapsed > 20:
                logger.warning("slow_request",
                              path=request.url.path,
                              elapsed_seconds=round(elapsed, 2),
                              correlation_id=getattr(request.state, 'correlation_id', 'unknown'))

            return response

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error("request_timeout",
                        path=request.url.path,
                        elapsed_seconds=round(elapsed, 2),
                        correlation_id=getattr(request.state, 'correlation_id', 'unknown'))
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Request timeout",
                    "detail": f"Request exceeded 45 second timeout (elapsed: {round(elapsed, 2)}s)"
                }
            )

# ============================================================================
# CUSTOM ROUTES
# ============================================================================

async def health_check(request: Request):
    """Health check for DigitalOcean (unauthenticated)."""
    return JSONResponse({
        "status": "healthy",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

async def list_tools_endpoint(request: Request):
    """List available MCP tools (authenticated)."""
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')

    logger.info("list_tools_start", correlation_id=correlation_id)

    # Get tools from FastMCP tool manager
    tools_list = await mcp.list_tools()

    tools = []
    for tool in tools_list:
        tools.append({
            "name": tool.name,
            "description": tool.description or "No description"
        })

    logger.info("list_tools_success",
                tool_count=len(tools),
                correlation_id=correlation_id)

    return JSONResponse({"tools": tools, "count": len(tools)})

async def execute_tool_endpoint(request: Request):
    """Execute MCP tool and return result (authenticated)."""
    start_time = time.time()
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')

    # Parse request body
    body = await request.json()
    tool_name = body.get('tool')
    arguments = body.get('arguments', {})

    # Track request size
    request_body = await request.body()
    request_size_bytes.observe(len(request_body))

    logger.info("tool_execute_start",
                tool=tool_name,
                correlation_id=correlation_id,
                arguments=arguments)

    try:
        # Execute tool via FastMCP
        result = await mcp.call_tool(tool_name, arguments)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Update Prometheus metrics
        tool_invocations.labels(tool=tool_name, status="success").inc()

        # Convert MCP result to JSON-serializable format
        if isinstance(result, tuple) and len(result) >= 1:
            result = result[0]

        if isinstance(result, list):
            serialized_result = []
            for item in result:
                if hasattr(item, 'text'):
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
            try:
                result = json.loads(result)
            except:
                pass
        elif hasattr(result, 'text'):
            try:
                result = json.loads(result.text)
            except:
                result = result.text
        elif hasattr(result, 'model_dump'):
            result = result.model_dump()

        response_data = {
            "success": True,
            "tool": tool_name,
            "result": result,
            "latency_ms": round(latency_ms, 2)
        }

        # Track response size
        try:
            response_json = json.dumps(response_data)
        except TypeError as e:
            logger.warning("json_serialization_fallback", error=str(e), result_type=str(type(result)))
            response_data["result"] = str(result)
            response_json = json.dumps(response_data)
        response_size_bytes.observe(len(response_json))

        logger.info("tool_execute_success",
                    tool=tool_name,
                    correlation_id=correlation_id,
                    latency_ms=round(latency_ms, 2))

        return JSONResponse(response_data)

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        tool_invocations.labels(tool=tool_name, status="error").inc()

        logger.error("tool_execute_error",
                     tool=tool_name,
                     correlation_id=correlation_id,
                     error=str(e),
                     error_type=type(e).__name__,
                     traceback=traceback.format_exc(),
                     latency_ms=round(latency_ms, 2))

        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Tool execution failed: {str(e)}"}
        )

async def metrics_endpoint(request: Request):
    """Prometheus metrics endpoint (authenticated)."""
    data, content_type = get_metrics_text()
    return Response(content=data, media_type=content_type)

# ============================================================================
# APPLICATION SETUP
# ============================================================================

# Get FastMCP's Starlette app (already has /mcp routes and lifespan)
app = mcp.streamable_http_app()

# Eagerly initialize database at module load to prevent first-request timeout
# Neon database may be suspended and take 10-15s to wake up
# This ensures the connection pool is ready before serving requests
from claude_mcp_hybrid import _get_db_adapter
try:
    logger.info("database_initialization_start")
    adapter = _get_db_adapter()
    logger.info("database_initialization_success", schema=adapter.schema)
except Exception as e:
    logger.error("database_initialization_failed", error=str(e))
    # Don't crash the server, let it handle cold starts per-request
    pass

# Add custom routes FIRST (before auth middleware, so routing happens before auth check)
app.routes.insert(0, Route('/health', health_check, methods=['GET']))
app.routes.insert(1, Route('/tools', list_tools_endpoint, methods=['GET']))
app.routes.insert(2, Route('/execute', execute_tool_endpoint, methods=['POST']))
app.routes.insert(3, Route('/metrics', metrics_endpoint, methods=['GET']))

# Add middleware (order matters - last added runs first in Starlette)
# Execution order: Timeout -> RequestLogging -> Auth -> CorrelationID -> Handler
app.add_middleware(CorrelationIdMiddleware)      # Innermost - adds correlation ID
app.add_middleware(BearerAuthMiddleware)         # Auth check
app.add_middleware(MCPRequestLoggingMiddleware)  # Log /mcp requests/responses
app.add_middleware(TimeoutMiddleware)            # Outermost - catch timeouts

logger.info("app_initialized",
            version=VERSION,
            environment=ENVIRONMENT,
            routes=['/health', '/tools', '/execute', '/metrics', '/mcp'])

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
