"""Bearer token authentication middleware for cloud-hosted MCP."""

import os
import secrets
import contextvars
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging_config import get_logger

logger = get_logger(__name__)

# Context variable for storing correlation_id across async operations
correlation_id_var = contextvars.ContextVar('correlation_id', default=None)

class BearerTokenAuth(HTTPBearer):
    """Bearer token authentication scheme with strict enforcement."""

    def __init__(self):
        # CRITICAL: auto_error=True to enforce authentication
        super().__init__(auto_error=True)

        # Load API key from environment
        self.api_key = os.getenv('DEMENTIA_API_KEY')
        if not self.api_key:
            logger.error("DEMENTIA_API_KEY not set - server will reject all requests")
            raise ValueError("DEMENTIA_API_KEY must be set for production deployment")

        logger.info("bearer_auth_initialized", has_api_key=True)

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:
        """Validate bearer token from Authorization header.

        CRITICAL SECURITY: This method MUST raise HTTPException on auth failure.
        Never return None for protected endpoints.
        """

        # Skip authentication ONLY for health check (required for DO monitoring)
        if request.url.path == "/health":
            return None

        # Get credentials from Authorization header (will raise 401 if missing due to auto_error=True)
        credentials = await super().__call__(request)

        # Additional safety check (should never be None due to auto_error=True)
        if not credentials:
            logger.error("auth_missing_credentials", path=request.url.path)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(credentials.credentials, self.api_key):
            logger.warning("auth_invalid_token", path=request.url.path,
                         token_prefix=credentials.credentials[:8] + "..." if len(credentials.credentials) > 8 else "***")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.debug("auth_success", path=request.url.path)
        return credentials


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to inject correlation IDs for request tracing."""

    async def dispatch(self, request: Request, call_next):
        """Add correlation ID to request context and response headers."""

        # Generate or extract correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = secrets.token_urlsafe(16)

        # Store in context variable for logging
        correlation_id_var.set(correlation_id)

        # Add to request state for endpoint access
        request.state.correlation_id = correlation_id

        logger.bind(correlation_id=correlation_id)

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response


def get_current_user(credentials: HTTPAuthorizationCredentials) -> str:
    """
    Extract user identifier from validated credentials.

    For Phase 1 (API key auth), returns a static user ID.
    In Phase 2 (OAuth), this will decode JWT and extract user_id.

    Args:
        credentials: Validated bearer token credentials

    Returns:
        User identifier string
    """
    # Phase 1: Static user (single-user system)
    return "default_user"


def get_current_project(request: Request, default: str = "default") -> str:
    """
    Extract project identifier from request.

    Priority:
    1. Request body "project" field
    2. Query parameter "project"
    3. Default value

    Args:
        request: FastAPI request object
        default: Default project if none specified

    Returns:
        Project identifier string
    """
    # Check query parameter
    project = request.query_params.get("project")
    if project:
        return project

    # Check request body (for POST requests)
    # Note: This requires body to be parsed first
    # In practice, this will be extracted in endpoint logic

    return default


# Example usage in endpoint:
# @app.post("/mcp/execute")
# async def execute_tool(
#     request: Request,
#     credentials: HTTPAuthorizationCredentials = Depends(bearer_auth)
# ):
#     user_id = get_current_user(credentials)
#     project_id = get_current_project(request)
#     correlation_id = request.state.correlation_id
#
#     logger.info("tool_execute_start",
#                 user_id=user_id,
#                 project_id=project_id,
#                 correlation_id=correlation_id)
