"""
MCP Session Persistence Middleware

Intercepts /mcp requests to manage persistent sessions in PostgreSQL.
Works alongside FastMCP's in-memory sessions to provide deployment resilience.

Strategy:
- Store sessions in PostgreSQL for persistence across restarts
- Track session IDs from Mcp-Session-Id header
- Create new sessions on initialize requests
- Update activity timestamps on tool calls
- Validate sessions haven't expired

This solves DEM-30: Sessions survive server restarts, no user disruption on deployment.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request, ClientDisconnect
from starlette.responses import JSONResponse

from mcp_session_store import PostgreSQLSessionStore

# Use structlog for consistent logging format
try:
    from src.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    # Fallback to standard logging for tests
    import logging
    logger = logging.getLogger(__name__)


class MCPSessionPersistenceMiddleware(BaseHTTPMiddleware):
    """
    Middleware to persist MCP sessions in PostgreSQL.

    Intercepts /mcp requests to:
    1. Create new sessions in PostgreSQL on initialize
    2. Validate existing sessions haven't expired
    3. Update activity timestamps on each request
    4. Return helpful errors for expired/invalid sessions
    """

    def __init__(self, app, db_pool):
        """
        Initialize session persistence middleware.

        Args:
            app: Starlette application
            db_pool: PostgreSQL connection pool (psycopg2)
        """
        super().__init__(app)
        self.session_store = PostgreSQLSessionStore(db_pool)

    def _generate_stable_session_id(self, api_key: str, user_agent: str) -> str:
        """
        Generate stable session ID based on API key and user agent.

        This allows different UIs (Desktop, claude.ai, Claude Code) to maintain
        separate sessions while using the same API key, and sessions persist
        across MCP reconnections.

        Args:
            api_key: Bearer token / API key
            user_agent: User agent string from request headers

        Returns:
            Stable session ID (hex string)
        """
        import hashlib

        # Create stable hash from api_key + user_agent
        # Different UIs have different user-agents → different session IDs
        # Same UI reconnecting → same session ID
        stable_input = f"{api_key}:{user_agent}".encode('utf-8')
        session_hash = hashlib.sha256(stable_input).hexdigest()

        # Return first 32 chars (same length as uuid.hex)
        return session_hash[:32]

    async def dispatch(self, request: Request, call_next):
        """
        Intercept /mcp requests to manage sessions.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from next handler or error response
        """
        # Only process /mcp endpoint
        if not request.url.path.startswith('/mcp'):
            return await call_next(request)

        # Extract session ID from headers
        session_id = request.headers.get('Mcp-Session-Id', 'missing')

        # Read request body to check if it's an initialize request
        try:
            body_bytes = await request.body()
            body = json.loads(body_bytes) if body_bytes else {}
        except ClientDisconnect:
            # Client disconnected during body read - log and re-raise
            # Starlette will handle this appropriately
            logger.warning("client_disconnected_during_body_read",
                         path=request.url.path,
                         session_id=session_id[:8] if session_id != 'missing' else 'missing')
            raise
        except json.JSONDecodeError:
            body = {}

        method = body.get('method', '')

        # Handle initialize request (new or resuming session)
        if method == 'initialize' or session_id == 'missing':
            # Generate stable session ID based on API key + user agent
            # This allows sessions to persist across MCP reconnections
            api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
            user_agent = request.headers.get('user-agent', 'unknown')

            # Generate our own stable session ID (ignore FastMCP's)
            stable_session_id = self._generate_stable_session_id(api_key, user_agent)

            # Check if session already exists (reconnection)
            existing_session = self.session_store.get_session(stable_session_id)

            if existing_session:
                # Resume existing session
                logger.info(f"🔄 Resuming session: {stable_session_id[:8]}, project: {existing_session.get('project_name', 'unknown')}, user_agent: {user_agent[:50]}")

                # Update activity timestamp
                self.session_store.update_activity(stable_session_id)

                # Set session context for tools to access
                try:
                    from claude_mcp_hybrid_sessions import config
                    config._current_session_id = stable_session_id
                    logger.debug(f"Session context set for tools: {stable_session_id[:8]}")
                except Exception as e:
                    logger.warning(f"Failed to set session context: {e}")

            else:
                # Create new session
                logger.info(f"📦 Creating new session: {stable_session_id[:8]}, user_agent: {user_agent[:50]}")

                try:
                    result = self.session_store.create_session(
                        session_id=stable_session_id,
                        project_name='__PENDING__',
                        client_info={'user_agent': user_agent}
                    )
                    logger.info(f"MCP session created: {stable_session_id[:8]}, project: __PENDING__")

                    # Set session context for tools to access
                    try:
                        from claude_mcp_hybrid_sessions import config
                        config._current_session_id = stable_session_id
                        logger.debug(f"Session context set for tools: {stable_session_id[:8]}")
                    except Exception as e:
                        logger.warning(f"Failed to set session context: {e}")

                except Exception as e:
                    logger.error(f"MCP session create failed: {stable_session_id[:8]}, error: {e}", exc_info=True)

            # Let FastMCP handle the initialize request (we don't care about its session ID)
            response = await call_next(request)
            return response

        # Existing session - validate and check for inactivity
        try:
            # Generate stable session ID (same logic as initialize)
            api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
            user_agent = request.headers.get('user-agent', 'unknown')
            stable_session_id = self._generate_stable_session_id(api_key, user_agent)

            # Check if session exists in PostgreSQL
            pg_session = self.session_store.get_session(stable_session_id)

            if pg_session is None:
                # Session not found - return 401 to force re-initialization
                logger.warning(f"MCP session not found: {stable_session_id[:8]}")

                return JSONResponse(
                    status_code=401,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32600,
                            "message": "Session not found",
                            "data": {
                                "detail": "Session not found. Please restart your MCP client to create a new session.",
                                "code": "SESSION_NOT_FOUND"
                            }
                        },
                        "id": body.get('id')
                    }
                )

            # Check if project selection is pending
            if pg_session.get('project_name') == '__PENDING__':
                # Check if this is a tools/list request or select_project_for_session call
                tool_name = body.get('params', {}).get('name', '')

                # Log the method being called for debugging
                logger.info(f"Pending session {stable_session_id[:8]} - method: '{method}', tool_name: '{tool_name}', http_method: {request.method}")

                # For StreamableHTTP, tools/list is likely a GET request, not JSON-RPC
                # Allow GET requests through so Claude.ai can discover tools
                if request.method == 'GET':
                    logger.info(f"Allowing GET request for pending session: {stable_session_id[:8]}")
                    return await call_next(request)

                # Allow all MCP discovery methods (needed for client initialization)
                # These are required for the MCP client to discover capabilities
                discovery_methods = ['tools/list', 'resources/list', 'prompts/list']
                if method in discovery_methods:
                    logger.info(f"Allowing discovery method '{method}' for pending session: {stable_session_id[:8]}")
                    return await call_next(request)

                # Allow DELETE requests (client disconnection)
                if request.method == 'DELETE':
                    logger.info(f"Allowing DELETE request for pending session: {stable_session_id[:8]}")
                    return await call_next(request)

                # Allow MCP protocol notifications (needed for client initialization)
                if method.startswith('notifications/') or method.startswith('logging/'):
                    logger.info(f"Allowing notification '{method}' for pending session: {stable_session_id[:8]}")
                    return await call_next(request)
                
                # Allow ping (health check)
                if method == 'ping':
                    logger.info(f"Allowing ping for pending session: {stable_session_id[:8]}")
                    return await call_next(request)

                # Allow project selection tools (needed to choose a project!)
                project_selection_tools = ['select_project_for_session', 'list_projects', 'get_project_info']
                if method == 'tools/call' and tool_name in project_selection_tools:
                    logger.info(f"Allowing project selection tool '{tool_name}' for pending session: {stable_session_id[:8]}")

                    # Set session context for tool to access
                    try:
                        from claude_mcp_hybrid_sessions import config
                        config._current_session_id = stable_session_id
                        logger.debug(f"Session context set for {stable_session_id[:8]}")
                    except Exception as e:
                        logger.warning(f"Failed to set session context: {e}")

                    response = await call_next(request)
                    return response

                # Any other tool - require project selection first
                logger.info(f"Project selection required for session: {stable_session_id[:8]}")

                # Get available projects
                try:
                    projects = self.session_store.get_projects_with_stats()

                    # Format project info for display
                    project_list = []
                    for p in projects:
                        last_used = p.get('last_used', 'never')
                        locks = p.get('context_locks', 0)
                        project_list.append({
                            "name": p['project_name'],
                            "context_locks": locks,
                            "last_used": last_used,
                            "description": f"{p['project_name']} ({locks} locks, {last_used})"
                        })

                    # Always include 'default' option if not present
                    if not any(p['name'] == 'default' for p in project_list):
                        project_list.append({
                            "name": "default",
                            "context_locks": 0,
                            "last_used": "never",
                            "description": "default (new session)"
                        })

                except Exception as e:
                    logger.error(f"Failed to get project list: {e}")
                    project_list = [{"name": "default", "description": "default (new session)"}]

                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": "PROJECT_SELECTION_REQUIRED",
                            "message": "Please select a project before using tools",
                            "data": {
                                "projects": project_list,
                                "instructions": "Call select_project_for_session('project_name') to continue",
                                "tool_name": "select_project_for_session"
                            }
                        },
                        "id": body.get('id')
                    }
                )

            # Check for inactivity (120 minutes = 7200 seconds)
            now = datetime.now(timezone.utc)
            last_active = pg_session['last_active']

            # Make timezone-aware if needed
            if last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=timezone.utc)

            inactive_seconds = (now - last_active).total_seconds()

            if inactive_seconds > 7200:  # 120 minutes
                # Session inactive - finalize handover and delete
                project_name = pg_session.get('project_name', 'default')

                logger.info(f"MCP session inactive ({inactive_seconds/60:.1f} min): {stable_session_id[:8]}, finalizing handover for project: {project_name}")

                # Finalize handover from session_summary
                try:
                    self.session_store.finalize_handover(stable_session_id, project_name)
                    logger.info(f"MCP handover finalized: {stable_session_id[:8]}, project: {project_name}")
                except Exception as e:
                    logger.error(f"MCP handover finalization failed: {stable_session_id[:8]}, error: {e}")

                # Delete session
                try:
                    self.session_store.delete_session(stable_session_id)
                    logger.info(f"MCP session deleted: {stable_session_id[:8]}")
                except Exception as e:
                    logger.error(f"MCP session deletion failed: {stable_session_id[:8]}, error: {e}")

                # Return 401 to force new session
                return JSONResponse(
                    status_code=401,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32600,
                            "message": "Session inactive",
                            "data": {
                                "detail": f"Session was inactive for {inactive_seconds/60:.0f} minutes. A handover was created. Please restart to begin a new session.",
                                "code": "SESSION_EXPIRED",
                                "inactive_minutes": int(inactive_seconds / 60)
                            }
                        },
                        "id": body.get('id')
                    }
                )

            # Valid session - update activity timestamp
            self.session_store.update_activity(stable_session_id)
            logger.debug(f"MCP session activity updated: {stable_session_id[:8]}")

            # Set session context for tools to access
            try:
                from claude_mcp_hybrid_sessions import config
                config._current_session_id = stable_session_id
                logger.debug(f"Session context set for tools: {stable_session_id[:8]}")
            except Exception as e:
                logger.warning(f"Failed to set session context: {e}")

        except Exception as e:
            logger.error(f"MCP session validation error: {stable_session_id[:8]}, error: {e}", exc_info=True)
            # Don't block request on validation errors
            pass

        # Continue to FastMCP handler
        return await call_next(request)
