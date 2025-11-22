# Testing Readiness Plan - 3 Week Multi-Site Single-Tenant Testing

## Goal
Stabilize the Custom Connector integration enough for **3 weeks of real-world testing** with comprehensive logging to audit stability and performance.

NOT production-ready - testing-ready.

## Critical Cleanup Tasks (Must Fix Before Testing)

### Priority 1: Core Functionality (Blockers)
**Timeline: 1-2 days**

- [ ] **Fix project creation** (`create_project` tool fails)
  - Debug why project creation errors occur
  - Test with Custom Connector
  - Verify project schema creation in PostgreSQL

- [ ] **Fix project switching/routing** (default → workspace bug)
  - Trace session state during project switch
  - Debug why context gets routed to wrong project
  - Verify project isolation works correctly

- [ ] **Test all 31 MCP tools via Custom Connector**
  - Create test script that calls each tool
  - Document which tools work/fail
  - Fix critical tool failures

- [ ] **Persist OAuth codes in PostgreSQL** (not memory)
  - Create `oauth_authorization_codes` table
  - Migrate code storage from dict to database
  - Add cleanup job for expired codes
  - Test across server restarts

### Priority 2: Stability (Important for Testing)
**Timeline: 1 day**

- [ ] **Fix session management for Custom Connector**
  - Debug session selection/creation errors
  - Ensure sessions persist across requests
  - Test session handover functionality

- [ ] **Add error handling to all MCP tools**
  - Wrap tools in try/catch with proper error responses
  - Return user-friendly error messages
  - Log errors with context for debugging

- [ ] **Test multi-project workflows**
  - Create → Switch → Lock → Recall across 3+ projects
  - Verify isolation (contexts don't leak between projects)
  - Test concurrent project operations

### Priority 3: Data Integrity (Testing Quality)
**Timeline: 0.5 days**

- [ ] **Add database health checks**
  - Verify schema integrity on startup
  - Check for orphaned data
  - Validate foreign key relationships

- [ ] **Implement graceful degradation**
  - Handle PostgreSQL connection failures
  - Handle OAuth service failures
  - Return clear errors instead of crashes

## Comprehensive Logging & Monitoring Regime

### Layer 1: Request/Response Logging (Already Exists, Enhance)

**What to log:**
```python
{
  "timestamp": "ISO-8601",
  "correlation_id": "unique-per-request",
  "method": "POST|GET|DELETE",
  "path": "/mcp",
  "mcp_method": "tools/list|tools/call|...",
  "tool_name": "lock_context|recall_context|...",
  "project": "project_name",
  "session_id": "session_uuid",
  "user_agent": "Claude-User|Claude-Desktop",
  "has_auth": true|false,
  "status_code": 200|401|500,
  "elapsed_ms": 1234.56,
  "error": "error message if failed",
  "error_type": "ValueError|DatabaseError|..."
}
```

**Enhancements needed:**
- [ ] Add `tool_name` to all tool invocations
- [ ] Add `project` to all context operations
- [ ] Add `error_type` classification
- [ ] Add response payload size

### Layer 2: Database Operation Logging (NEW)

**What to log:**
```python
{
  "timestamp": "ISO-8601",
  "correlation_id": "matches request",
  "operation": "SELECT|INSERT|UPDATE|DELETE",
  "table": "context_locks|sessions|...",
  "project_schema": "dementia_abc123",
  "query_ms": 45.67,
  "rows_affected": 1,
  "error": "if query failed"
}
```

**Implementation:**
- [ ] Add logging to `postgres_adapter.py`
- [ ] Log all queries with timing
- [ ] Track connection pool stats
- [ ] Monitor query performance

### Layer 3: Tool Execution Logging (NEW)

**What to log:**
```python
{
  "timestamp": "ISO-8601",
  "correlation_id": "matches request",
  "tool": "lock_context",
  "project": "project_name",
  "parameters": {
    "topic": "api_spec",
    "content_size_bytes": 8192,
    "tags": "api,spec"
  },
  "result": "success|error",
  "execution_ms": 234.56,
  "database_calls": 3,
  "total_db_ms": 123.45,
  "error": "if failed"
}
```

**Implementation:**
- [ ] Add decorator to all MCP tools for automatic logging
- [ ] Track tool execution time
- [ ] Track database calls per tool
- [ ] Log tool parameters (sanitized)

### Layer 4: Session Lifecycle Logging (NEW)

**What to log:**
```python
{
  "timestamp": "ISO-8601",
  "event": "session_created|session_resumed|session_expired|project_switched",
  "session_id": "session_uuid",
  "project": "current_project",
  "previous_project": "if switched",
  "tool_calls": 0,
  "duration_minutes": 45,
  "last_activity": "ISO-8601"
}
```

**Implementation:**
- [ ] Log session creation in `mcp_session_store.py`
- [ ] Log session resume in middleware
- [ ] Log project switches
- [ ] Track session activity metrics

### Layer 5: OAuth Flow Logging (NEW)

**What to log:**
```python
{
  "timestamp": "ISO-8601",
  "event": "oauth_authorize|oauth_token|token_validate",
  "client_id": "client_xyz",
  "code_challenge": "present|missing",
  "code_verifier": "valid|invalid|missing",
  "token_issued": true|false,
  "error": "if failed"
}
```

**Implementation:**
- [ ] Add logging to `oauth_mock.py`
- [ ] Track OAuth flow completion rate
- [ ] Log authorization code lifecycle
- [ ] Monitor token validation

### Layer 6: Performance Metrics (NEW)

**What to track:**
```python
{
  "timestamp": "ISO-8601",
  "metric": "request_duration|db_query_duration|tool_execution",
  "p50": 123.45,
  "p95": 456.78,
  "p99": 789.12,
  "max": 2000.0,
  "count": 1000
}
```

**Implementation:**
- [ ] Add Prometheus histogram metrics for all operations
- [ ] Track percentiles (p50, p95, p99)
- [ ] Create `/metrics` dashboard
- [ ] Set up alerting thresholds

### Layer 7: Error Classification & Tracking (NEW)

**What to track:**
```python
{
  "timestamp": "ISO-8601",
  "error_type": "DatabaseConnectionError|ToolExecutionError|OAuthError|...",
  "error_message": "sanitized error",
  "stack_trace": "if available",
  "frequency": 5,
  "first_seen": "ISO-8601",
  "last_seen": "ISO-8601",
  "affected_tools": ["lock_context", "recall_context"],
  "affected_projects": ["project1", "project2"]
}
```

**Implementation:**
- [ ] Create error classification enum
- [ ] Track error frequency and patterns
- [ ] Group similar errors
- [ ] Alert on new error types

## Testing Period Monitoring Dashboard

### Daily Metrics to Track

**Stability:**
- Request success rate (target: >99%)
- Tool execution success rate (target: >95%)
- Database connection failures (target: 0)
- OAuth flow success rate (target: >98%)
- Session creation/resume success rate (target: >99%)

**Performance:**
- Request duration (p50, p95, p99)
- Database query duration (p50, p95, p99)
- Tool execution duration (p50, p95, p99)
- Memory usage (MB)
- Connection pool utilization (%)

**Usage:**
- Total requests per day
- Tool invocations per tool
- Active projects
- Active sessions
- Contexts created per day
- Database size growth (MB/day)

### Weekly Review Checklist

- [ ] Review error logs for patterns
- [ ] Check performance degradation trends
- [ ] Verify no data corruption in database
- [ ] Test project isolation (random audit)
- [ ] Review session handover quality
- [ ] Check OAuth code cleanup job
- [ ] Monitor database size growth
- [ ] Review connection pool stats

## Implementation Timeline

### Week 0 (Before Testing Starts): 2-3 days
- Fix critical bugs (project creation, switching)
- Test all 31 tools
- Implement core logging (Layers 1-3)
- Persist OAuth codes in PostgreSQL
- Deploy to staging
- Run 24-hour soak test

### Week 1 (Testing): Monitor + Fix
- Implement remaining logging (Layers 4-7)
- Monitor daily metrics
- Fix issues as they appear
- Daily log review

### Week 2 (Testing): Optimize
- Analyze performance metrics
- Optimize slow queries
- Add missing error handling
- Weekly review meeting

### Week 3 (Testing): Stabilize
- Focus on stability (no new features)
- Fix any remaining bugs
- Document lessons learned
- Prepare production plan

## Success Criteria for Testing Period

**Minimum Bar:**
- [ ] 95%+ request success rate over 3 weeks
- [ ] All 31 tools work via Custom Connector
- [ ] No data corruption detected
- [ ] Project isolation verified
- [ ] OAuth survives server restarts
- [ ] No security incidents
- [ ] Comprehensive logs for debugging

**Stretch Goals:**
- [ ] 99%+ request success rate
- [ ] p95 request duration <500ms
- [ ] Zero database connection failures
- [ ] Session handovers working perfectly
- [ ] Performance metrics trending stable

## Logging Best Practices

**DO:**
- Use structured logging (JSON)
- Include correlation IDs in all logs
- Log timestamps in ISO-8601 UTC
- Sanitize sensitive data (passwords, tokens)
- Use log levels appropriately (DEBUG, INFO, WARNING, ERROR)
- Include context (project, session, user)

**DON'T:**
- Log full tokens or passwords
- Log huge payloads (>1KB - log size instead)
- Use print() statements (use logger)
- Mix logging styles (use structlog everywhere)
- Forget to add correlation IDs

## Next Steps

1. **Prioritize critical fixes** (project creation, switching)
2. **Implement core logging** (Layers 1-3)
3. **Test all tools** (create comprehensive test suite)
4. **Deploy to staging** with full logging
5. **Run 24-hour soak test** to catch crashes
6. **Begin 3-week testing period** with daily monitoring

---

**This is a testing readiness plan, NOT a production plan.**

The goal is to make it stable enough to learn from real-world usage over 3 weeks, with enough logging to understand what breaks and why.
