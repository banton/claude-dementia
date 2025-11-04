# MCP Cloud-Hosted Protocol Documentation

## Overview

This document describes the expected protocol flow for cloud-hosted MCP servers accessed by Claude Desktop via HTTP transport.

## Architecture

```
Claude Desktop → HTTP Client → Cloud MCP Server → Database
                    ↓                ↓
               (Bearer Auth)   (Tool Execution)
```

## Complete Request/Response Flow

```mermaid
sequenceDiagram
    participant CD as Claude Desktop
    participant MW as Auth Middleware
    participant CID as Correlation ID Middleware
    participant MCP as MCP Handler (/mcp)
    participant Tool as Tool Function
    participant DB as Database

    Note over CD,DB: Successful Tool Execution Flow

    CD->>MW: POST /mcp<br/>Authorization: Bearer {token}<br/>Content-Type: application/json<br/>{jsonrpc request}

    MW->>MW: Validate Bearer token
    alt Auth Failed
        MW-->>CD: 401 Unauthorized<br/>{"detail": "Invalid API key"}
    end

    MW->>CID: Request authenticated
    CID->>CID: Generate/extract correlation ID
    CID->>MCP: Add X-Correlation-ID header

    MCP->>MCP: Parse JSON-RPC request<br/>{<br/>  "jsonrpc": "2.0",<br/>  "id": 1,<br/>  "method": "tools/call",<br/>  "params": {<br/>    "name": "wake_up",<br/>    "arguments": {...}<br/>  }<br/>}

    alt Invalid JSON-RPC Format
        MCP-->>CD: 400 Bad Request<br/>{"error": "Invalid request"}
    end

    MCP->>Tool: Call tool function<br/>await wake_up(...)
    Tool->>DB: Connect to database<br/>(may wake from idle)

    alt Database Connection Failed
        DB-->>Tool: ConnectionError
        Tool-->>MCP: Raise exception
        MCP-->>CD: 500 Internal Server Error<br/>{"error": "DB connection failed"}
    end

    DB-->>Tool: Connection successful
    Tool->>DB: Execute queries
    DB-->>Tool: Query results
    Tool-->>MCP: Return result string/JSON

    MCP->>MCP: Format JSON-RPC response<br/>{<br/>  "jsonrpc": "2.0",<br/>  "id": 1,<br/>  "result": {<br/>    "content": [{<br/>      "type": "text",<br/>      "text": "{result}"<br/>    }]<br/>  }<br/>}

    MCP-->>CD: 200 OK<br/>X-Correlation-ID: {id}<br/>{jsonrpc response}
    CD->>CD: Display result to user

    Note over CD,DB: Timeout Scenario

    CD->>MW: POST /mcp (tool call)
    MW->>CID: Auth OK
    CID->>MCP: Forward request
    MCP->>Tool: Execute tool
    Tool->>DB: Wake from idle (10-15s)

    alt Client Timeout (30s)
        CD->>CD: Client timeout
        CD-->>CD: "Tool ran without output"
        Note over Tool,DB: Server continues processing
        DB-->>Tool: Wake complete
        Tool-->>MCP: Return result
        MCP-->>CD: 200 OK (too late)
        CD->>CD: Response discarded
    end
```

## Request Format (JSON-RPC 2.0)

### Tool Call Request
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "wake_up",
    "arguments": {
      "project": "claude_dementia"
    }
  }
}
```

### Headers Required
```http
POST /mcp HTTP/1.1
Host: dementia-mcp-server-x8fkw.ondigitalocean.app
Authorization: Bearer {DEMENTIA_API_KEY}
Content-Type: application/json
X-Correlation-ID: req-1730727043123 (optional)
```

## Response Format (JSON-RPC 2.0)

### Success Response
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"session_id\": \"abc123\", \"status\": \"ok\"}"
      }
    ]
  }
}
```

### Error Response (Application Error)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Internal error",
    "data": {
      "detail": "Database connection failed"
    }
  }
}
```

### HTTP Error Responses

#### 400 Bad Request
- Malformed JSON-RPC request
- Missing required fields
- Invalid method name
- Invalid tool name

#### 401 Unauthorized
- Missing Authorization header
- Invalid Bearer token
- Expired credentials

#### 500 Internal Server Error
- Tool execution exception
- Database connection failure
- Unexpected server error

## Timeout Behavior

### Claude Desktop Client Timeouts
- **Default**: ~30 seconds for tool execution
- **Behavior**: If no response received, shows "Tool ran without output or errors"
- **Recovery**: Client abandons request, server may still be processing

### Server-Side Timeouts
- **Database statement timeout**: 30 seconds (postgres_adapter.py)
- **HTTP request timeout**: No explicit timeout (relies on Uvicorn/Starlette defaults)
- **Database wake time**: 10-15 seconds for Neon cold start

### Recommended Timeout Handling

1. **Client-side**: Increase timeout for slow operations
2. **Server-side**: Add request timeout middleware
3. **Database**: Optimize for faster wake (connection pooling)
4. **Tool-level**: Add progress callbacks for long operations

## Authentication Flow

```mermaid
sequenceDiagram
    participant Client
    participant BearerAuth as BearerAuthMiddleware
    participant Env as Environment Variables

    Client->>BearerAuth: Request with Authorization header
    BearerAuth->>BearerAuth: Extract Bearer token
    BearerAuth->>Env: Get DEMENTIA_API_KEY

    alt No API key in environment
        BearerAuth-->>Client: 401 Unauthorized
    end

    BearerAuth->>BearerAuth: secrets.compare_digest(token, api_key)

    alt Token mismatch
        BearerAuth-->>Client: 401 Unauthorized
    end

    BearerAuth->>Client: Continue to handler
```

## Database Connection Flow

```mermaid
sequenceDiagram
    participant Tool
    participant Adapter as PostgresAdapter
    participant Pool as Connection Pool
    participant Neon as Neon Database

    Tool->>Adapter: _get_db_adapter(schema)
    Adapter->>Adapter: Check _adapters cache

    alt Adapter exists
        Adapter-->>Tool: Return cached adapter
    else Adapter not cached
        Adapter->>Adapter: Create new adapter
        Adapter->>Pool: Create SimpleConnectionPool(1, 10)
        Adapter->>Adapter: Cache in _adapters
        Adapter-->>Tool: Return new adapter
    end

    Tool->>Adapter: get_connection()
    Adapter->>Pool: pool.getconn()
    Pool->>Neon: Establish connection

    alt Database is idle
        Neon->>Neon: Wake from suspension (10-15s)
        Neon-->>Pool: Connection ready
    else Database is active
        Neon-->>Pool: Connection ready (instant)
    end

    Pool-->>Adapter: Connection object
    Adapter->>Adapter: SET statement_timeout = '30s'
    Adapter-->>Tool: Return connection

    Tool->>Tool: Execute queries
    Tool->>Adapter: Close connection
    Adapter->>Pool: pool.putconn(conn)
```

## Current Issues Identified

### Issue 1: 400 Bad Request on Tool Calls
**Symptom**: `POST /mcp HTTP/1.1" 400 Bad Request`
- Requests fail before reaching tool execution
- No logs showing tool invocation
- Happens with both `sleep` and `wake_up`

**Possible Causes**:
1. Invalid JSON-RPC format from client
2. Missing required MCP protocol fields
3. Unsupported method name
4. FastMCP protocol version mismatch

**Investigation Needed**:
- [ ] Enable request body logging in server_hosted.py
- [ ] Verify Claude Desktop sends valid JSON-RPC 2.0 format
- [ ] Check FastMCP's expected request structure
- [ ] Add error logging before 400 response

### Issue 2: 30+ Second Timeout with No Output
**Symptom**: Tools return "Tool ran without output or errors"
- Client waits 30+ seconds
- No response received
- Database remains idle (no wake event)

**Possible Causes**:
1. Request rejected at HTTP layer (400) before reaching tool
2. Tool executes but response format invalid
3. Client timeout shorter than database wake time
4. Response lost during transmission

**Investigation Needed**:
- [ ] Add request/response logging middleware
- [ ] Measure actual database wake time
- [ ] Test with curl to isolate client vs server
- [ ] Add timeout middleware to detect slow requests

## Testing Protocol Compliance

### Manual Test with curl

```bash
# Test authentication
curl -X POST https://dementia-mcp-server-x8fkw.ondigitalocean.app/mcp \
  -H "Authorization: Bearer ${DEMENTIA_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "wake_up",
      "arguments": {"project": "claude_dementia"}
    }
  }'

# Test without auth (should get 401)
curl -X POST https://dementia-mcp-server-x8fkw.ondigitalocean.app/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "wake_up",
      "arguments": {"project": "claude_dementia"}
    }
  }'

# Test invalid JSON-RPC (should get 400)
curl -X POST https://dementia-mcp-server-x8fkw.ondigitalocean.app/mcp \
  -H "Authorization: Bearer ${DEMENTIA_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "invalid": "request"
  }'
```

### Expected Responses

**Valid Request**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "..."}]
  }
}
```

**Invalid Auth**:
```json
{
  "detail": "Invalid API key"
}
```

**Invalid Request**:
```json
{
  "jsonrpc": "2.0",
  "id": null,
  "error": {
    "code": -32600,
    "message": "Invalid Request"
  }
}
```

## Recommendations

### 1. Add Request Logging Middleware
```python
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith('/mcp'):
            body = await request.body()
            logger.debug("mcp_request_received",
                        path=request.url.path,
                        method=request.method,
                        headers=dict(request.headers),
                        body=body.decode('utf-8'))

        response = await call_next(request)
        return response
```

### 2. Add Timeout Middleware
```python
class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()
        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=45.0  # 45s server timeout
            )
            return response
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error("request_timeout",
                        path=request.url.path,
                        elapsed_seconds=elapsed)
            return JSONResponse(
                status_code=504,
                content={"error": "Request timeout"}
            )
```

### 3. Improve Error Logging in FastMCP Handler
- Log raw request body before parsing
- Log parsing errors with details
- Log tool execution start/end
- Log response before sending

### 4. Test Database Wake Performance
```python
# Add timing to wake_up tool
start = time.time()
conn = _get_db_for_project(project)
wake_time = time.time() - start
logger.info("database_wake_time", seconds=wake_time)
```

## Next Steps

1. Add request logging middleware to capture 400 errors
2. Test with curl to verify MCP protocol compliance
3. Measure database wake time under cold start
4. Add timeout middleware for long operations
5. Document findings and update this file
