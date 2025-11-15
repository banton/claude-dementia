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

# Configuration
# BASE_URL should be set in environment, fallback to localhost for local dev
BASE_URL = os.getenv('BASE_URL', os.getenv('APP_URL', 'https://dementia-mcp-7f4vf.ondigitalocean.app'))
STATIC_TOKEN = os.getenv('DEMENTIA_API_KEY', 'wWKYw3FTk_IhCCVwwmKopF7RTvGn8yDEFobOyEXZOHU')

# In-memory storage for demo (use PostgreSQL for production)
# For single-user demo, this is fine - it resets on restart
auth_codes: Dict[str, dict] = {}  # code -> {client_id, redirect_uri, code_challenge, user}
access_tokens: Dict[str, dict] = {}  # token -> {client_id, user, expires_at}

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
        "token_endpoint_auth_methods_supported": ["none"],  # Public client
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

    # Store authorization code with PKCE challenge
    auth_codes[auth_code] = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'code_challenge': code_challenge,
        'code_challenge_method': code_challenge_method,
        'user': 'demo-user',  # Single user
        'scope': scope,
        'expires_at': datetime.now(timezone.utc) + timedelta(minutes=5)
    }

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

    Validates PKCE and returns our static token as the access token.
    """
    # Parse form data
    form = await request.form()

    grant_type = form.get('grant_type')
    code = form.get('code')
    redirect_uri = form.get('redirect_uri')
    code_verifier = form.get('code_verifier')
    client_id = form.get('client_id')

    # Validate grant type
    if grant_type != 'authorization_code':
        return JSONResponse(
            {"error": "unsupported_grant_type"},
            status_code=400
        )

    # Validate authorization code exists
    if code not in auth_codes:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Invalid authorization code"},
            status_code=400
        )

    auth_data = auth_codes[code]

    # Check expiration
    if datetime.now(timezone.utc) > auth_data['expires_at']:
        del auth_codes[code]
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

    # PKCE verified! Issue access token
    # For single-user demo, we use our static token as the access token
    access_token = STATIC_TOKEN

    # Store token metadata (for validation)
    access_tokens[access_token] = {
        'client_id': client_id,
        'user': auth_data['user'],
        'scope': auth_data['scope'],
        'expires_at': datetime.now(timezone.utc) + timedelta(hours=24)
    }

    # Clean up used authorization code
    del auth_codes[code]

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
    Validate OAuth access token.

    For single-user demo: If token matches our static token, it's valid.
    Real OAuth would verify JWT signature or introspect with auth server.
    """
    # Check if it's our static token
    if token == STATIC_TOKEN:
        # Check if we have metadata for it
        if token in access_tokens:
            token_data = access_tokens[token]

            # Check expiration
            if datetime.now(timezone.utc) > token_data['expires_at']:
                del access_tokens[token]
                return None

            return token_data
        else:
            # Token is valid but no metadata (e.g., used directly via env var)
            # Create virtual metadata
            return {
                'client_id': 'static-client',
                'user': 'demo-user',
                'scope': 'mcp',
                'expires_at': datetime.now(timezone.utc) + timedelta(hours=24)
            }

    return None

# ============================================================================
# ROUTES TO ADD TO SERVER_HOSTED.PY
# ============================================================================

OAUTH_ROUTES = [
    # Discovery endpoints
    Route('/.well-known/oauth-authorization-server', oauth_authorization_server_metadata, methods=['GET']),
    Route('/.well-known/oauth-protected-resource', oauth_protected_resource_metadata, methods=['GET']),

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
    return f'Bearer resource="{BASE_URL}/.well-known/oauth-protected-resource"'
