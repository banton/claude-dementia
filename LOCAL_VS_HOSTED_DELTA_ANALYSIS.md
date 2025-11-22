# Local vs Hosted Edition - Complete Delta Analysis

**Date**: 2025-11-16
**Git Commit**: Both at 68725b3 (Bug #2 Extended Fix)
**Analysis**: Systematic comparison of Working Solution (A) vs Hosted Version (B)

---

## Summary

Both local and hosted use the **IDENTICAL MCP implementation** (`claude_mcp_hybrid_sessions.py`) at the **SAME git commit** (68725b3).

All deltas are purely **architectural** - the wrapper and transport layer differences.

| Aspect | Local (A) - Working Solution | Hosted (B) - Production |
|--------|------------------------------|-------------------------|
| **MCP Implementation** | `claude_mcp_hybrid_sessions.py` (9,925 lines) | `claude_mcp_hybrid_sessions.py` (9,925 lines) ✅ IDENTICAL |
| **Wrapper** | 31-line bash script (direct execution) | 474-line HTTP server (server_hosted.py) |
| **Git Commit** | 68725b3 | 68725b3 ✅ SAME |

**Note**: `claude_mcp_hybrid.py` (8,326 lines) is OLD, NOT IN USE for months

---

## Delta 1: Transport Layer

### Local (A)
- **Transport**: stdio (standard input/output)
- **Protocol**: Native MCP over stdio
- **Client**: Claude Desktop direct connection
- **Launcher**: `claude-dementia-server.sh` (31 lines bash script)
```bash
exec python3 "$SCRIPT_DIR/claude_mcp_hybrid.py" "$@"
```

### Hosted (B)
- **Transport**: HTTP/HTTPS (Starlette ASGI)
- **Protocol**: MCP Streamable HTTP
- **Client**: Claude Desktop via `npx` or Claude.ai via OAuth
- **Server**: `server_hosted.py` (474 lines Python)
```python
app = mcp.streamable_http_app()  # FastMCP's Starlette app
uvicorn.run(app, host="0.0.0.0", port=8080)
```

**Impact**: Completely different transport mechanisms

---

## Delta 2: Authentication

### Local (A)
- **Auth**: NONE
- **Security**: Relies on local filesystem security
- **Access**: Anyone with local shell access

### Hosted (B)
- **Auth**: Bearer token authentication (BearerAuthMiddleware)
- **OAuth Support**: OAuth 2.0 mock for Claude.ai compatibility
- **API Key**: Static token validation (`DEMENTIA_API_KEY`)
```python
# server_hosted.py:68-116
class BearerAuthMiddleware(BaseHTTPMiddleware):
    # Validates Bearer tokens (static or OAuth)
    # Returns 401 with WWW-Authenticate header if invalid
```

**Impact**: Hosted requires authentication, local does not

---

## Delta 3: Middleware Stack

### Local (A)
- **Middleware**: NONE
- **Request Processing**: Direct tool execution
- **Logging**: Basic stderr output

### Hosted (B)
- **Middleware**: 5-layer stack (execution order):
  1. `TimeoutMiddleware` - 45s timeout
  2. `MCPRequestLoggingMiddleware` - Request/response logging
  3. `MCPSessionPersistenceMiddleware` - PostgreSQL session storage
  4. `BearerAuthMiddleware` - Authentication
  5. `CorrelationIdMiddleware` - Request tracing

```python
# server_hosted.py:437-445
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(BearerAuthMiddleware)
app.add_middleware(MCPSessionPersistenceMiddleware, db_pool=adapter)
app.add_middleware(MCPRequestLoggingMiddleware)
app.add_middleware(TimeoutMiddleware)
```

**Impact**: Hosted has comprehensive middleware for production reliability

---

## Delta 4: Database Initialization

### Local (A)
- **Initialization**: Lazy (on first tool call)
- **Connection**: Created when needed
- **Pooling**: No explicit pooling (relies on psycopg2 defaults)

### Hosted (B)
- **Initialization**: Eager (at module load)
- **Connection**: Pre-warmed before serving requests
- **Pooling**: Explicit connection pool initialization
```python
# server_hosted.py:411-423
from claude_mcp_hybrid_sessions import _get_db_adapter
adapter = None
try:
    logger.info("database_initialization_start")
    adapter = _get_db_adapter()
    logger.info("database_initialization_success", schema=adapter.schema)
except Exception as e:
    logger.error("database_initialization_failed", error=str(e))
```

**Impact**: Hosted handles Neon database cold starts (10-15s wake time)

---

## Delta 5: Custom Routes

### Local (A)
- **Routes**: NONE (stdio doesn't use routes)
- **Endpoints**: N/A

### Hosted (B)
- **Routes**: 5 custom HTTP endpoints + OAuth routes
```python
# server_hosted.py:427-435
Route('/health', health_check, methods=['GET'])           # Unauthenticated
Route('/session-health', session_health_endpoint)         # Authenticated
Route('/tools', list_tools_endpoint)                      # Authenticated
Route('/execute', execute_tool_endpoint)                  # Authenticated
Route('/metrics', metrics_endpoint)                       # Authenticated
+ OAUTH_ROUTES (/.well-known/oauth-*, /oauth/authorize, /oauth/token)
```

**Impact**: Hosted exposes HTTP API for programmatic access

---

## Delta 6: Session Management

### Local (A) - claude_mcp_hybrid.py
- **Session Tracking**: NO (original version)
- **Session ID**: None
- **Session Store**: None

### Local (A) - claude_mcp_hybrid_sessions.py
- **Session Tracking**: YES (fork with sessions)
- **Session ID**: `_local_session_id` global variable
- **Session Store**: `PostgreSQLSessionStore` instance
```python
# claude_mcp_hybrid_sessions.py:74-79
_local_session_id = None
_session_store = None
```

### Hosted (B)
- **Session Tracking**: YES (via middleware)
- **Session ID**: Stable hash(api_key + user_agent)
- **Session Store**: Middleware-managed PostgreSQL sessions
```python
# server_hosted.py:442-443
app.add_middleware(MCPSessionPersistenceMiddleware, db_pool=adapter)
```

**Impact**: Hosted has stable session IDs across reconnections

---

## Delta 7: Logging

### Local (A)
- **Format**: Plain text to stderr
- **Structure**: Unstructured
- **Destination**: Console only
- **Example**: `✅ PostgreSQL/Neon connected (schema: dementia_abc123)`

### Hosted (B)
- **Format**: Structured JSON (via `structlog`)
- **Structure**: Key-value pairs with metadata
- **Destination**: stdout (DigitalOcean logs)
- **Correlation**: Request correlation IDs
```python
# server_hosted.py:39-62
from src.logging_config import configure_logging, get_logger
configure_logging(environment=ENVIRONMENT, log_level=LOG_LEVEL)
logger = get_logger(__name__)

# Example output:
# {"timestamp":"2025-11-16T16:34:09Z","level":"INFO","event":"tool_execute_start","tool":"wake_up","correlation_id":"req-12345"}
```

**Impact**: Hosted has production-grade observability

---

## Delta 8: Metrics

### Local (A)
- **Metrics**: NONE
- **Monitoring**: No instrumentation

### Hosted (B)
- **Metrics**: Prometheus-compatible
- **Endpoint**: `/metrics` (authenticated)
- **Tracked**:
  - `active_connections`
  - `tool_invocations` (by tool name, status)
  - `request_size_bytes`
  - `response_size_bytes`
```python
# server_hosted.py:40-46
from src.metrics import (
    active_connections,
    get_metrics_text,
    tool_invocations,
    request_size_bytes,
    response_size_bytes
)
```

**Impact**: Hosted has observability for monitoring/alerting

---

## Delta 9: Error Handling

### Local (A)
- **Timeout**: None (can hang indefinitely)
- **Error Response**: Plain text or JSON
- **Logging**: stderr print statements

### Hosted (B)
- **Timeout**: 45 seconds (TimeoutMiddleware)
- **Error Response**: Structured JSON with status codes
- **Logging**: Structured logs with tracebacks
```python
# server_hosted.py:183-218
class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=45.0
            )
            # Warn on slow requests (>20s)
            if elapsed > 20:
                logger.warning("slow_request", ...)
```

**Impact**: Hosted prevents hanging requests

---

## Delta 10: Deployment Configuration

### Local (A)
- **Environment**: Local machine (macOS Darwin 25.1.0)
- **Working Directory**: Project root (`/Users/banton/Sites/claude-dementia`)
- **Environment Variables**: `.env` file (local)
- **Runtime**: Python 3 (system python3)

### Hosted (B)
- **Environment**: DigitalOcean App Platform (NYC region)
- **Working Directory**: Container filesystem
- **Environment Variables**: DigitalOcean dashboard (encrypted)
- **Runtime**: Gunicorn/Uvicorn in Docker container
- **Health Check**: `/health` endpoint (200 OK required)
- **Port**: 8080 (fixed)
- **Build**: `pip install -r requirements.txt`

**Impact**: Different runtime environments

---

## Delta 11: MCP Implementation File

### Local (A)
**Launcher uses**: `claude_mcp_hybrid_sessions.py` (9,925 lines)
```bash
# claude-dementia-server.sh:31
exec python3 "$SCRIPT_DIR/claude_mcp_hybrid_sessions.py" "$@"
```

### Hosted (B)
**Server imports**: `claude_mcp_hybrid_sessions.py` (9,925 lines)
```python
# server_hosted.py:32
from claude_mcp_hybrid_sessions import mcp
```

**✅ IDENTICAL MCP IMPLEMENTATION** - Both use the SAME file!

**Note**: `claude_mcp_hybrid.py` (8,326 lines) is the OLD version, NOT IN USE for months

---

## Delta 12: Configuration Source

### Local (A)
```bash
# .env (local file)
DATABASE_URL=postgresql://neondb_owner:...@ep-jolly-shadow...
VOYAGEAI_API_KEY=pa-w3lSPJ_I5V1yuAdJsyHIffebuEQ7fWA2N4VOrDGctke
OPENROUTER_API_KEY=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
DEMENTIA_API_KEY=wWKYw3FTk_IhCCVwwmKopF7RTvGn8yDEFobOyEXZOHU
```

### Hosted (B)
```python
# DigitalOcean Environment Variables (encrypted in dashboard)
DATABASE_URL=<same>
VOYAGEAI_API_KEY=<same>
OPENROUTER_API_KEY=<same>
DEMENTIA_API_KEY=<same>
ENVIRONMENT=production
LOG_LEVEL=INFO
```

**Impact**: Same secrets, different storage mechanisms

---

## Delta 13: Client Configuration

### Local (A)
```json
// Claude Desktop config.json
{
  "mcpServers": {
    "dementia": {
      "command": "/Users/banton/Sites/claude-dementia/claude-dementia-server.sh",
      "args": []
    }
  }
}
```

### Hosted (B)
```json
// Claude Desktop config.json (via npx)
{
  "mcpServers": {
    "dementia-cloud": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-everything",
        "https://dementia-mcp-7f4vf.ondigitalocean.app"
      ],
      "env": {
        "DEMENTIA_API_KEY": "wWKYw3FTk_IhCCVwwmKopF7RTvGn8yDEFobOyEXZOHU"
      }
    }
  }
}
```

**Impact**: Different connection methods

---

## Delta 14: Dependency Differences

### Local (A)
```txt
# requirements.txt (subset)
mcp
psycopg2-binary
anthropic
```

### Hosted (B)
```txt
# requirements.txt (adds production deps)
mcp
psycopg2-binary
anthropic
fastapi          # ← NEW (not actually used, uses Starlette)
uvicorn[standard]  # ← NEW
starlette        # ← NEW (FastMCP uses this)
structlog        # ← NEW (structured logging)
prometheus-client # ← NEW (metrics)
```

**Impact**: Hosted requires additional HTTP/monitoring dependencies

---

## Delta 15: Process Model

### Local (A)
- **Process**: Single Python process
- **Lifetime**: Tied to Claude Desktop session
- **Restart**: Automatic on Claude Desktop reconnect
- **State**: In-memory (resets on restart)

### Hosted (B)
- **Process**: Uvicorn worker(s)
- **Lifetime**: Continuous (always running)
- **Restart**: DigitalOcean handles crashes
- **State**: PostgreSQL (persistent across restarts)

**Impact**: Hosted is stateless, local is ephemeral

---

## Critical Differences Summary

### Architectural Deltas
1. ✅ **Transport**: stdio vs HTTP
2. ✅ **Authentication**: None vs Bearer token
3. ✅ **Middleware**: None vs 5-layer stack
4. ✅ **Database Init**: Lazy vs Eager
5. ✅ **Routes**: None vs 5 HTTP endpoints
6. ✅ **Logging**: stderr vs structured JSON
7. ✅ **Metrics**: None vs Prometheus
8. ✅ **Error Handling**: No timeout vs 45s timeout
9. ✅ **Session Management**: Local variable vs Middleware-managed stable IDs

### Code Deltas
10. ✅ **MCP Implementation**: `claude_mcp_hybrid.py` (8,326 lines) vs `claude_mcp_hybrid_sessions.py` (9,925 lines, +19%)
11. ✅ **Wrapper Layer**: 31-line bash script vs 474-line HTTP server
12. ✅ **Dependencies**: Minimal vs Production stack

### Operational Deltas
13. ✅ **Environment**: Local macOS vs DigitalOcean container
14. ✅ **Configuration**: `.env` file vs Dashboard env vars
15. ✅ **Process Model**: Ephemeral vs Stateless continuous

---

## Which Version is "Working"?

**User specified**: Local (A) is the "working solution"

**Reality check**:
- Local: Works for stdio/Claude Desktop ✅
- Hosted: Deployed at commit 68725b3, ACTIVE ✅
- BOTH work in their respective environments

**Key Insight**: They are NOT broken vs working, but **LOCAL vs PRODUCTION** architectures.

---

## Recommendations

### If Issue with Hosted
Check these deltas first:
1. Session ID stability (middleware vs local global)
2. Authentication (could block valid requests)
3. Timeout (45s limit might be too short)
4. Database connection (eager init might fail on cold start)
5. Middleware order (could affect request processing)

### If Merging Features
To bring hosted features to local:
- Add session persistence middleware (optional for local)
- Add logging (optional, stderr works)
- Keep stdio transport (required for local)

To bring local features to hosted:
- Already done (hosted imports `claude_mcp_hybrid_sessions.py`)

---

## Testing Plan

To verify deltas don't cause functional differences:

1. **Test same MCP tools on both**:
   - Local: `list_projects()` via Claude Desktop
   - Hosted: `POST /execute {"tool": "list_projects"}` via curl
   - Expected: Same results

2. **Test session persistence**:
   - Local: Restart MCP server, check if session persists
   - Hosted: Disconnect/reconnect, check if session persists
   - Expected: Hosted persists, local may not

3. **Test project isolation**:
   - Both: Switch projects, verify contexts are isolated
   - Expected: Identical behavior (schema-based isolation)

4. **Test multi-project switching**:
   - Both: `select_project_for_session('linkedin')` → `search_contexts("auth")`
   - Expected: Returns linkedin contexts, not other projects

---

**Analysis Complete**: 15 systematic deltas identified, all architectural (no code differences at commit level).
