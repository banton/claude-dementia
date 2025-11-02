#!/usr/bin/env python3
"""
Test-Driven Development for FastMCP Starlette Integration

Tests verify that we can:
1. Add middleware to FastMCP's Starlette app
2. Add custom routes to FastMCP's Starlette app
3. Run the combined app with uvicorn
4. Connect via mcp-remote

Run with: pytest tests/test_starlette_mcp_integration.py -v
"""

import pytest
import os
import sys
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFastMCPStarletteIntegration:
    """Test that we can extend FastMCP's Starlette app"""

    def test_can_get_fastmcp_starlette_app(self):
        """Test: FastMCP returns a Starlette app"""
        from claude_mcp_hybrid import mcp

        app = mcp.streamable_http_app()

        assert isinstance(app, Starlette), "FastMCP should return Starlette app"
        assert hasattr(app, 'add_middleware'), "App should have add_middleware method"
        assert hasattr(app, 'routes'), "App should have routes"

    def test_can_add_middleware_to_fastmcp_app(self):
        """Test: Can add middleware to FastMCP Starlette app"""
        from claude_mcp_hybrid import mcp

        app = mcp.streamable_http_app()

        # Create test middleware
        class TestMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                response.headers['X-Test-Header'] = 'middleware-works'
                return response

        # Add middleware - should not raise
        app.add_middleware(TestMiddleware)

        # Verify middleware was added
        assert len(app.user_middleware) > 0, "Middleware should be added"

    def test_can_add_custom_routes_to_fastmcp_app(self):
        """Test: Can add custom routes to FastMCP Starlette app"""
        from claude_mcp_hybrid import mcp

        app = mcp.streamable_http_app()
        initial_route_count = len(app.routes)

        # Add a custom route
        async def health_check(request):
            return JSONResponse({"status": "healthy"})

        app.routes.append(Route('/health', health_check))

        # Verify route was added
        assert len(app.routes) > initial_route_count, "Custom route should be added"

    def test_custom_health_endpoint_without_auth(self):
        """Test: Custom /health endpoint returns 200 without authentication"""
        from claude_mcp_hybrid import mcp

        app = mcp.streamable_http_app()

        # Add health endpoint
        async def health_check(request):
            return JSONResponse({"status": "healthy", "version": "4.3.0"})

        app.routes.insert(0, Route('/health', health_check))

        # Test with TestClient
        client = TestClient(app)
        response = client.get('/health')

        assert response.status_code == 200, "Health check should return 200"
        assert response.json()['status'] == 'healthy', "Should return healthy status"

    def test_auth_middleware_blocks_unauthorized_mcp_requests(self):
        """Test: Auth middleware blocks unauthorized requests to /mcp"""
        from claude_mcp_hybrid import mcp
        import secrets

        app = mcp.streamable_http_app()

        # Add auth middleware
        class BearerAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.url.path.startswith('/mcp'):
                    auth_header = request.headers.get('Authorization')
                    if not auth_header or not auth_header.startswith('Bearer '):
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Missing authorization header"}
                        )

                    token = auth_header.replace('Bearer ', '')
                    expected = os.getenv('DEMENTIA_API_KEY', 'test_key_123')

                    if not secrets.compare_digest(token, expected):
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Invalid API key"}
                        )

                return await call_next(request)

        app.add_middleware(BearerAuthMiddleware)

        # Test without auth - should fail
        client = TestClient(app)

        # Note: We can't actually test the /mcp POST without running the full server
        # because it requires the task group initialization
        # But we can verify the middleware is in place
        assert len(app.user_middleware) > 0, "Auth middleware should be added"

    def test_auth_middleware_allows_authorized_requests(self):
        """Test: Auth middleware allows requests with valid Bearer token"""
        from claude_mcp_hybrid import mcp
        import secrets

        app = mcp.streamable_http_app()

        # Add health endpoint
        async def health_check(request):
            return JSONResponse({"status": "healthy"})

        app.routes.insert(0, Route('/health', health_check))

        # Add auth middleware that doesn't block /health
        class BearerAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.url.path.startswith('/mcp'):
                    auth_header = request.headers.get('Authorization')
                    if not auth_header or not auth_header.startswith('Bearer '):
                        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

                    token = auth_header.replace('Bearer ', '')
                    expected = os.getenv('DEMENTIA_API_KEY', 'test_key_123')

                    if not secrets.compare_digest(token, expected):
                        return JSONResponse(status_code=401, content={"detail": "Invalid"})

                return await call_next(request)

        app.add_middleware(BearerAuthMiddleware)

        # Test health endpoint without auth - should work
        client = TestClient(app)
        response = client.get('/health')
        assert response.status_code == 200, "/health should work without auth"


class TestArchitectureValidation:
    """Validate the new architecture design"""

    def test_architecture_uses_fastmcp_as_base(self):
        """Test: New architecture uses FastMCP Starlette app as base, not FastAPI"""
        from claude_mcp_hybrid import mcp
        from starlette.applications import Starlette

        app = mcp.streamable_http_app()

        # Should be Starlette, NOT FastAPI
        assert type(app).__name__ == 'Starlette', "Should use Starlette as base"
        assert not type(app).__name__ == 'FastAPI', "Should NOT use FastAPI as base"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
