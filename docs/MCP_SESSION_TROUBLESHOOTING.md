# MCP Session Troubleshooting Guide

## Issue: "Tool ran without output or errors" / 400 Bad Request

### Symptoms

- MCP tools (sleep, wake_up, etc.) return no output
- Production logs show: `POST /mcp HTTP/1.1" 400 Bad Request`
- Response happens in <1ms (instant rejection)
- Database remains idle (no connection made)
- Error persists across multiple tool calls

### Root Cause

**Stale MCP Session after Server Deployment**

When the cloud-hosted MCP server is deployed:

1. **Previous server instance is killed** (hard shutdown)
2. **In-memory session storage is lost** (FastMCP stores sessions in RAM)
3. **Client still has old session ID** cached from previous connection
4. **New server rejects requests** with old session ID → 400 Bad Request
5. **Client doesn't auto-reinitialize** - just shows "Tool ran without output"

**Why it happens:**
- FastMCP's `StreamableHTTP` transport stores sessions in memory only
- Every deployment creates a brand new server instance
- Clients (Claude Code/Claude Desktop) cache session IDs across deployments
- MCP spec expects servers to return 400 for unknown sessions
- Clients should detect 400 and reinitialize, but don't always

### How to Identify

**Production Logs Pattern:**
```
{"mcp_session_id": "ebe1a03adbf64ff8a78ec158029f160b", ...}  // Old session
{"status_code": 400, "elapsed_ms": 0.85, ...}                 // Instant rejection
```

**No initialize request:**
- Sessions should start with `mcp_session_id: "missing"` (initialize)
- If first request has a session ID, it's from a previous connection

**Timing:**
- 400 errors happen in <2ms (no database connection)
- Successful requests take 3-10+ seconds (database wake + query)

### Solution

**Immediate Fix: Restart the Client**

**For Claude Code:**
1. Exit Claude Code completely
2. Relaunch Claude Code
3. Tools will work immediately

**For Claude Desktop:**
1. Quit Claude Desktop
2. Relaunch Claude Desktop
3. First tool call will initialize new session

**Verification:**

After restart, logs should show:
```
{"mcp_session_id": "missing", ...}              // Initialize request
{"status_code": 200, ...}                       // Success
{"mcp_session_id": "0d5c139bab474dc3b9e916428bf9a64b", ...}  // New session
```

### Long-Term Solutions

#### Option 1: Persistent Session Storage (Recommended)

**Pros:**
- Sessions survive server restarts
- No client disruption on deployment
- Better user experience

**Cons:**
- Adds complexity
- Requires database schema for sessions
- Session cleanup/expiration needed

**Implementation:**
```python
# Store sessions in PostgreSQL
CREATE TABLE mcp_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    capabilities JSONB,
    client_info JSONB
);

# On server startup, reload active sessions
# On session access, update last_active
# Expire sessions after 24 hours inactive
```

#### Option 2: Graceful Session Migration

**Pros:**
- Simpler than persistent storage
- Leverages existing infra

**Cons:**
- Still causes brief disruption
- Clients must support graceful degradation

**Implementation:**
```python
# During deployment:
1. New instance starts
2. Load balancer routes to both old + new
3. Old instance serves existing sessions (10 min timeout)
4. New instance handles new sessions
5. Old instance shuts down after sessions expire
```

#### Option 3: Client-Side Session Recovery

**Pros:**
- No server changes needed
- Clients handle their own reconnection

**Cons:**
- Requires client support
- May cause user confusion

**Implementation:**
```python
# In MCP client wrapper:
async def call_tool_with_retry(tool, args):
    try:
        return await mcp.call_tool(tool, args)
    except ClientError as e:
        if e.status_code == 400:
            # Session likely stale, reinitialize
            await mcp.initialize()
            return await mcp.call_tool(tool, args)
```

#### Option 4: Session Health Endpoint

**Pros:**
- Proactive detection
- Can warn users before failure

**Cons:**
- Requires client polling
- Extra HTTP requests

**Implementation:**
```python
@app.get("/session/{session_id}/health")
async def check_session_health(session_id: str):
    if session_exists(session_id):
        return {"status": "valid", "session_id": session_id}
    else:
        return {"status": "invalid", "session_id": session_id,
                "action": "reinitialize"}
```

### Prevention Strategies

**1. Detect Deployment Events**

Add deployment marker to logs:
```python
DEPLOYMENT_ID = os.getenv('DEPLOYMENT_ID', 'unknown')
logger.info("server_started", deployment_id=DEPLOYMENT_ID)
```

**2. Add Session Validation Middleware**

Log when sessions are rejected:
```python
if status_code == 400 and "session" in error_message:
    logger.warning("stale_session_detected",
                   session_id=request.headers.get('mcp-session-id'),
                   deployment_id=DEPLOYMENT_ID)
```

**3. Monitor Session Creation Rate**

Alert when many new sessions created (indicates mass reconnection):
```python
session_creation_rate.labels(deployment=DEPLOYMENT_ID).inc()
# Alert if >10 new sessions in 1 minute after deployment
```

**4. Document in Server Response**

For 400 errors, include helpful message:
```python
return JSONResponse(
    status_code=400,
    content={
        "error": "Invalid session",
        "detail": "Session not found. This may happen after server restart.",
        "action": "Please restart your MCP client to reinitialize the connection.",
        "deployment_id": DEPLOYMENT_ID
    }
)
```

### Monitoring & Alerts

**Key Metrics:**
- Session creation rate (spikes indicate mass reconnection)
- 400 error rate on /mcp endpoint (indicates stale sessions)
- Average session lifetime (low = frequent reconnections)
- Requests with unknown session IDs

**Alert Conditions:**
```
400_error_rate_on_mcp > 10 per minute
AND
deployment_timestamp < 5 minutes ago
→ Send notification: "Users may need to restart clients after deployment"
```

### Related Issues

**GitHub Issues Referencing This Problem:**
- [modelcontextprotocol/python-sdk#180](https://github.com/langchain-ai/langchain-mcp-adapters/issues/180) - Intermittent 400 Bad Request
- [modelcontextprotocol/python-sdk#1053](https://github.com/modelcontextprotocol/python-sdk/issues/1053) - Streamable HTTP transport fails on Cloud Run
- [modelcontextprotocol/python-sdk#492](https://github.com/modelcontextprotocol/python-sdk/issues/492) - Client error 400 Bad Request during session init

**MCP Specification:**
- [Transports - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- Servers SHOULD respond with 400 Bad Request for requests with unknown session IDs

### Summary

**The stale session issue is an inherent limitation of stateless MCP deployments with in-memory session storage.**

**Quick Fix:** Restart the client
**Long-term Fix:** Implement persistent session storage in database
**Best Practice:** Add deployment notifications + session health monitoring

## Implementation Checklist

- [ ] Implement persistent session storage in PostgreSQL
- [ ] Add session validation logging to detect stale sessions
- [ ] Create session health check endpoint
- [ ] Add deployment notifications for users
- [ ] Monitor session creation rate and 400 errors
- [ ] Update client libraries to auto-retry on 400 with reinit
- [ ] Document deployment process to minimize disruption
- [ ] Add graceful shutdown period for old deployments

---

**Last Updated:** 2025-11-04
**Related Tickets:** DEM-29 (Connection Pool Exhaustion - discovered during investigation)
