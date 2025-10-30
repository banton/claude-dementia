# Cloud-Hosted MCP API Specification

## Overview

This document specifies the HTTP/SSE (Server-Sent Events) API for the cloud-hosted Dementia MCP server. This enables remote access from Claude Desktop, mobile clients, and other MCP-compatible applications.

## Transport Protocol

**Base**: HTTP/REST + Server-Sent Events (SSE)
**Authentication**: Bearer Token (API Key)
**Content-Type**: `application/json`
**SSE Stream**: `text/event-stream`

## Authentication

All requests require Bearer token authentication:

```http
Authorization: Bearer YOUR_API_KEY
```

**Unauthorized Response** (401):
```json
{
  "error": "unauthorized",
  "message": "Missing or invalid API key"
}
```

## Core Endpoints

### 1. Health Check

**Endpoint**: `GET /health`
**Auth**: None (public)
**Purpose**: Container health check for DigitalOcean App Platform

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "4.2.0",
  "timestamp": "2025-01-30T12:34:56Z"
}
```

### 2. Metrics

**Endpoint**: `GET /metrics`
**Auth**: Bearer Token
**Purpose**: Observability metrics for monitoring

**Response** (200 OK):
```text
# HELP dementia_tool_invocations_total Total tool invocations
# TYPE dementia_tool_invocations_total counter
dementia_tool_invocations_total{tool="wake_up"} 42
dementia_tool_invocations_total{tool="lock_context"} 127

# HELP dementia_tool_latency_seconds Tool execution latency
# TYPE dementia_tool_latency_seconds histogram
dementia_tool_latency_seconds_bucket{tool="wake_up",le="0.5"} 40
dementia_tool_latency_seconds_bucket{tool="wake_up",le="1.0"} 42

# HELP dementia_active_connections Current active connections
# TYPE dementia_active_connections gauge
dementia_active_connections 3

# HELP dementia_error_rate_total Error rate per tool
# TYPE dementia_error_rate_total counter
dementia_error_rate_total{tool="lock_context"} 2
```

### 3. List Tools

**Endpoint**: `GET /mcp/tools`
**Auth**: Bearer Token
**Purpose**: Discover available MCP tools

**Response** (200 OK):
```json
{
  "tools": [
    {
      "name": "wake_up",
      "description": "Start development session and load context",
      "inputSchema": {
        "type": "object",
        "properties": {
          "project": {
            "type": "string",
            "description": "Project name (optional, auto-detected)"
          }
        }
      }
    },
    {
      "name": "lock_context",
      "description": "Lock immutable context with versioning",
      "inputSchema": {
        "type": "object",
        "required": ["content", "topic"],
        "properties": {
          "content": {"type": "string"},
          "topic": {"type": "string"},
          "tags": {"type": "string"},
          "priority": {"type": "string", "enum": ["always_check", "important", "reference"]}
        }
      }
    }
    // ... 21 more tools
  ]
}
```

### 4. Execute Tool (Request-Response)

**Endpoint**: `POST /mcp/execute`
**Auth**: Bearer Token
**Purpose**: Execute MCP tool and return result synchronously

**Request Body**:
```json
{
  "tool": "lock_context",
  "arguments": {
    "content": "DATABASE_URL=postgresql://...",
    "topic": "database_config",
    "priority": "important"
  }
}
```

**Response** (200 OK):
```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "tool": "lock_context",
  "success": true,
  "result": {
    "status": "locked",
    "version": 1,
    "size": 256,
    "hash": "a3f5b..."
  },
  "latency_ms": 45,
  "timestamp": "2025-01-30T12:34:56Z"
}
```

**Error Response** (400/500):
```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "tool": "lock_context",
  "success": false,
  "error": {
    "type": "validation_error",
    "message": "Missing required field: content"
  },
  "latency_ms": 12,
  "timestamp": "2025-01-30T12:34:56Z"
}
```

### 5. Execute Tool (Streaming)

**Endpoint**: `POST /mcp/execute/stream`
**Auth**: Bearer Token
**Content-Type**: `text/event-stream`
**Purpose**: Execute tool with streaming response for long-running operations

**Request Body**: Same as `/mcp/execute`

**SSE Stream Response**:
```text
event: start
data: {"correlation_id":"550e8400...","tool":"scan_project_files"}

event: progress
data: {"status":"scanning","files_scanned":100,"files_total":450}

event: progress
data: {"status":"scanning","files_scanned":250,"files_total":450}

event: result
data: {"success":true,"result":{"total_files":450,"added":12,"modified":5}}

event: end
data: {"latency_ms":1234}
```

## Structured Logging Format

All operations log JSON to stdout for DigitalOcean aggregation:

```json
{
  "timestamp": "2025-01-30T12:34:56.789Z",
  "level": "info",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_abc123",
  "project_id": "myproject",
  "tool_name": "lock_context",
  "latency_ms": 45,
  "success": true,
  "error_message": null,
  "metadata": {
    "topic": "database_config",
    "version": 1
  }
}
```

## Error Codes

| Code | Type | Description |
|------|------|-------------|
| 400 | Bad Request | Invalid input parameters |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | Valid key but insufficient permissions |
| 404 | Not Found | Tool or resource not found |
| 422 | Unprocessable Entity | Valid JSON but semantic validation failed |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Database connection failed |

## Rate Limiting (Future)

Not implemented in Phase 1. Headers reserved for future use:

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1609459200
```

## CORS Headers (Future)

For web-based MCP clients:

```http
Access-Control-Allow-Origin: https://claude.ai
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 86400
```

## Security Headers

All responses include:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
```

## Project/Schema Isolation

Multi-tenancy via Row-Level Security (RLS):

1. Client includes `project` parameter (optional)
2. Server resolves project via `_get_project_for_context()`:
   - Explicit parameter → use it
   - Session active project → use it
   - Auto-detect from filesystem → use detected schema
   - Default → `"default"`
3. All database queries scoped to `project_id` or schema

## Claude Desktop Custom Connector

Configuration for testing:

```json
{
  "mcpServers": {
    "dementia-cloud": {
      "transport": "http",
      "url": "https://dementia-mcp-abcd1234.ondigitalocean.app",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

## Future Enhancements (Not Phase 1)

- **OAuth 2.1**: Replace API keys with proper user authentication
- **WebSocket**: Real-time bidirectional communication
- **Valkey/Redis**: Caching layer for hot contexts
- **Rate limiting**: Per-user request throttling
- **Request validation**: OpenAPI schema validation
- **Batch execution**: Execute multiple tools in single request

## Implementation Notes

**FastAPI vs Flask**: FastAPI recommended for:
- Native async/await support
- Automatic OpenAPI documentation
- Type validation via Pydantic
- Built-in SSE support via `StreamingResponse`

**Database Connection**: Use connection pooling (psycopg2.pool) to avoid connection exhaustion under load.

**Session Management**: Generate UUID v4 session IDs, store in PostgreSQL with expiry timestamp. NO in-memory storage (containers are ephemeral).

**Error Handling**: Always catch exceptions at endpoint level, log structured error, return generic message to client. Never expose internal paths or stack traces.
