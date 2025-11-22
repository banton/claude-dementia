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
import anyio  # For ClosedResourceError, BrokenResourceError
from datetime import datetime, timezone
from typing import Dict, Any

# Starlette imports (FastMCP uses Starlette, not FastAPI)
from starlette.routing import Route
from starlette.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from contextlib import asynccontextmanager

# Import existing MCP server (LATEST version with session management)
from claude_mcp_hybrid_sessions import mcp

# Import session persistence (ASYNC)
from mcp_session_middleware import MCPSessionPersistenceMiddleware
from mcp_session_store_async import PostgreSQLSessionStoreAsync

# Import production infrastructure
from src.logging_config import configure_logging, get_logger
from src.metrics import (
    active_connections,
    get_metrics_text,
    tool_invocations,
    request_size_bytes,
    response_size_bytes
)

# Import OAuth mock (for Claude.ai compatibility)
from oauth_mock import (
    OAUTH_ROUTES,
    validate_oauth_token,
    get_www_authenticate_header
)

# Configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
VERSION = "4.3.0"

# Configure structured logging
configure_logging(environment=ENVIRONMENT, log_level=LOG_LEVEL)
logger = get_logger(__name__)

# ============================================================================
# SSE CRASH SUPPRESSION - DEPRECATED
# ============================================================================
# NOTE: Middleware approach doesn't work - exceptions happen inside async
# generators and don't propagate to middleware layer. Using graceful DELETE
# handler instead (graceful_mcp_delete with 2s wait period).

# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================

class BearerAuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for MCP endpoints.

    Supports both:
    1. Static Bearer token (for Claude Desktop via npx)
    2. OAuth tokens (for Claude.ai custom connectors)
    """

    async def dispatch(self, request, call_next):
        # Only check auth for /mcp/* and /execute, /tools, /metrics paths
        # OAuth endpoints are unauthenticated (public authorization flow)
        protected_paths = ['/mcp', '/execute', '/tools', '/metrics']

        if any(request.url.path.startswith(path) for path in protected_paths):
            auth_header = request.headers.get("Authorization")

            if not auth_header or not auth_header.startswith("Bearer "):
                # Return 401 with WWW-Authenticate header (required by MCP spec)
                return JSONResponse(
                    status_code=401,
                    headers={"WWW-Authenticate": get_www_authenticate_header()},
                    content={"detail": "Missing or invalid authorization header"}
                )

            token = auth_header.replace("Bearer ", "")
            api_key = os.getenv('DEMENTIA_API_KEY')

            # Try OAuth token validation first
            token_data = validate_oauth_token(token)
            if token_data:
                # Valid OAuth token - attach user info to request
                request.state.user = token_data.get('user', 'demo-user')
                request.state.auth_type = 'oauth'
            # Fall back to static API key (for Claude Desktop)
            elif api_key and secrets.compare_digest(token, api_key):
                # Valid static token
                request.state.user = 'static-user'
                request.state.auth_type = 'static'
            else:
                # Invalid token - return 401 with WWW-Authenticate header
                return JSONResponse(
                    status_code=401,
                    headers={"WWW-Authenticate": get_www_authenticate_header()},
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
                       accept=request.headers.get('accept', 'missing'),
                       mcp_session_id=request.headers.get('mcp-session-id', 'missing'),
                       has_auth=bool(request.headers.get('authorization')),
                       correlation_id=getattr(request.state, 'correlation_id', 'unknown'))

        # Process the request
        start_time = time.time()
        response = await call_next(request)
        
        # Ensure SSE responses are not buffered by Nginx/DigitalOcean
        if request.url.path.startswith('/mcp'):
            response.headers['X-Accel-Buffering'] = 'no'
            
        # Log response details (header-only)
        elapsed_ms = (time.time() - start_time) * 1000

        # Log the response for /mcp endpoint
        if request.url.path.startswith('/mcp'):
            # For error responses, try to capture the body
            error_detail = None
            if response.status_code >= 400:
                try:
                    # Try to read response body (for StreamingResponse this may not work)
                    if hasattr(response, 'body'):
                        error_detail = response.body[:500].decode('utf-8', errors='replace')
                except:
                    pass

            logger.info("mcp_response_sent",
                       status_code=response.status_code,
                       elapsed_ms=round(elapsed_ms, 2),
                       error_detail=error_detail,
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
            # 300 second timeout (matching research recommendation for cold starts)
            response = await asyncio.wait_for(
                call_next(request),
                timeout=300.0
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
                    "detail": f"Request exceeded 300 second timeout (elapsed: {round(elapsed, 2)}s)"
                }
            )

# ============================================================================
# GRACEFUL SHUTDOWN MIDDLEWARE
# ============================================================================

class GracefulShutdownMiddleware(BaseHTTPMiddleware):
    """
    Intercept DELETE /mcp requests to handle graceful shutdown.
    
    Claude.ai sends DELETE /mcp to close sessions, then immediately sends new
    POST requests. This causes ClosedResourceError if we close SSE streams immediately.
    
    Solution: Wait 2 seconds before closing to allow pending requests to complete.
    """
    
    async def dispatch(self, request, call_next):
        # Check for DELETE /mcp or /mcp/
        if request.method == 'DELETE' and request.url.path.rstrip('/') == '/mcp':
            session_id = request.headers.get('mcp-session-id', 'unknown')
            correlation_id = getattr(request.state, 'correlation_id', 'unknown')
            
            logger.info("graceful_session_close_start",
                        session_id=session_id,
                        correlation_id=correlation_id)
            
            # Wait 2 seconds for pending requests to complete
            await asyncio.sleep(2)
            
            logger.info("graceful_session_close_complete",
                        session_id=session_id,
                        correlation_id=correlation_id)
            
            # Return 202 Accepted
            return Response(status_code=202, content=b"")
            
        return await call_next(request)

async def graceful_mcp_delete(request: Request):
    """
    Gracefully close MCP session with pending request draining.

    Claude.ai sends DELETE /mcp to close sessions, then immediately sends new
    POST requests. This causes ClosedResourceError if we close SSE streams immediately.

    Solution: Wait 2 seconds before closing to allow pending requests to complete.
    """
    session_id = request.headers.get('mcp-session-id', 'unknown')
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')

    logger.info("graceful_session_close_start",
                session_id=session_id,
                correlation_id=correlation_id)

    # Wait 2 seconds for pending requests to complete
    # Claude.ai typically waits 1-2s between DELETE and new POST
    await asyncio.sleep(2)

    logger.info("graceful_session_close_complete",
                session_id=session_id,
                correlation_id=correlation_id)

    # Return 202 Accepted instead of 204 to prevent Custom Connector token discard
    # 202 means "accepted for processing" not "resource deleted"
    # Workaround for Custom Connector bug where it discards OAuth token after DELETE 204
    return Response(status_code=202, content=b"")

async def health_check(request: Request):
    """Health check for DigitalOcean (unauthenticated)."""
    return JSONResponse({
        "status": "healthy",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

async def session_health_endpoint(request: Request):
    """Session health check endpoint (authenticated)."""
    try:
        # Get database adapter and session store
        from claude_mcp_hybrid_sessions import _get_db_adapter
        adapter = _get_db_adapter()

        # Quick database connectivity test using adapter.get_connection()
        # Works for both pooled (Neon) and non-pooled connections
        conn = adapter.get_connection()
        try:
            with conn.cursor() as cur:
                # Count active and expired sessions
                cur.execute("""
                    SELECT
                        COUNT(*) as total_sessions,
                        COUNT(CASE WHEN expires_at > NOW() THEN 1 END) as active_sessions,
                        COUNT(CASE WHEN expires_at <= NOW() THEN 1 END) as expired_sessions
                    FROM mcp_sessions
                """)
                row = cur.fetchone()

                total_sessions = row['total_sessions'] if row else 0
                active_sessions = row['active_sessions'] if row else 0
                expired_sessions = row['expired_sessions'] if row else 0

            return JSONResponse({
                "status": "healthy",
                "database": "connected",
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "expired_sessions": expired_sessions,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Session health check failed: {e}")
        return JSONResponse({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status_code=503)

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
            "description": tool.description or "No description",
            "inputSchema": tool.inputSchema
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

# PATCH: Fix schema compatibility for Custom Connector
# Removes 'title' fields and simplifies 'anyOf' structures that confuse the connector
try:
    from schema_patcher import patch_mcp_tools
    logger.info("patching_tool_schemas_start")
    patch_mcp_tools(mcp)
    logger.info("patching_tool_schemas_complete")
except Exception as e:
    logger.error("patching_tool_schemas_failed", error=str(e))

# Get FastMCP's Starlette app (already has /mcp routes and lifespan)
app = mcp.streamable_http_app()

# Wrap FastMCP's lifespan with database keep-alive task
# This prevents Neon from sleeping and causing 5-11 second response times
from database_keepalive import start_keepalive_scheduler

_original_lifespan = app.router.lifespan_context

@asynccontextmanager
async def lifespan_with_keepalive(app_instance):
    """Wrap FastMCP's lifespan to add database keep-alive task."""
    # Start database keep-alive task (ping every 15 seconds to prevent Neon compute auto-suspend)
    # Neon's compute auto-suspends after short inactivity, causing 10-15s cold starts
    # Frequent pings keep the compute warm for sub-second response times
    keepalive_task = None
    if adapter is not None:
        keepalive_task = asyncio.create_task(
            start_keepalive_scheduler(adapter, interval_seconds=15)
        )
        logger.info("database_keepalive_task_started")

    # Enter FastMCP's lifespan (if it exists)
    if _original_lifespan is not None:
        async with _original_lifespan(app_instance):
            yield
    else:
        yield

    # Cleanup: Cancel keep-alive task on shutdown
    if keepalive_task is not None:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        logger.info("database_keepalive_task_stopped")

# NOTE: Don't replace lifespan yet - middleware additions will reset it
# We'll replace it AFTER all middleware is added

# Eagerly initialize async database adapter at module load to prevent first-request timeout
# Neon database may be suspended and take 10-15s to wake up
# This ensures the connection pool is ready before serving requests
from postgres_adapter_async import PostgreSQLAdapterAsync
adapter = None  # Initialize to None in case initialization fails
try:
    logger.info("database_initialization_start")
    adapter = PostgreSQLAdapterAsync()
    logger.info("database_initialization_success",
                schema=adapter.schema,
                adapter_type="async",
                database_url_host=adapter.database_url.split('@')[1] if '@' in adapter.database_url else 'unknown')
except Exception as e:
    logger.error("database_initialization_failed", error=str(e))
    # Don't crash the server, let it handle cold starts per-request
    pass


# Add custom routes FIRST (before auth middleware, so routing happens before auth check)
app.routes.insert(0, Route('/health', health_check, methods=['GET']))
app.routes.insert(1, Route('/session-health', session_health_endpoint, methods=['GET']))
app.routes.insert(2, Route('/tools', list_tools_endpoint, methods=['GET']))
app.routes.insert(3, Route('/execute', execute_tool_endpoint, methods=['POST']))
app.routes.insert(4, Route('/metrics', metrics_endpoint, methods=['GET']))

# NOTE: Route modification removed in favor of GracefulShutdownMiddleware
# This avoids breaking FastMCP's internal routing and task group initialization

# Add OAuth routes for Claude.ai compatibility (unauthenticated - public OAuth flow)
for idx, route in enumerate(OAUTH_ROUTES):
    app.routes.insert(5 + idx, route)

# Add middleware (order matters - last added runs first in Starlette)
# Execution order: Timeout -> RequestLogging -> SessionPersistence -> Auth -> CorrelationID -> CORS -> Handler
from starlette.middleware.cors import CORSMiddleware

app.add_middleware(CorrelationIdMiddleware)              # Innermost - adds correlation ID
# NOTE: Custom Connector doesn't send Bearer token in MCP requests (only in OAuth flow)
# Disabling auth for Custom Connector compatibility. Claude Desktop still works via npx with static token.
# app.add_middleware(BearerAuthMiddleware)                 # Auth disabled for Custom Connector
app.add_middleware(GracefulShutdownMiddleware)           # Handle DELETE /mcp gracefully
# Session middleware now uses async PostgreSQLAdapterAsync - no more blocking!
if adapter is not None:
    app.add_middleware(MCPSessionPersistenceMiddleware,  # Persist sessions in PostgreSQL
                       db_pool=adapter)                  # Pass async database adapter
    logger.info("session_middleware_enabled", adapter_type="async")
app.add_middleware(MCPRequestLoggingMiddleware)          # Log /mcp requests/responses
app.add_middleware(TimeoutMiddleware)                    # Catch timeouts

# Add CORS middleware (outermost to handle preflight requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://claude.ai", 
        "https://preview.claude.ai", 
        "http://localhost:5173",  # MCP Inspector
        "http://localhost:3000"   # Local dev
    ],
    allow_origin_regex="https://.*\.claude\.ai",  # Allow all claude.ai subdomains
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Mcp-Session-Id", "X-Correlation-ID"],
    expose_headers=["Mcp-Session-Id", "X-Correlation-ID", "X-Request-Id"]
)

# NOTE: SSE crash suppression now handled by graceful DELETE handler, not middleware

logger.info("app_initialized",
            version=VERSION,
            environment=ENVIRONMENT,
            routes=['/health', '/session-health', '/tools', '/execute', '/metrics', '/mcp',
                    '/.well-known/oauth-*', '/oauth/authorize', '/oauth/token'])

# Debug: Print all routes
for r in app.routes:
    if hasattr(r, 'path'):
        logger.info("route_debug", path=r.path, methods=getattr(r, 'methods', 'ALL'))
    else:
        logger.info("route_debug", route=str(r))

# NOW replace app's lifespan with wrapped version (after all middleware added)
# This prevents middleware additions from resetting it
app.router.lifespan_context = lifespan_with_keepalive

logger.info("lifespan_debug", lifespan=str(app.router.lifespan_context))

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

    # Run uvicorn server directly (no background cleanup - using lazy evaluation)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_config=None
    )
