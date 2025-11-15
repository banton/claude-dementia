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
from starlette.requests import Request
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
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes) if body_bytes else {}
        except json.JSONDecodeError:
            body = {}

        method = body.get('method', '')

        # Handle initialize request (new session)
        if method == 'initialize' or session_id == 'missing':
            # This is a new session - will be created by FastMCP
            # We'll create our PostgreSQL record after the request succeeds
            response = await call_next(request)

            # If FastMCP created session successfully, store in PostgreSQL
            if response.status_code == 200:
                # Extract new session ID from response
                # (FastMCP returns it in response headers or body)
                new_session_id = response.headers.get('Mcp-Session-Id')
                logger.debug(f"FastMCP header Mcp-Session-Id length: {len(new_session_id) if new_session_id else 0}, value: {new_session_id}")

                if new_session_id:
                    try:
                        result = self.session_store.create_session(
                            session_id=new_session_id,
                            project_name='__PENDING__',  # Sentinel - user must select project
                            client_info={'user_agent': request.headers.get('user-agent', 'unknown')}
                        )
                        logger.info(f"MCP session created: {new_session_id[:8]} (len={len(new_session_id)}), stored_id: {result['session_id'][:8]} (len={len(result['session_id'])})")
                    except Exception as e:
                        logger.error(f"MCP session create failed: {new_session_id[:8]}, error: {e}", exc_info=True)

            return response

        # Existing session - validate and check for inactivity
        try:
            # Check if session exists in PostgreSQL
            pg_session = self.session_store.get_session(session_id)

            if pg_session is None:
                # Session not found - return 401 to force re-initialization
                logger.warning(f"MCP session not found: {session_id[:8]}")

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
                logger.info(f"Pending session {session_id[:8]} - method: '{method}', tool_name: '{tool_name}', http_method: {request.method}")

                # For StreamableHTTP, tools/list is likely a GET request, not JSON-RPC
                # Allow GET requests through so Claude.ai can discover tools
                if request.method == 'GET':
                    logger.info(f"Allowing GET request for pending session: {session_id[:8]}")
                    return await call_next(request)

                # Allow all MCP discovery methods (needed for client initialization)
                # These are required for the MCP client to discover capabilities
                discovery_methods = ['tools/list', 'resources/list', 'prompts/list']
                if method in discovery_methods:
                    logger.info(f"Allowing discovery method '{method}' for pending session: {session_id[:8]}")
                    return await call_next(request)

                # Allow MCP protocol notifications (needed for client initialization)
                if method.startswith('notifications/'):
                    logger.info(f"Allowing notification '{method}' for pending session: {session_id[:8]}")
                    return await call_next(request)

                # Allow project selection tools (needed to choose a project!)
                project_selection_tools = ['select_project_for_session', 'list_projects', 'get_project_info']
                if method == 'tools/call' and tool_name in project_selection_tools:
                    logger.info(f"🔵 STEP 1: Allowing project selection tool '{tool_name}' for pending session: {session_id[:8]}")

                    # Set session context for tool to access
                    try:
                        from claude_mcp_hybrid_sessions import config
                        config._current_session_id = session_id
                        logger.info(f"🔵 STEP 2: Session context set for {session_id[:8]}")
                    except Exception as e:
                        logger.warning(f"🔴 STEP 2 FAILED: Failed to set session context: {e}")

                    logger.info(f"🔵 STEP 3: Passing request to FastMCP for tool '{tool_name}'")
                    response = await call_next(request)
                    logger.info(f"🔵 STEP 6: Response received from FastMCP, status: {response.status_code}")
                    return response

                # Any other tool - require project selection first
                logger.info(f"Project selection required for session: {session_id[:8]}")

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

                logger.info(f"MCP session inactive ({inactive_seconds/60:.1f} min): {session_id[:8]}, finalizing handover for project: {project_name}")

                # Finalize handover from session_summary
                try:
                    self.session_store.finalize_handover(session_id, project_name)
                    logger.info(f"MCP handover finalized: {session_id[:8]}, project: {project_name}")
                except Exception as e:
                    logger.error(f"MCP handover finalization failed: {session_id[:8]}, error: {e}")

                # Delete session
                try:
                    self.session_store.delete_session(session_id)
                    logger.info(f"MCP session deleted: {session_id[:8]}")
                except Exception as e:
                    logger.error(f"MCP session deletion failed: {session_id[:8]}, error: {e}")

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
            self.session_store.update_activity(session_id)
            logger.debug(f"MCP session activity updated: {session_id[:8]}")

            # Set session context for tools to access
            try:
                from claude_mcp_hybrid_sessions import config
                config._current_session_id = session_id
                logger.debug(f"Session context set for tools: {session_id[:8]}")
            except Exception as e:
                logger.warning(f"Failed to set session context: {e}")

        except Exception as e:
            logger.error(f"MCP session validation error: {session_id[:8]}, error: {e}", exc_info=True)
            # Don't block request on validation errors
            pass

        # Continue to FastMCP handler
        return await call_next(request)
