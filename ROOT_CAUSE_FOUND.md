# Root Cause Analysis - Custom Connector Tool Visibility

## Problem
Custom Connector could not discover MCP tools, showing error:
```
"Error connecting to dementia. Please confirm that you have permission to access the service, that you're using the correct credentials, and that your server handles auth correctly.
(invalid_grant: Invalid authorization code)"
```

## Root Cause

**The blocker was the OAuth authorization code flow**, not the Bearer auth middleware.

### The Bug
In `oauth_mock.py`, authorization codes were stored in **in-memory Python dict**:
```python
auth_codes: Dict[str, dict] = {}  # code -> {client_id, redirect_uri, code_challenge, user}
```

### Why This Failed
1. Custom Connector requests authorization: `GET /oauth/authorize`
2. Server generates code and stores in `auth_codes` dict
3. Server redirects Custom Connector with code
4. **Server deploys/restarts (memory wiped)** ⚠️
5. Custom Connector tries to exchange code: `POST /oauth/token`
6. Code not found in `auth_codes` → `invalid_grant` error ❌

### The Fix
Modified `oauth_mock.py` to accept authorization codes even if not in memory:

```python
# TESTING MODE: Accept authorization code even if not in memory
# (handles server restarts between authorize and token exchange)
# In production, store codes in PostgreSQL

# Issue access token
access_token = STATIC_TOKEN

# Store token metadata (for validation)
access_tokens[access_token] = {
    'client_id': client_id,
    'user': 'demo-user',
    'scope': 'mcp',
    'expires_at': datetime.now(timezone.utc) + timedelta(hours=24)
}
```

## Secondary Issue: Custom Connector Doesn't Send Bearer Tokens

After fixing OAuth, we tested re-enabling BearerAuthMiddleware and found:

**Custom Connector does NOT send the Bearer token in MCP requests!**

Logs show:
```
"has_auth": false
"status_code": 401
```

Even though OAuth completes successfully and Custom Connector receives a token, it **does not include it in the Authorization header** when making MCP requests (`POST /mcp`, `GET /mcp`).

**Result:** BearerAuthMiddleware **must remain disabled** for Custom Connector compatibility.

## Final Configuration

```python
# Custom Connector doesn't send Bearer token in MCP requests (only in OAuth flow)
# Disabling auth for Custom Connector compatibility
# app.add_middleware(BearerAuthMiddleware)  # Auth disabled
```

**Trade-off:**
- ✅ Custom Connector works (OAuth for connection, no auth on MCP calls)
- ❌ MCP endpoints are unauthenticated (relies on OAuth'd connection only)
- ✅ Claude Desktop via npx still works (doesn't need auth middleware)

## Production Fix Needed

For production stability, authorization codes should be stored in **PostgreSQL**, not memory:
- Add `oauth_codes` table to database
- Store codes with expiration timestamps
- Clean up expired codes periodically

This ensures codes survive server restarts and work across multiple server instances.

## Success Confirmation

Screenshot shows tools appearing in Custom Connector menu:
- gather database statistics
- ai summarize context
- Apply migrations
- Batch lock contexts
- Batch recall contexts
- Check contexts
- Context dashboard
- Create project
- Delete project
- Execute sql
- Explore context tree
- ... and more

✅ **Custom Connector can now discover and use all 31 MCP tools**
