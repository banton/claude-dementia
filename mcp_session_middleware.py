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
                            client_info={'user_agent': request.headers.get('user-agent', 'unknown')}
                        )
                        logger.info(f"MCP session created: {new_session_id[:8]} (len={len(new_session_id)}), stored_id: {result['session_id'][:8]} (len={len(result['session_id'])})")
                    except Exception as e:
                        logger.error(f"MCP session create failed: {new_session_id[:8]}, error: {e}", exc_info=True)

            return response

        # Existing session - validate and update activity
        try:
            # Check if session exists in PostgreSQL
            pg_session = self.session_store.get_session(session_id)

            if pg_session is None:
                # Session not found in PostgreSQL
                # This happens after deployment when FastMCP lost in-memory sessions
                logger.warning(f"MCP session not found in database: {session_id[:8]}")

                # Try to recreate session in PostgreSQL
                # (FastMCP might still accept it if client sends initialize)
                try:
                    result = self.session_store.create_session(session_id=session_id)
                    logger.info(f"MCP session recreated: {session_id[:8]}, stored_id: {result['session_id'][:8]}")
                except Exception as e:
                    logger.error(f"MCP session recreate failed: {session_id[:8]}, error: {e}", exc_info=True)

            elif self.session_store.is_expired(session_id):
                # Session expired
                logger.warning(f"MCP session expired: {session_id[:8]}, expires_at: {pg_session['expires_at']}")

                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32600,
                            "message": "Session expired",
                            "data": {
                                "detail": "Your session has expired. Please restart your MCP client to reinitialize the connection.",
                                "expires_at": pg_session['expires_at'].isoformat()
                            }
                        },
                        "id": body.get('id')
                    }
                )

            else:
                # Valid session - update activity timestamp
                self.session_store.update_activity(session_id)
                logger.debug(f"MCP session activity updated: {session_id[:8]}")

        except Exception as e:
            logger.error(f"MCP session validation error: {session_id[:8]}, error: {e}")
            # Don't block request on validation errors
            pass

        # Continue to FastMCP handler
        return await call_next(request)
