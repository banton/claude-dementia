# MCP Protocol Implementation Verification

## Analysis of server_hosted.py Against MCP Cloud Protocol

### ✅ Authentication Flow - CORRECT

**Expected**: Bearer token authentication with constant-time comparison

**Implementation** (server_hosted.py:55-82):
```python
class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Only check auth for /mcp/* and /execute, /tools, /metrics paths
        protected_paths = ['/mcp', '/execute', '/tools', '/metrics']

        if any(request.url.path.startswith(path) for path in protected_paths):
            auth_header = request.headers.get("Authorization")

            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,  # ✅ Correct
                    content={"detail": "Missing or invalid authorization header"}
                )

            token = auth_header.replace("Bearer ", "")
            api_key = os.getenv('DEMENTIA_API_KEY')

            # Constant-time comparison to prevent timing attacks
            if not api_key or not secrets.compare_digest(token, api_key):
                return JSONResponse(
                    status_code=401,  # ✅ Correct
                    content={"detail": "Invalid API key"}
                )

        return await call_next(request)
```

**Status**: ✅ **CORRECT** - Follows protocol exactly

---

### ✅ Correlation ID Tracking - CORRECT

**Expected**: Add correlation ID to requests for tracing

**Implementation** (server_hosted.py:88-97):
```python
class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        correlation_id = request.headers.get('X-Correlation-ID', f'req-{int(time.time() * 1000)}')
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers['X-Correlation-ID'] = correlation_id
        return response
```

**Status**: ✅ **CORRECT** - Implements correlation ID tracking

---

### ⚠️ MCP Request Handling - DELEGATED TO FASTMCP

**Expected**: Parse JSON-RPC 2.0 request, validate format, call tool

**Implementation** (server_hosted.py:242):
```python
# Get FastMCP's Starlette app (already has /mcp routes and lifespan)
app = mcp.streamable_http_app()
```

**Analysis**:
- MCP request handling is **delegated to FastMCP library**
- We do NOT have visibility into:
  - JSON-RPC parsing logic
  - Request validation
  - Error handling for malformed requests
  - 400 Bad Request generation logic

**Status**: ⚠️ **UNKNOWN** - Cannot verify without FastMCP source code

**Critical Questions**:
1. What JSON-RPC format does FastMCP expect?
2. What causes FastMCP to return 400 Bad Request?
3. Does FastMCP log request parsing errors?
4. What is FastMCP's timeout behavior?

---

### ❌ Request/Response Logging - MISSING

**Expected**: Log all MCP requests and responses for debugging

**Current Implementation**: No logging middleware for `/mcp` endpoint

**Evidence**:
- Production logs show: `POST /mcp HTTP/1.1" 400 Bad Request`
- No logs showing request body
- No logs showing why 400 was returned
- No logs showing if tool was invoked

**Impact**: **Cannot debug 400 errors without request logging**

**Status**: ❌ **MISSING** - Critical debugging capability absent

**Fix Needed**:
```python
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith('/mcp'):
            body = await request.body()
            logger.info("mcp_request_received",
                       method=request.method,
                       path=request.url.path,
                       content_type=request.headers.get('content-type'),
                       body_preview=body[:500].decode('utf-8', errors='replace'))

        response = await call_next(request)

        if request.url.path.startswith('/mcp'):
            logger.info("mcp_response_sent",
                       status_code=response.status_code,
                       correlation_id=getattr(request.state, 'correlation_id', 'unknown'))

        return response
```

---

### ❌ Timeout Middleware - MISSING

**Expected**: Server-side timeout to prevent hanging requests

**Current Implementation**: No timeout middleware

**Evidence**:
- Tools hang for 30+ seconds
- No server-side timeout configured
- Relies on client timeout (30s)
- Database wake can take 10-15s

**Impact**: Long operations can exceed client timeout

**Status**: ❌ **MISSING** - No server-side timeout protection

**Fix Needed**:
```python
import asyncio

class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()
        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=45.0  # 45s server timeout (longer than client 30s)
            )
            elapsed = time.time() - start_time
            if elapsed > 20:
                logger.warning("slow_request",
                              path=request.url.path,
                              elapsed_seconds=round(elapsed, 2))
            return response
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error("request_timeout",
                        path=request.url.path,
                        elapsed_seconds=round(elapsed, 2))
            return JSONResponse(
                status_code=504,
                content={"error": "Request timeout after 45 seconds"}
            )
```

---

### ✅ Database Connection Flow - CORRECT

**Expected**: Connection pooling with retry logic for Neon wake

**Implementation** (postgres_adapter.py:200-227):
```python
def get_connection(self):
    """Get connection from pool with retry logic."""
    max_retries = 3
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            conn = self.pool.getconn()

            # Set statement timeout per-connection
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '30s'")

            return conn

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️  Connection attempt {attempt + 1} failed: {e}", file=sys.stderr)
                print(f"   Retrying in {retry_delay} seconds...", file=sys.stderr)
                time.sleep(retry_delay)
            else:
                raise
```

**Implementation** (postgres_adapter.py:278-320 - ensure_schema_exists):
```python
# CRITICAL FIX: Set search_path at ROLE level (not session level)
cur.execute("SELECT CURRENT_USER")
role_name = cur.fetchone()['current_user']

cur.execute(
    sql.SQL("ALTER ROLE {} SET search_path TO {}, public").format(
        sql.Identifier(role_name),
        sql.Identifier(self.schema)
    )
)
```

**Status**: ✅ **CORRECT** - Properly handles Neon transaction pooling and wake delays

---

### ⚠️ Tool Execution Error Handling - PARTIAL

**Expected**: Catch exceptions, return proper JSON-RPC error format

**Implementation** (server_hosted.py:215-230 for /execute endpoint):
```python
except Exception as e:
    latency_ms = (time.time() - start_time) * 1000
    tool_invocations.labels(tool=tool_name, status="error").inc()

    logger.error("tool_execute_error",
                 tool=tool_name,
                 correlation_id=correlation_id,
                 error=str(e),
                 error_type=type(e).__name__,
                 traceback=traceback.format_exc(),
                 latency_ms=round(latency_ms, 2))

    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Tool execution failed: {str(e)}"}
    )
```

**Analysis**:
- /execute endpoint has good error handling ✅
- /mcp endpoint error handling is in FastMCP (unknown) ⚠️

**Status**: ⚠️ **PARTIAL** - /execute is good, /mcp is unknown

---

## Critical Findings

### 1. 🔴 ROOT CAUSE OF 400 ERRORS: FastMCP Request Validation

**Problem**: FastMCP library handles `/mcp` endpoint, we have no visibility into:
- What request format it expects
- Why it returns 400
- What errors it logs
- How it validates JSON-RPC

**Evidence**:
```
07:30:43 INFO: POST /mcp HTTP/1.1" 400 Bad Request
07:34:00 INFO: POST /mcp HTTP/1.1" 400 Bad Request
```

**No logs showing**:
- Request body
- Parsing errors
- Validation failures
- Tool invocation attempts

**This means**: The 400 error happens **inside FastMCP**, before our tools run.

---

### 2. 🔴 MISSING: Request Logging for /mcp Endpoint

**Problem**: Cannot debug 400 errors without seeing request body

**Fix**: Add request logging middleware BEFORE FastMCP handler

**Priority**: **CRITICAL** - Blocks all debugging

---

### 3. 🟡 MISSING: Server-Side Timeout

**Problem**: Long operations exceed client 30s timeout

**Impact**:
- Database wake (10-15s) + query (5-10s) = 15-25s total
- Close to client timeout limit
- No server timeout protection

**Fix**: Add timeout middleware with 45s limit

**Priority**: **HIGH** - Improves reliability

---

### 4. 🟡 UNKNOWN: FastMCP JSON-RPC Implementation

**Problem**: We don't know how FastMCP handles:
- JSON-RPC 2.0 parsing
- Method validation
- Parameter validation
- Error responses

**Fix**: Need to either:
1. Read FastMCP source code (in production venv)
2. Test with curl to understand behavior
3. Add logging to capture FastMCP behavior

**Priority**: **HIGH** - Needed to fix 400 errors

---

## Immediate Action Plan

### Step 1: Add Request Logging Middleware
```python
# In server_hosted.py, add this middleware
class MCPRequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log MCP requests and responses for debugging."""

    async def dispatch(self, request, call_next):
        if request.url.path.startswith('/mcp'):
            # Read body (be careful - can only read once)
            body = await request.body()
            logger.info("mcp_request_received",
                       method=request.method,
                       path=request.url.path,
                       content_type=request.headers.get('content-type'),
                       content_length=len(body),
                       body_preview=body[:1000].decode('utf-8', errors='replace'))

            # Create new request with body (since we read it)
            from starlette.requests import Request
            request = Request(scope=request.scope, receive=request.receive)

        response = await call_next(request)

        if request.url.path.startswith('/mcp'):
            logger.info("mcp_response_sent",
                       status_code=response.status_code,
                       correlation_id=getattr(request.state, 'correlation_id', 'unknown'))

        return response

# Add BEFORE auth middleware (line 264):
app.add_middleware(MCPRequestLoggingMiddleware)
app.add_middleware(BearerAuthMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

### Step 2: Test with curl

```bash
# Export API key
export DEMENTIA_API_KEY="wWKYw3FTk_IhCCVwwmKopF7RTvGn8yDEFobOyEXZOHU"

# Test valid JSON-RPC request
curl -X POST https://dementia-mcp-server-x8fkw.ondigitalocean.app/mcp \
  -H "Authorization: Bearer ${DEMENTIA_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: test-curl-001" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "wake_up",
      "arguments": {
        "project": "claude_dementia"
      }
    }
  }' -v

# Check logs for request body and response
```

### Step 3: Measure Database Wake Time

```python
# Add to wake_up() function in claude_mcp_hybrid.py:
import time

async def wake_up(project: Optional[str] = None) -> str:
    wake_start = time.time()

    conn = _get_db_for_project(project)

    wake_time = time.time() - wake_start
    logger.info("database_wake_time",
               project=project,
               seconds=round(wake_time, 2))

    # ... rest of function
```

### Step 4: Add Timeout Middleware

```python
# After request logging, before auth (line 264)
app.add_middleware(TimeoutMiddleware)  # 45s timeout
app.add_middleware(MCPRequestLoggingMiddleware)
app.add_middleware(BearerAuthMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

---

## Expected Outcomes After Fixes

### After Request Logging:
- See exact JSON-RPC request body causing 400
- Identify if FastMCP expects different format
- See FastMCP error messages in logs

### After curl Testing:
- Confirm valid JSON-RPC format works
- Identify what Claude Desktop sends differently
- Verify authentication and request flow

### After Timeout Middleware:
- Detect slow requests >20s
- Kill requests >45s with 504 response
- Better error messages for timeouts

### After Database Wake Timing:
- Know exact wake time under cold start
- Optimize if needed
- Set appropriate timeout values

---

## Protocol Compliance Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Authentication | ✅ CORRECT | Bearer token, constant-time comparison |
| Correlation ID | ✅ CORRECT | Tracks requests across systems |
| Database Connection | ✅ CORRECT | Retry logic, transaction pooling fix |
| MCP Request Parsing | ⚠️ UNKNOWN | Handled by FastMCP (black box) |
| Request Logging | ❌ MISSING | Cannot debug 400 errors |
| Timeout Handling | ❌ MISSING | No server-side timeout |
| Error Responses | ⚠️ PARTIAL | /execute good, /mcp unknown |
| Tool Execution | ✅ CORRECT | Proper async handling |

**Overall Assessment**: Implementation is **mostly correct** but has **critical debugging gaps** that prevent diagnosing the 400 error issue.

**Priority Fixes**:
1. 🔴 Add request logging middleware (critical)
2. 🔴 Test with curl to understand FastMCP behavior (critical)
3. 🟡 Add timeout middleware (high)
4. 🟡 Add database wake timing (high)
