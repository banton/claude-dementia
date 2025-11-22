#!/usr/bin/env python3
"""
Minimal OAuth 2.1 Mock for Claude.ai Custom Connector

This implements the bare minimum OAuth endpoints required by Claude.ai
while using a static token underneath. Perfect for single-user deployments.

Security Note: This is NOT production OAuth! It's a mock that satisfies
Claude.ai's protocol requirements while maintaining single-user simplicity.
"""

import os
import json
import secrets
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from urllib.parse import urlencode, parse_qs

from starlette.routing import Route
from starlette.responses import JSONResponse, RedirectResponse, HTMLResponse
from starlette.requests import Request
from postgres_adapter import PostgreSQLAdapter

# Configuration
# BASE_URL should be set in environment, fallback to localhost for local dev
BASE_URL = os.getenv('BASE_URL', os.getenv('APP_URL', 'https://dementia-mcp-7f4vf.ondigitalocean.app'))
STATIC_TOKEN = os.getenv('DEMENTIA_API_KEY', '<MUST_SET_ENV_VAR>')

# OAuth Client Credentials (REQUIRED for security)
OAUTH_CLIENT_ID = os.getenv('OAUTH_CLIENT_ID')
OAUTH_CLIENT_SECRET = os.getenv('OAUTH_CLIENT_SECRET')

if not OAUTH_CLIENT_ID or not OAUTH_CLIENT_SECRET:
    raise ValueError(
        "OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET must be set in environment. "
        "Generate with: python3 -c 'import secrets; print(f\"OAUTH_CLIENT_ID=dementia-{secrets.token_urlsafe(16)}\"); "
        "print(f\"OAUTH_CLIENT_SECRET={secrets.token_urlsafe(32)}\")'"
    )

# PostgreSQL storage for OAuth data (persists across restarts)
# Tables: oauth_authorization_codes, oauth_access_tokens (created in postgres_adapter.py)
_db = PostgreSQLAdapter()

# ============================================================================
# OAUTH DISCOVERY ENDPOINTS (Required by MCP Spec)
# ============================================================================

async def oauth_authorization_server_metadata(request: Request):
    """
    OAuth 2.0 Authorization Server Metadata (RFC 8414)

    Claude.ai uses this to discover authorization endpoints.
    """
    return JSONResponse({
        "issuer": f"{BASE_URL}/oauth",
        "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
        "token_endpoint": f"{BASE_URL}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],  # Confidential client
        "scopes_supported": ["mcp"],
    })

async def oauth_protected_resource_metadata(request: Request):
    """
    OAuth 2.0 Protected Resource Metadata (RFC 9728)

    MCP server metadata - tells clients about our resource.
    """
    return JSONResponse({
        "resource": BASE_URL,
        "authorization_servers": [f"{BASE_URL}/oauth"],
        "bearer_methods_supported": ["header"],
        "resource_documentation": "https://github.com/banton/claude-dementia",
        "scopes_supported": ["mcp"],
    })

# ============================================================================
# OAUTH AUTHORIZATION FLOW (Simplified for Single-User)
# ============================================================================

async def oauth_authorize(request: Request):
    """
    Authorization endpoint - handles OAuth authorization requests.

    For single-user demo, we auto-approve and redirect immediately.
    Real OAuth would show a consent screen.
    """
    # Parse query parameters
    params = dict(request.query_params)

    client_id = params.get('client_id')
    redirect_uri = params.get('redirect_uri')
    response_type = params.get('response_type')
    code_challenge = params.get('code_challenge')
    code_challenge_method = params.get('code_challenge_method')
    state = params.get('state')
    scope = params.get('scope', 'mcp')

    # Validate required parameters
    if not all([client_id, redirect_uri, response_type, code_challenge]):
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Missing required parameters"},
            status_code=400
        )

    # Validate client_id (constant-time comparison)
    if not secrets.compare_digest(client_id, OAUTH_CLIENT_ID):
        return JSONResponse(
            {"error": "invalid_client", "error_description": "Invalid client_id"},
            status_code=401
        )

    if response_type != 'code':
        return JSONResponse(
            {"error": "unsupported_response_type"},
            status_code=400
        )

    if code_challenge_method != 'S256':
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Only S256 PKCE supported"},
            status_code=400
        )

    # Generate authorization code
    auth_code = secrets.token_urlsafe(32)

    # Store authorization code in PostgreSQL
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    _db.execute_update(
        """
        INSERT INTO oauth_authorization_codes
        (code, client_id, redirect_uri, code_challenge, code_challenge_method, user_id, scope, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        params=[
            auth_code,
            client_id,
            redirect_uri,
            code_challenge,
            code_challenge_method,
            'demo-user',  # Single user
            scope,
            expires_at
        ]
    )

    # Auto-approve for single-user demo (no consent screen needed)
    # Redirect back to client with authorization code
    redirect_params = {'code': auth_code}
    if state:
        redirect_params['state'] = state

    redirect_url = f"{redirect_uri}?{urlencode(redirect_params)}"

    return RedirectResponse(redirect_url)

async def oauth_token(request: Request):
    """
    Token endpoint - exchanges authorization code for access token.

    Validates client credentials, PKCE, and returns our static token as the access token.
    """
    # Parse form data
    form = await request.form()

    grant_type = form.get('grant_type')
    code = form.get('code')
    redirect_uri = form.get('redirect_uri')
    code_verifier = form.get('code_verifier')
    client_id = form.get('client_id')
    client_secret = form.get('client_secret')

    # Validate grant type
    if grant_type != 'authorization_code':
        return JSONResponse(
            {"error": "unsupported_grant_type"},
            status_code=400
        )

    # Validate client credentials (REQUIRED for security)
    if not client_id or not client_secret:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Missing client credentials"},
            status_code=400
        )

    # Validate client_id (constant-time comparison)
    if not secrets.compare_digest(client_id, OAUTH_CLIENT_ID):
        return JSONResponse(
            {"error": "invalid_client", "error_description": "Invalid client_id"},
            status_code=401
        )

    # Validate client_secret (constant-time comparison)
    if not secrets.compare_digest(client_secret, OAUTH_CLIENT_SECRET):
        return JSONResponse(
            {"error": "invalid_client", "error_description": "Invalid client_secret"},
            status_code=401
        )

    # Retrieve authorization code from PostgreSQL
    result = _db.execute_query(
        """
        SELECT client_id, redirect_uri, code_challenge, scope, expires_at, used_at
        FROM oauth_authorization_codes
        WHERE code = %s
        """,
        params=[code]
    )

    if not result:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Invalid or expired authorization code"},
            status_code=400
        )

    auth_data = result[0]

    # Check if already used
    if auth_data['used_at'] is not None:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Authorization code already used"},
            status_code=400
        )

    # Check expiration
    if datetime.now(timezone.utc) > auth_data['expires_at']:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Authorization code expired"},
            status_code=400
        )

    # Validate client_id matches
    if client_id != auth_data['client_id']:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Client ID mismatch"},
            status_code=400
        )

    # Validate redirect_uri matches
    if redirect_uri != auth_data['redirect_uri']:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Redirect URI mismatch"},
            status_code=400
        )

    # Validate PKCE code_verifier
    if not code_verifier:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Missing code_verifier"},
            status_code=400
        )

    # Verify PKCE challenge
    verifier_hash = hashlib.sha256(code_verifier.encode()).digest()
    verifier_challenge = base64.urlsafe_b64encode(verifier_hash).decode().rstrip('=')

    if verifier_challenge != auth_data['code_challenge']:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "PKCE verification failed"},
            status_code=400
        )

    # Mark authorization code as used
    _db.execute_update(
        "UPDATE oauth_authorization_codes SET used_at = NOW() WHERE code = %s",
        params=[code]
    )

    # Issue access token
    # For single-user demo, we use our static token as the access token
    access_token = STATIC_TOKEN

    # Store token metadata in PostgreSQL (upsert for idempotency)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    _db.execute_update(
        """
        INSERT INTO oauth_access_tokens
        (access_token, client_id, user_id, scope, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (access_token) DO UPDATE
        SET last_used_at = NOW(), expires_at = EXCLUDED.expires_at
        """,
        params=[
            access_token,
            client_id,
            'demo-user',
            'mcp',
            expires_at
        ]
    )

    # Return token response
    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 86400,  # 24 hours
        "scope": auth_data['scope']
    })

# ============================================================================
# TOKEN VALIDATION (Used by BearerAuthMiddleware)
# ============================================================================

def validate_oauth_token(token: str) -> Optional[dict]:
    """
    Validate OAuth access token using PostgreSQL.

    For single-user demo: If token matches our static token, it's valid.
    Real OAuth would verify JWT signature or introspect with auth server.
    """
    # Check if it's our static token
    if token != STATIC_TOKEN:
        return None

    # Query PostgreSQL for token metadata
    result = _db.execute_query(
        """
        SELECT client_id, user_id, scope, expires_at
        FROM oauth_access_tokens
        WHERE access_token = %s
        """,
        params=[token]
    )

    if result:
        token_data = result[0]

        # Check expiration
        if datetime.now(timezone.utc) > token_data['expires_at']:
            # Cleanup expired token
            _db.execute_update(
                "DELETE FROM oauth_access_tokens WHERE access_token = %s",
                params=[token]
            )
            return None

        # Update last_used_at timestamp
        _db.execute_update(
            "UPDATE oauth_access_tokens SET last_used_at = NOW() WHERE access_token = %s",
            params=[token]
        )

        return {
            'client_id': token_data['client_id'],
            'user': token_data['user_id'],
            'scope': token_data['scope'],
            'expires_at': token_data['expires_at']
        }
    else:
        # Token is valid but no metadata (e.g., used directly via env var)
        # Create virtual metadata
        return {
            'client_id': 'static-client',
            'user': 'demo-user',
            'scope': 'mcp',
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=24)
        }


# ============================================================================
# ROUTES TO ADD TO SERVER_HOSTED.PY
# ============================================================================

OAUTH_ROUTES = [
    # Discovery endpoints (MCP spec requires /mcp suffix)
    Route('/.well-known/oauth-authorization-server/mcp', oauth_authorization_server_metadata, methods=['GET']),
    Route('/.well-known/oauth-protected-resource/mcp', oauth_protected_resource_metadata, methods=['GET']),

    # OAuth flow endpoints
    Route('/oauth/authorize', oauth_authorize, methods=['GET']),
    Route('/oauth/token', oauth_token, methods=['POST']),
]

# ============================================================================
# HELPER: Update WWW-Authenticate Header for 401 Responses
# ============================================================================

def get_www_authenticate_header() -> str:
    """
    Returns WWW-Authenticate header value for 401 responses.

    Required by MCP spec to tell clients where to find OAuth metadata.
    """
    return f'Bearer resource="{BASE_URL}/.well-known/oauth-protected-resource/mcp"'
