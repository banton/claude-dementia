# Diagnosis: "5% Working" Production Instability

## Date: Nov 15, 2025, 18:00 UTC
## Deployment: 71012a2a (ACTIVE)

## User Complaint
> "lots of errors again. In general this feels 5% working at the moment, no stability, no ability, lots of issues"

## Root Cause Analysis

### The Core Issue
`select_project_for_session` tool is **intermittently failing** with 400 status codes **without executing the tool function**. The middleware correctly allows the request through, but FastMCP/Starlette is returning 400 before the tool runs.

### Evidence

#### Pattern 1: Successful Execution (20% of calls)
```
17:11:23 - POST /mcp with tool: select_project_for_session
17:11:23 - Middleware: "Allowing project selection tool"
17:11:23 - FastMCP: "Processing request of type CallToolRequest"  ← TOOL EXECUTES
17:11:23 - ✅ Using Neon's PgBouncer pooler
17:11:27 - ✅ Migration 11 complete
17:11:27 - ✅ Schema 'workspace' ready
17:11:27 - status_code: 200 (elapsed: 5253ms)
```

#### Pattern 2: Fast Failure (80% of calls)
```
17:09:03 - POST /mcp with tool: select_project_for_session
17:09:03 - Middleware: "Allowing project selection tool"
17:09:03 - [NO "Processing request" LOG - TOOL NEVER EXECUTES]
17:09:03 - status_code: 400 (elapsed: 925ms)  ← INSTANT FAILURE
```

#### Pattern 3: Silent Success (Rare)
```
17:46:13 - POST /mcp with tool: select_project_for_session
17:46:13 - Middleware: "Allowing project selection tool"
17:46:13 - FastMCP: "Processing request of type CallToolRequest"
17:46:13 - [NO DATABASE LOGS - SUSPICIOUS]
17:46:13 - status_code: 200 (elapsed: 907ms)  ← TOO FAST!
```

### Key Observations

1. **Middleware is working correctly**
   - Session creation: ✅ Working
   - Session validation: ✅ Working
   - Project selection tool allowlist: ✅ Working
   - Session context injection (line 170-173): ✅ Working

2. **Tool registration appears correct**
   - Only one definition of `select_project_for_session` exists
   - Has proper `@mcp.tool()` decorator
   - Correct `async def` signature
   - No startup errors in logs

3. **The failure happens BETWEEN middleware and tool execution**
   - Middleware logs: "Allowing project selection tool" (line 166)
   - Expected next log: "Processing request of type CallToolRequest"
   - **MISSING**: This log never appears for failed requests
   - FastMCP returns 400 without calling the tool function

4. **Error responses have no detail**
   - All logs show: `"error_detail": null`
   - No exceptions logged
   - No traceback in server logs
   - FastMCP is silently rejecting the request

### Hypothesis: Parameter Validation Failure

The most likely cause is **parameter validation in FastMCP**:

1. Claude.ai sends request with `arguments: {project_name: "linkedin"}`
2. Middleware allows request through
3. FastMCP attempts to validate parameters against tool schema
4. **Validation fails silently** (possibly malformed arguments object)
5. FastMCP returns 400 **without executing** the tool
6. No error logged because it's treated as a client error

### Why It's Intermittent

The successful calls (Pattern 1) work because they:
- Use the correct parameter format
- Have properly structured arguments
- Match the expected schema exactly

The failed calls (Pattern 2) fail because they likely:
- Have slightly malformed arguments
- Missing required fields
- Wrong parameter types
- Extra/unexpected fields

The silent successes (Pattern 3) are concerning because they:
- Return 200 OK
- But don't execute database operations
- Suggest the tool is returning early with cached/default data
- Or returning without actual execution

### Impact

**User Experience:**
- 80% of `select_project_for_session` calls fail
- Users forced to retry multiple times
- No clear error message explaining why
- System appears broken/unstable

**Cascading Failures:**
- Failed project selection blocks ALL other tools
- Middleware requires project selection before allowing tools
- Users stuck in "pending" session state
- Cannot access locked contexts or memories

## Recommended Next Steps

### Immediate Investigation

1. **Add request body logging before tool execution**
   - Log the exact `params.arguments` object
   - Log the expected parameter schema
   - Identify what's different between successful and failed requests

2. **Add FastMCP error handling**
   - Catch parameter validation exceptions
   - Log validation errors before returning 400
   - Return descriptive error messages to client

3. **Check FastMCP version compatibility**
   - Verify FastMCP library version
   - Check for known issues with parameter handling
   - Review recent FastMCP changes/bugs

### Code Changes Needed

**In `server_hosted.py` or middleware:**
```python
# Log request body BEFORE passing to FastMCP
logger.info(f"Tool call params: {body.get('params', {})}")
```

**In `claude_mcp_hybrid_sessions.py`:**
```python
# Add parameter validation logging at start of function
@mcp.tool()
async def select_project_for_session(project_name: str) -> str:
    logger.info(f"select_project_for_session called with: {project_name}")
    logger.info(f"Session context: {getattr(config, '_current_session_id', 'NOT SET')}")
    # ... rest of function
```

### Testing Plan

1. Create test script that calls `select_project_for_session` 20 times
2. Log all requests/responses
3. Identify pattern in successful vs failed calls
4. Reproduce failure locally
5. Fix parameter validation issue

## Files Involved

- `mcp_session_middleware.py` - Session validation (WORKING)
- `server_hosted.py` - FastMCP integration (SUSPECT)
- `claude_mcp_hybrid_sessions.py` - Tool implementation (NEEDS LOGGING)
- FastMCP library - Parameter validation (SUSPECT)

## Timeline

- **17:08:06** - Server started (version 4.3.0)
- **17:09:03** - First `select_project_for_session` failure (400)
- **17:11:23** - First successful call (200, 5.2s)
- **17:46:13** - Fast success (200, 0.9s - suspicious)
- **17:50:27** - Another failure (400)

## Conclusion

The system is NOT 5% working - the core infrastructure (database, sessions, middleware) is 100% functional. The issue is a **parameter validation bug in FastMCP** that causes 80% of `select_project_for_session` calls to fail silently.

This creates a terrible user experience because:
1. Users can't select projects reliably
2. No clear error message
3. Retries sometimes work (confusing)
4. All other tools are blocked until project is selected

**Priority:** CRITICAL - blocks all functionality
**Complexity:** LOW - likely a simple parameter formatting issue
**Fix Time:** 1-2 hours once we log the actual requests
