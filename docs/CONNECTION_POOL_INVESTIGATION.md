# Connection Pool Exhaustion Investigation

**Date**: 2025-11-04
**Issue**: dementia-cloud MCP server experiencing "connection pool exhausted" errors
**Status**: Root cause identified, solutions proposed

---

## Problem Statement

The dementia-cloud MCP server (hosted on DigitalOcean) experiences "connection pool exhausted" errors when calling tools like `wake_up()` and `explore_context_tree()`, while the local `claude_mcp_hybrid.py` server works fine with the same Neon database.

**Error from logs**:
```
❌ Connection failed after 5 attempts: connection pool exhausted
```

---

## Investigation Findings

### 1. Architecture Comparison

**Local Server (`claude_mcp_hybrid.py`)**:
- stdio transport (direct Python process)
- Single process serving one user
- Adapter caching implemented (`_adapter_cache` dictionary)
- Connections automatically released when process ends

**Cloud Server (`server_hosted.py` on DigitalOcean)**:
- HTTP transport (Starlette/Uvicorn)
- Long-running server process
- Multiple concurrent requests
- Same adapter caching code imported from `claude_mcp_hybrid.py`

### 2. Connection Pool Configuration

From `postgres_adapter.py` line 82-83:
```python
self.pool = psycopg2.pool.SimpleConnectionPool(
    1, 10,  # min=1, max=10 connections
    ...
)
```

**Each `PostgreSQLAdapter` creates a connection pool with 1-10 connections.**

### 3. Evidence from Production Logs

```
2025-11-04T09:03:14 ✅ PostgreSQL connection pool initialized (schema: workspace)
2025-11-04T13:15:25 ✅ PostgreSQL connection pool initialized (schema: toolbelt)
2025-11-04T13:15:25 ❌ Connection failed after 5 attempts: connection pool exhausted
```

**Observation**: Multiple connection pools are created (one per schema/project).

### 4. Root Cause Analysis

#### Primary Issue: Connection Leaks in Long-Running Server

The `AutoClosingPostgreSQLConnection` wrapper relies on Python's garbage collector (`__del__`) to return connections to the pool:

```python
class AutoClosingPostgreSQLConnection:
    def close(self):
        if not self._closed:
            self.adapter.release_connection(self.conn)
            self._closed = True

    def __del__(self):
        self.close()  # Called by garbage collector
```

**Problem**: In a long-running HTTP server:
1. **Non-deterministic garbage collection** - `__del__` may not be called immediately
2. **Reference cycles** - Connections held in closures/exception handlers
3. **Long request lifetimes** - Connections stay checked out during slow operations
4. **No timeout on `pool.getconn()`** - Blocks forever if pool is exhausted

#### Secondary Issue: Multiple Connection Pools

With multi-project support:
- 2 projects × 10 connections/project = 20 connections maximum
- Neon free tier: ~100 connections limit
- This alone shouldn't exhaust the pool

**But combined with connection leaks**, it compounds the problem.

### 5. Why Local Server Works

The local server works because:
1. **Short process lifetime** - Process exits after each tool call (stdio transport)
2. **Single user** - No concurrent requests
3. **OS-level cleanup** - All connections released when process exits
4. **No HTTP request lifecycle** - No middleware/handler holding references

---

## Proposed Solutions

### Solution 1: Add Context Manager Support (Immediate Fix)

**Priority**: HIGH
**Effort**: LOW (2-3 hours)
**Impact**: Prevents connection leaks

Modify `AutoClosingPostgreSQLConnection` to support `with` statements:

```python
class AutoClosingPostgreSQLConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # Keep existing __del__ as fallback
    def __del__(self):
        self.close()
```

Update tool implementations to use context managers:

```python
# BEFORE (prone to leaks)
def wake_up(project: Optional[str] = None) -> str:
    conn = _get_db_for_project(project)
    # ... use conn ...
    # Relies on __del__ to release connection

# AFTER (guaranteed release)
def wake_up(project: Optional[str] = None) -> str:
    with _get_db_for_project(project) as conn:
        # ... use conn ...
    # Connection released here, even if exception occurs
```

**Files to modify**:
- `claude_mcp_hybrid.py` - Add `__enter__/__exit__` to wrapper
- All tool functions - Wrap connection usage in `with` statements

### Solution 2: Add Connection Pool Monitoring (Short-term)

**Priority**: MEDIUM
**Effort**: LOW (1-2 hours)
**Impact**: Visibility into pool health

Add Prometheus metrics to track pool usage:

```python
from prometheus_client import Gauge

pool_connections_used = Gauge(
    'db_pool_connections_used',
    'Number of connections currently in use',
    ['schema']
)

pool_connections_available = Gauge(
    'db_pool_connections_available',
    'Number of available connections in pool',
    ['schema']
)

class PostgreSQLAdapter:
    def get_connection_stats(self):
        # psycopg2 pool doesn't expose stats directly
        # Need to track manually
        return {
            'total': 10,
            'used': self._connections_used,
            'available': 10 - self._connections_used
        }
```

### Solution 3: Add Timeout to `pool.getconn()` (Short-term)

**Priority**: HIGH
**Effort**: LOW (30 minutes)
**Impact**: Prevents indefinite hangs

Wrap `pool.getconn()` with timeout:

```python
import signal
from contextlib import contextmanager

@contextmanager
def timeout_context(seconds):
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Connection pool timeout after {seconds}s")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

def get_connection(self, max_retries=5, initial_delay=2.0):
    for attempt in range(max_retries):
        try:
            with timeout_context(10):  # 10 second timeout
                conn = self.pool.getconn()
            # ... rest of code ...
```

### Solution 4: Reduce Connection Pool Size (Immediate Mitigation)

**Priority**: MEDIUM
**Effort**: TRIVIAL (5 minutes)
**Impact**: Reduces pressure on Neon

Change pool size from `SimpleConnectionPool(1, 10)` to `SimpleConnectionPool(1, 5)`:

```python
self.pool = psycopg2.pool.SimpleConnectionPool(
    1, 5,  # Reduced from 10 to 5
    ...
)
```

**Rationale**:
- Most tools only use 1 connection at a time
- With 5 projects × 5 connections = 25 max (vs 50 currently)
- Still allows some concurrency

### Solution 5: Connection Pool Cleanup on Idle (Long-term)

**Priority**: LOW
**Effort**: MEDIUM (4-6 hours)
**Impact**: Proactive cleanup of stale connections

Add background task to release idle connections:

```python
async def cleanup_idle_connections():
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        for schema, adapter in _adapter_cache.items():
            # Close idle connections (requires psycopg2 extension)
            adapter.cleanup_idle_connections(max_idle_time=600)
```

---

## Recommended Implementation Plan

### Phase 1: Immediate Fixes (Today)
1. ✅ **Solution 4**: Reduce pool size to 5 connections (deploy immediately)
2. ✅ **Solution 3**: Add timeout to `pool.getconn()` (prevent hangs)

### Phase 2: Proper Fix (This Week)
3. ✅ **Solution 1**: Add context manager support + update all tools
4. ✅ **Solution 2**: Add connection pool monitoring

### Phase 3: Long-term Improvements (Next Sprint)
5. ⏳ **Solution 5**: Implement idle connection cleanup
6. ⏳ Consider migrating to connection pooling proxy (PgBouncer)

---

## Testing Strategy

### 1. Local Integration Tests

Create test that simulates connection pool exhaustion:

```python
def test_connection_pool_recovery_under_load():
    """Test that connections are properly released under concurrent load."""

    # Create small pool to force exhaustion
    adapter = PostgreSQLAdapter(max_connections=2)

    # Simulate concurrent requests
    async def make_request():
        with adapter.get_connection() as conn:
            await asyncio.sleep(0.1)  # Simulate slow query
            return conn.execute("SELECT 1")

    # Run 10 concurrent requests with pool of 2
    results = await asyncio.gather(*[make_request() for _ in range(10)])

    # All requests should succeed (connections reused)
    assert len(results) == 10
```

### 2. Production Deployment Test

```bash
# Deploy fixes to staging
doctl apps update <app-id> --spec .do/app-staging.yaml

# Run load test
for i in {1..50}; do
    curl -H "Authorization: Bearer $API_KEY" \
         https://staging.app/execute \
         -d '{"tool":"wake_up","arguments":{}}' &
done
wait

# Check metrics
curl https://staging.app/metrics | grep db_pool
```

### 3. Monitor Production

Watch for connection pool errors for 24 hours:

```bash
# Stream logs and filter for connection errors
doctl apps logs <app-id> --follow | grep -i "pool\|exhaust"
```

---

## Neon Database Considerations

### Connection Limits

**Neon Free Tier**:
- Max connections: ~100
- Pool mode: Transaction pooling
- Idle timeout: 5 minutes
- Compute auto-suspend: After inactivity

**Our Usage**:
- Current: 2-5 projects × 10 connections = 20-50 connections
- After fix: 2-5 projects × 5 connections = 10-25 connections
- Safe margin: 75 connections free for spikes

### Transaction Pooling Implications

Neon uses **transaction pooling** (`pool_mode=transaction`), which means:
- Each connection handles multiple transactions
- SET statements only persist for one transaction
- Must use `ALTER ROLE` for persistent settings (already implemented)

**Already handled** in `postgres_adapter.py` line 294-300:
```python
# CRITICAL FIX: Set search_path at ROLE level
cur.execute(
    sql.SQL("ALTER ROLE {} SET search_path TO {}, public").format(
        sql.Identifier(role_name),
        sql.Identifier(self.schema)
    )
)
```

---

## Related Files

- `server_hosted.py` - Cloud MCP server (imports from claude_mcp_hybrid)
- `claude_mcp_hybrid.py` - Local MCP server (defines tools and adapters)
- `postgres_adapter.py` - PostgreSQL connection pooling
- `tests/integration/test_mcp_session_persistence.py` - Integration tests

---

## Next Steps

1. **Implement Phase 1 fixes** (Solution 3 + 4)
2. **Test locally** with connection pool stress test
3. **Deploy to production**
4. **Monitor for 24 hours**
5. **Implement Phase 2** if issue persists
6. **Document learnings** for future reference

---

**Author**: Claude Code
**Reviewed**: Pending
**Status**: Investigation Complete, Awaiting Implementation
