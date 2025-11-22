# SSE Crash Investigation - Claude.ai Custom Connector

**Date**: 2025-11-16
**Deployment**: cacebdd3 (ACTIVE)
**Issue**: MCP tools not appearing in Claude.ai custom connector despite successful OAuth

---

## Root Cause Identified

**DELETE /mcp requests from Claude.ai are crashing SSE streams**

### Evidence from Logs

```
18:10:37 UTC - DELETE /mcp (session: c00f439c24d34f258c7bf57ad7a0a66e)
18:10:39 UTC - Processing ListToolsRequest
18:10:39 UTC - ClosedResourceError (SSE stream already closed by DELETE)

18:14:18 UTC - DELETE /mcp (session: 45778cf2ed8943d0a7bd92eb70e1c7dc)
18:14:20 UTC - Processing ListToolsRequest
18:14:20 UTC - ClosedResourceError (SSE stream already closed by DELETE)
```

### Pattern

1. Claude.ai client sends `DELETE /mcp` to close session
2. FastMCP StreamableHTTP closes the SSE writer immediately
3. Concurrent `ListToolsRequest` tries to write to closed stream
4. `anyio.ClosedResourceError` / `anyio.BrokenResourceError`
5. Tools never appear in UI

### Traceback

```python
File "mcp/server/streamable_http.py", line 507, in _handle_post_request
    await writer.send(session_message)
File "anyio/streams/memory.py", line 256, in send
    raise BrokenResourceError from None
anyio.BrokenResourceError
```

---

## Why This is Happening

**Claude.ai's aggressive session management:**
- Sends DELETE requests when switching away from chat
- Sends DELETE requests before reconnecting
- Then immediately sends new POST /mcp requests with different session IDs
- Expects graceful handling of overlapping requests

**MCP StreamableHTTP's behavior:**
- DELETE closes SSE writer immediately
- Doesn't wait for in-flight requests to complete
- No graceful shutdown period
- Crashes when trying to write to closed stream

---

## Attempted Solutions (Didn't Work)

### 1. Session Stability (Deployment 64646105)
- Generated stable session IDs from hash(api_key + user_agent)
- **Result**: Session IDs are stable, but DELETE still crashes

### 2. OAuth Token Validation
- Implemented OAuth 2.0 mock
- **Result**: Authentication works perfectly, but DELETE still crashes

### 3. Middleware Improvements
- Added session persistence middleware
- **Result**: Sessions persist, but DELETE still crashes

---

## The Real Problem

**This is NOT our code - it's the MCP StreamableHTTP protocol implementation:**

```python
# FastMCP's streamable_http.py:507
# When DELETE comes in, this immediately closes the writer
await writer.send(session_message)
# ↑ Crashes if writer was closed by concurrent DELETE
```

**We're using FastMCP's `mcp.streamable_http_app()` which:**
- Doesn't expose DELETE handler customization
- Doesn't have graceful shutdown logic
- Doesn't queue pending responses before closing

---

## Options Forward

### Option 1: Catch and Suppress ClosedResourceError (QUICK FIX)

Add exception handling in StreamableHTTP middleware:

```python
# server_hosted.py - Add SSE crash suppression middleware
class SSECrashSuppressionMiddleware(BaseHTTPMiddleware):
    """Suppress SSE crashes from concurrent DELETE + POST requests."""

    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
            return response
        except (anyio.ClosedResourceError, anyio.BrokenResourceError) as e:
            # Claude.ai sent DELETE while request was processing
            # Return empty response instead of crashing
            logger.warning("sse_concurrent_delete",
                          path=request.url.path,
                          error=str(e),
                          correlation_id=getattr(request.state, 'correlation_id', 'unknown'))

            # Return 503 Service Unavailable with retry hint
            return JSONResponse(
                status_code=503,
                headers={"Retry-After": "1"},
                content={"detail": "Session closed, please retry"}
            )
```

**Pros:**
- Quick fix (< 30 minutes)
- Prevents crashes
- Client will retry automatically

**Cons:**
- Doesn't fix root cause
- Still wastes some requests
- Bandaid solution

---

### Option 2: Implement Graceful DELETE Handler (PROPER FIX)

Replace FastMCP's DELETE handler with custom implementation:

```python
# server_hosted.py - Custom DELETE handler
async def graceful_mcp_delete(request: Request):
    """Gracefully close MCP session with pending request draining."""
    session_id = request.headers.get('mcp-session-id')

    if not session_id:
        return JSONResponse(status_code=400, content={"detail": "Missing session ID"})

    logger.info("graceful_session_close_start", session_id=session_id)

    # Wait up to 2 seconds for pending requests to complete
    # (Claude.ai typically waits 1-2s between DELETE and new POST)
    await asyncio.sleep(2)

    # Now close the session
    # TODO: Call FastMCP's internal session cleanup

    logger.info("graceful_session_close_complete", session_id=session_id)

    return JSONResponse(status_code=204)  # No Content

# Replace FastMCP's DELETE route
# Remove: mcp.streamable_http_app() default DELETE handler
# Add: Route('/mcp', graceful_mcp_delete, methods=['DELETE'])
```

**Pros:**
- Proper fix
- Graceful shutdown
- No wasted requests

**Cons:**
- Requires understanding FastMCP internals
- More complex (1-2 hours)
- May break on FastMCP updates

---

### Option 3: Don't Use FastMCP StreamableHTTP (NUCLEAR OPTION)

Implement MCP StreamableHTTP from scratch using Starlette:

- Full control over SSE lifecycle
- Custom DELETE handling
- Custom session management
- But: Large refactoring effort (4-6 hours)

**Not recommended** - overkill for this issue

---

## Recommended Fix: Option 1 + Option 2

### Phase 1: Quick Fix (NOW)
Implement SSE crash suppression middleware to stop the bleeding.

### Phase 2: Proper Fix (LATER)
Implement graceful DELETE handler with request draining.

---

## Testing Plan

After implementing fix:

1. Start with clean Claude.ai custom connector
2. Test DELETE + immediate POST pattern:
   ```
   curl -X DELETE https://dementia-mcp-7f4vf.ondigitalocean.app/mcp \
        -H "Authorization: Bearer $API_KEY" \
        -H "mcp-session-id: test-session-123"

   # Immediately send POST (within 100ms)
   curl -X POST https://dementia-mcp-7f4vf.ondigitalocean.app/mcp \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
   ```

3. Monitor logs for ClosedResourceError (should be suppressed)

4. Test in Claude.ai:
   - Connect custom connector
   - Switch to different chat (triggers DELETE)
   - Switch back (triggers new POST)
   - Verify tools appear

---

## Timeline

**Immediate (30 min):**
- Implement SSE crash suppression middleware
- Deploy to production
- Test with Claude.ai custom connector

**Follow-up (1-2 hours):**
- Research FastMCP session cleanup
- Implement graceful DELETE handler
- Test concurrent requests
- Deploy and verify

---

## Status

**Current Deployment**: cacebdd3
**Current State**: Tools not appearing due to SSE crashes
**Next Action**: Implement SSE crash suppression middleware
