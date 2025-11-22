# MCP Tools Visibility Investigation

**Date**: November 22, 2025
**Issue**: Custom Connector in Claude.ai not showing tools
**Status**: ROOT CAUSE IDENTIFIED

## Summary

The `/tools` REST endpoint works perfectly and returns proper MCP-formatted tools with `inputSchema`. The issue is NOT with tool schema formatting. The problem is that **Custom Connectors use the MCP StreamableHTTP protocol at `/mcp`, not the REST `/tools` endpoint**.

## Key Findings

### 1. REST `/tools` Endpoint - ✅ WORKING

```bash
curl -H "Authorization: Bearer <token>" https://dementia-mcp-7f4vf.ondigitalocean.app/tools
```

**Response**:
- ✅ HTTP 200 OK
- ✅ Returns `application/json`
- ✅ Contains 31 tools
- ✅ Tools have `inputSchema` (NOT `parameters`)
- ✅ Schema is clean (thanks to `schema_patcher.py`)

**Example tool structure**:
```json
{
  "name": "switch_project",
  "description": "...",
  "inputSchema": {
    "properties": { "name": { "type": "string" } },
    "required": ["name"],
    "type": "object"
  }
}
```

### 2. MCP Protocol at `/mcp` - ❌ SESSION VALIDATION ISSUE

According to MCP spec, Custom Connectors:
1. Send JSON-RPC messages to `/mcp` endpoint
2. Use `tools/list` method to discover tools
3. Require `mcp-session-id` header for session management

**Test result**:
```bash
POST /mcp
Headers: { "mcp-session-id": "<uuid>" }
Body: { "jsonrpc": "2.0", "method": "tools/list", "id": 1 }
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Bad Request: No valid session ID provided"
  }
}
```

## Root Cause Analysis

### The Problem

The `/mcp` endpoint has strict session validation that prevents initial connection without a pre-existing session. This creates a chicken-and-egg problem:

1. Custom Connector tries to connect
2. Server requires valid session ID
3. But session doesn't exist yet!
4. Connection fails before `initialize` can create session

### Where the Issue Lives

File: `server_hosted.py:238-266` (graceful_mcp_delete handler)
File: `mcp_session_middleware.py` (session validation middleware)

The session middleware is rejecting requests that don't have a pre-existing valid session, but Custom Connectors need to establish a session FIRST through the `initialize` handshake.

## How MCP StreamableHTTP Should Work

According to the spec:

1. **Client sends `initialize`** with optional `mcp-session-id`
2. **Server responds** with `result` containing `serverInfo` and `capabilities`
3. **Client sends `initialized` notification**
4. **Client can now send `tools/list`, `tools/call`, etc.**

**Critical**: The `initialize` request should work WITHOUT a pre-existing session!

## Schema Patching - Already Fixed

Our `schema_patcher.py` correctly transforms:
- Removes `title` fields
- Converts `anyOf` to `type: [T, 'null']` for optional fields
- Keeps `inputSchema` (MCP spec) instead of `parameters` (OpenAPI spec)

This is working correctly for the `/tools` endpoint.

## What Custom Connectors Actually Use

Based on research:

1. **NOT REST endpoints** like `/tools`
2. **MCP StreamableHTTP protocol** at `/mcp`
3. **JSON-RPC 2.0 messages** like `initialize`, `tools/list`, `tools/call`
4. **Session management** via `mcp-session-id` header

## Next Steps

**Option 1**: Fix session validation to allow `initialize` without session
**Option 2**: Check if FastMCP's `streamable_http_app()` already handles this
**Option 3**: Review Custom Connector initialization logs in production

## Related Files

- `server_hosted.py`: FastMCP server with `/mcp` endpoint
- `mcp_session_middleware.py`: Session validation middleware
- `claude_mcp_hybrid_sessions.py`: Main MCP server with tools
- `schema_patcher.py`: Tool schema cleanup (already working)

## References

- MCP Spec: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- StreamableHTTP: https://www.claudemcp.com/blog/mcp-streamable-http
- Custom Connectors: CUSTOM-CONNECTOR-RESEARCH.md
