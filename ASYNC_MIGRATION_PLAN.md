# Async Architecture Migration Plan

**Goal:** Convert entire stack to true async (asyncpg) for proper non-blocking database operations

**Date:** 2025-11-22
**Status:** DESIGN PHASE - Awaiting Approval

---

## Problem Statement

### Current Architecture (Blocking)
```
FastMCP (async)
  ↓
MCP Tools (async def)
  ↓
PostgreSQLAdapter (def) ← BLOCKS HERE
  ↓
psycopg2 (sync)
  ↓
PostgreSQL
```

**Issues:**
- Tools are `async def` but call sync database methods
- Session middleware makes sync DB calls in async context → 7-12s delays
- Event loop blocking when middleware + tools both use sync DB
- Cannot use session persistence without blocking

### Target Architecture (Non-Blocking)
```
FastMCP (async)
  ↓
MCP Tools (async def)
  ↓
PostgreSQLAdapterAsync (async def) ← FULLY ASYNC
  ↓
asyncpg (async)
  ↓
PostgreSQL
```

**Benefits:**
- True async from top to bottom
- No event loop blocking
- Session middleware can safely make DB calls
- Can re-enable project selection
- Faster under concurrent load (if we scale to multi-user)

---

## Migration Strategy

### Phase 1: Create Async Database Layer ✅
**Files to Create:**
- `postgres_adapter_async.py` - New async adapter using asyncpg

**Implementation:**
```python
# postgres_adapter_async.py
import asyncpg
from typing import Optional

class PostgreSQLAdapterAsync:
    """Fully async PostgreSQL adapter using asyncpg."""

    def __init__(self, database_url: Optional[str] = None, schema: Optional[str] = None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.schema = schema or self._get_schema_name()
        self._pool: Optional[asyncpg.Pool] = None

    async def get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
        return self._pool

    async def execute_query(self, query: str, params=None):
        """Execute SELECT query, return rows."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"SET search_path TO {self.schema}")
            rows = await conn.fetch(query, *(params or []))
            return [dict(row) for row in rows]

    async def execute_update(self, query: str, params=None):
        """Execute INSERT/UPDATE/DELETE."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"SET search_path TO {self.schema}")
            result = await conn.execute(query, *(params or []))
            return result

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
```

**Key Differences from psycopg2:**
- Connection pooling built-in (asyncpg.create_pool)
- `await` required for all operations
- Returns list of dicts (like psycopg2 RealDictCursor)
- Parameter placeholders: `$1, $2, $3` instead of `%s`

---

### Phase 2: Convert Session Store to Async ✅
**Files to Modify:**
- `mcp_session_store.py`

**Changes:**
```python
# BEFORE (blocking)
class PostgreSQLSessionStore:
    def create_session(self, session_id: str, project_name: str):
        conn = self.db_adapter.get_connection()  # BLOCKS
        with conn.cursor() as cur:
            cur.execute("INSERT ...")

# AFTER (async)
class PostgreSQLSessionStore:
    async def create_session(self, session_id: str, project_name: str):
        await self.db_adapter.execute_update(
            "INSERT INTO sessions (id, project_name) VALUES ($1, $2)",
            [session_id, project_name]
        )
```

**Methods to Convert:**
- ✅ `create_session()` → `async def create_session()`
- ✅ `get_session()` → `async def get_session()`
- ✅ `update_activity()` → `async def update_activity()`
- ✅ `get_active_sessions()` → `async def get_active_sessions()`
- ✅ `cleanup_expired_sessions()` → `async def cleanup_expired_sessions()`

---

### Phase 3: Convert Session Middleware to Async ✅
**Files to Modify:**
- `mcp_session_middleware.py`

**Changes:**
```python
# BEFORE (blocking sync calls)
existing_session = self.session_store.get_session(stable_session_id)  # BLOCKS
result = self.session_store.create_session(...)  # BLOCKS

# AFTER (async)
existing_session = await self.session_store.get_session(stable_session_id)
result = await self.session_store.create_session(...)
```

**Critical Fix:**
This removes the 7-12s blocking delay we discovered in testing.

---

### Phase 4: Convert All MCP Tools ✅
**Files to Modify:**
- `claude_mcp_hybrid_sessions.py` (all tools)

**Pattern to Apply:**
```python
# BEFORE (blocking)
async def lock_context(content: str, topic: str):
    conn = adapter.get_connection()  # BLOCKS
    with conn.cursor() as cur:
        cur.execute("INSERT ...")

# AFTER (async)
async def lock_context(content: str, topic: str):
    await adapter.execute_update(
        "INSERT INTO context_locks (content, topic) VALUES ($1, $2)",
        [content, topic]
    )
```

**Tools to Convert (~30 tools):**
- lock_context
- recall_context
- unlock_context
- search_contexts
- semantic_search_contexts
- query_database
- execute_sql
- get_last_handover
- create_project
- list_projects
- switch_project
- etc. (all database-using tools)

---

### Phase 5: Update Server Initialization ✅
**Files to Modify:**
- `server_hosted.py`

**Changes:**
```python
# BEFORE (sync adapter)
from postgres_adapter import PostgreSQLAdapter
adapter = PostgreSQLAdapter()

# AFTER (async adapter)
from postgres_adapter_async import PostgreSQLAdapterAsync
adapter = None  # Initialize in lifespan

@asynccontextmanager
async def lifespan_with_async_db(app_instance):
    """Initialize async database pool on startup."""
    global adapter
    adapter = PostgreSQLAdapterAsync()
    await adapter.get_pool()  # Create pool

    # Start keep-alive (can stay as is)
    keepalive_task = asyncio.create_task(...)

    yield

    # Cleanup
    await adapter.close()
    keepalive_task.cancel()
```

---

### Phase 6: Update Keep-Alive for Async ✅
**Files to Modify:**
- `database_keepalive.py`

**Changes:**
```python
# BEFORE (sync)
def ping_database_once(db_adapter) -> tuple[bool, float]:
    conn = db_adapter.get_connection()
    cur.execute("SELECT 1")

# AFTER (async)
async def ping_database_once(db_adapter) -> tuple[bool, float]:
    result = await db_adapter.execute_query("SELECT 1")
    return (True, elapsed_ms)

async def start_keepalive_scheduler(db_adapter, interval_seconds: int = 15):
    while True:
        await ping_database_once(db_adapter)
        await asyncio.sleep(interval_seconds)
```

---

## SQL Parameter Placeholder Migration

**Critical:** asyncpg uses `$1, $2, $3` instead of `%s, %s, %s`

**Migration Tool Needed:**
```python
def convert_psycopg2_to_asyncpg(query: str) -> str:
    """Convert %s placeholders to $1, $2, $3."""
    count = 0
    result = []
    for char in query:
        if char == '%' and result and result[-1] != '%':
            count += 1
            result.append(f'${count}')
            continue
        if char == 's' and result and result[-1] == '%':
            continue
        result.append(char)
    return ''.join(result)
```

**Example:**
```sql
-- BEFORE (psycopg2)
"SELECT * FROM contexts WHERE label = %s AND version = %s"

-- AFTER (asyncpg)
"SELECT * FROM contexts WHERE label = $1 AND version = $2"
```

---

## Testing Strategy

### Unit Tests
```python
# tests/test_postgres_adapter_async.py
import pytest
import asyncio

@pytest.mark.asyncio
async def test_execute_query():
    adapter = PostgreSQLAdapterAsync()
    result = await adapter.execute_query("SELECT 1 as test")
    assert result[0]['test'] == 1
    await adapter.close()

@pytest.mark.asyncio
async def test_execute_update():
    adapter = PostgreSQLAdapterAsync()
    await adapter.execute_update(
        "INSERT INTO test (name) VALUES ($1)",
        ["test_value"]
    )
    await adapter.close()
```

### Integration Tests
1. **Session Middleware:**
   - Initialize request → creates session
   - Resume request → loads existing session
   - Measure response time (should be <1s)

2. **MCP Tools:**
   - lock_context → verify async DB call
   - recall_context → verify async query
   - select_project_for_session → verify works now

3. **Keep-Alive:**
   - Verify pings run every 15s
   - Verify no blocking

### Performance Tests
```bash
# Before migration (sync)
ab -n 100 -c 10 https://server/tools
# Expected: Some blocking, variable latency

# After migration (async)
ab -n 100 -c 10 https://server/tools
# Expected: Consistent <1s latency
```

---

## Deployment Strategy

### Step 1: Parallel Development
- Create `postgres_adapter_async.py` alongside existing `postgres_adapter.py`
- Keep both adapters during migration
- Switch via environment variable: `USE_ASYNC_DB=true`

### Step 2: Feature Flag Approach
```python
# config.py
USE_ASYNC_DB = os.getenv('USE_ASYNC_DB', 'false').lower() == 'true'

if USE_ASYNC_DB:
    from postgres_adapter_async import PostgreSQLAdapterAsync as Adapter
else:
    from postgres_adapter import PostgreSQLAdapter as Adapter
```

### Step 3: Gradual Rollout
1. **Local testing:** Use async adapter locally
2. **Staging deployment:** Deploy with `USE_ASYNC_DB=true`
3. **Monitor performance:** Check response times
4. **Production:** Switch production after validation
5. **Remove old code:** Delete `postgres_adapter.py` after 1 week

---

## Risk Assessment

### High Risk ⚠️
- **SQL syntax differences:** `%s` → `$1` requires careful conversion
- **Query result format:** asyncpg returns Records, not dicts (need conversion)
- **Connection lifecycle:** Pool management different from psycopg2
- **Migration scale:** ~30 tools × ~3-5 queries each = ~100 query conversions

### Medium Risk ⚡
- **Session middleware timing:** Must not introduce new delays
- **Keep-alive compatibility:** Ensure async version works correctly
- **Error handling:** asyncpg exceptions differ from psycopg2

### Low Risk ✅
- **FastMCP compatibility:** Already async, should work seamlessly
- **Database schema:** No changes needed
- **Tool interfaces:** Only internal implementation changes

---

## Rollback Plan

### If Migration Fails:
1. **Immediate:** Set `USE_ASYNC_DB=false` (instant rollback)
2. **Redeploy:** Push previous commit
3. **Investigate:** Review error logs, fix issues
4. **Retry:** Test locally before next attempt

### Rollback Triggers:
- Response time > 5 seconds
- Tool errors > 5% of requests
- Database connection errors
- Session persistence failures

---

## Success Criteria

### Functional Requirements ✅
- [ ] All 31 tools work correctly
- [ ] Session middleware works without blocking
- [ ] `select_project_for_session()` works
- [ ] Project switching persists across requests
- [ ] No database errors in logs

### Performance Requirements ⚡
- [ ] Response times < 1 second (95th percentile)
- [ ] No event loop blocking detected
- [ ] Database keep-alive maintains 15s interval
- [ ] Concurrent requests don't block each other

### Testing Requirements 🧪
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Systematic tool test: 10/10 tools pass
- [ ] Load test: 100 requests under 1s average

---

## Implementation Order

### Priority 1: Core Infrastructure (Day 1)
1. Create `postgres_adapter_async.py`
2. Write unit tests for async adapter
3. Convert `mcp_session_store.py` to async
4. Test session store in isolation

### Priority 2: Middleware & Server (Day 2)
5. Convert `mcp_session_middleware.py` to async
6. Update `server_hosted.py` initialization
7. Convert `database_keepalive.py` to async
8. Test middleware + server integration

### Priority 3: Tools Migration (Day 3-4)
9. Convert high-priority tools (lock, recall, search)
10. Convert session tools (select_project, switch_project)
11. Convert remaining tools
12. Run systematic tool test

### Priority 4: Testing & Deployment (Day 5)
13. Full integration testing
14. Performance testing
15. Deploy to staging
16. Deploy to production

---

## Open Questions

1. **Connection Pool Size:**
   - How many connections should pool maintain?
   - Current: min=2, max=10
   - Need load testing to optimize

2. **Query Timeout:**
   - Should we set statement_timeout in asyncpg?
   - Current psycopg2: 30 seconds
   - Recommendation: Keep 30s for compatibility

3. **Error Handling:**
   - How should we handle asyncpg.exceptions vs psycopg2.Error?
   - Need consistent error mapping

4. **Migration Tool:**
   - Should we auto-convert queries or manual review?
   - Recommendation: Manual review for safety

---

## Next Steps

**Awaiting Approval:**
- [ ] Review this plan
- [ ] Approve architecture approach
- [ ] Approve migration strategy
- [ ] Approve testing approach

**After Approval:**
1. Create feature branch: `feature/async-migration`
2. Implement Priority 1 tasks
3. Test thoroughly
4. Request code review
5. Deploy to staging
6. Deploy to production

---

**Estimated Effort:** 3-5 days full-time
**Estimated Risk:** Medium-High (significant refactor)
**Recommendation:** Proceed with caution, test extensively
