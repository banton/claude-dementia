# Neon Connection Pool Fix - Stale Connection Issue

**Date**: 2025-11-08
**Issue**: SSL errors on first tool call after idle period
**Root Cause**: Stale connections in pool after Neon autosuspends (5 min idle)

---

## Problem Analysis

### Error Pattern from Logs:
```
2025-11-05T07:15:55 Error executing tool wake_up: SSL connection has been closed unexpectedly
✅ PostgreSQL connection pool initialized (schema: linkedin)  // Retry succeeds
```

### What's Happening:

1. **t=0**: User locks context, connection pool created (1-3 connections)
2. **t=6min**: User idle, Neon autosuspends database, **server closes connections**
3. **t=7min**: User calls `wake_up`, code uses **stale connection from pool**
4. **Result**: `SSL connection has been closed unexpectedly` error
5. **Recovery**: Code detects failure, creates new pool, succeeds

### Why Current Code Fails:

**File**: `postgres_adapter.py:85-92`

```python
self.pool = psycopg2.pool.SimpleConnectionPool(
    1, 3,  # 1-3 connections
    self.database_url,
    cursor_factory=RealDictCursor,
    connect_timeout=15
    # NO connection validation!
    # NO max connection age!
)
```

**Problem**: Pool keeps connections forever, doesn't validate they're alive.

---

## Solution 1: Connection Validation (RECOMMENDED) ⭐

Add connection health check before use.

### Implementation:

**File**: `postgres_adapter.py`

Add new method after `__init__`:

```python
def _validate_connection(self, conn):
    """
    Validate that connection is alive and ready to use.

    Neon may close idle connections when autosuspending.
    This prevents "SSL connection closed unexpectedly" errors.

    Args:
        conn: psycopg2 connection from pool

    Returns:
        bool: True if connection is valid, False if stale
    """
    try:
        # Quick ping to check if connection is alive
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        # Connection is stale/closed
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['ssl', 'closed', 'terminated', 'broken']):
            print(f"⚠️  Detected stale connection: {e}", file=sys.stderr)
            return False
        raise  # Re-raise if it's a different error
```

Update `get_connection` context manager:

```python
@contextmanager
def get_connection(self):
    """
    Get database connection from pool with validation.

    Validates connection before use to handle Neon autosuspend.
    """
    conn = self.pool.getconn()

    # Validate connection is alive (handles Neon autosuspend)
    max_attempts = 2
    for attempt in range(max_attempts):
        if self._validate_connection(conn):
            break  # Connection is good
        else:
            # Stale connection detected, close and get new one
            try:
                conn.close()
            except:
                pass

            if attempt < max_attempts - 1:
                print(f"🔄 Refreshing stale connection (attempt {attempt + 2}/{max_attempts})", file=sys.stderr)
                conn = self.pool.getconn()
            else:
                raise ConnectionError("Failed to get valid connection after validation")

    try:
        # Set search_path for schema isolation
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(self.schema)
            ))
        yield conn
    finally:
        self.pool.putconn(conn)
```

**Benefits**:
- Detects stale connections before use
- Transparently gets new connection if needed
- User never sees SSL error
- Minimal performance impact (SELECT 1 is < 1ms when connection alive)

**Trade-offs**:
- Adds 1 extra query per connection use (acceptable overhead)
- Slightly more complex code

---

## Solution 2: Connection Age Limit

Don't keep connections longer than Neon's autosuspend period.

### Implementation:

**File**: `postgres_adapter.py`

Replace `SimpleConnectionPool` with custom pool wrapper:

```python
class NeonAwareConnectionPool:
    """
    Wrapper around SimpleConnectionPool that respects Neon's autosuspend.

    Connections older than max_age are automatically discarded and recreated.
    """

    def __init__(self, min_conn, max_conn, dsn, cursor_factory, connect_timeout, max_age_seconds=240):
        """
        Args:
            max_age_seconds: Max age for connections (default: 240s = 4 min, less than Neon's 5 min autosuspend)
        """
        self.pool = psycopg2.pool.SimpleConnectionPool(
            min_conn, max_conn, dsn,
            cursor_factory=cursor_factory,
            connect_timeout=connect_timeout
        )
        self.max_age = max_age_seconds
        self.conn_created_at = {}  # Track connection creation times

    def getconn(self):
        """Get connection from pool, replacing if too old."""
        conn = self.pool.getconn()
        conn_id = id(conn)

        # Check connection age
        if conn_id in self.conn_created_at:
            age = time.time() - self.conn_created_at[conn_id]
            if age > self.max_age:
                print(f"🔄 Connection aged out ({age:.0f}s), creating fresh one", file=sys.stderr)
                try:
                    conn.close()
                except:
                    pass
                self.pool.putconn(conn)
                conn = self.pool.getconn()  # Get new connection
                conn_id = id(conn)

        # Track creation time
        self.conn_created_at[conn_id] = time.time()
        return conn

    def putconn(self, conn):
        """Return connection to pool."""
        self.pool.putconn(conn)

    def closeall(self):
        """Close all connections."""
        self.pool.closeall()
        self.conn_created_at.clear()
```

Then in `__init__`:

```python
self.pool = NeonAwareConnectionPool(
    1, 3,
    self.database_url,
    cursor_factory=RealDictCursor,
    connect_timeout=15,
    max_age_seconds=240  # 4 minutes, less than Neon's 5 min autosuspend
)
```

**Benefits**:
- Proactively prevents stale connections
- Connections always fresh when Neon autosuspends
- No validation overhead on every use

**Trade-offs**:
- More complex pool management
- Still creates new connections (just proactively vs reactively)

---

## Solution 3: No Pooling (Simplest)

For stdio transport (Claude Desktop), create connection per-request.

### Implementation:

**File**: `postgres_adapter.py:85-92`

```python
# For stdio/local use: No pooling (connection per request)
# For HTTP/cloud use: Pool with validation (Solution 1)

TRANSPORT = os.getenv('MCP_TRANSPORT', 'stdio')

if TRANSPORT == 'http':
    # HTTP needs pooling for concurrent requests
    self.pool = psycopg2.pool.SimpleConnectionPool(...)
else:
    # stdio is single-threaded, no pooling needed
    # This completely avoids stale connection issue
    self.pool = None  # Signal to use direct connections
```

Update `get_connection`:

```python
@contextmanager
def get_connection(self):
    """Get database connection (pooled for HTTP, direct for stdio)."""
    if self.pool:
        # Pooled connection (HTTP)
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)
    else:
        # Direct connection (stdio)
        conn = psycopg2.connect(
            self.database_url,
            cursor_factory=RealDictCursor,
            connect_timeout=15
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(self.schema)
                ))
            yield conn
        finally:
            conn.close()
```

**Benefits**:
- Simplest solution for stdio/Claude Desktop
- No stale connection possible
- No pool management complexity

**Trade-offs**:
- Connection overhead on every request (~50-200ms for Neon)
- Not suitable for HTTP (concurrent requests need pooling)

---

## Solution 4: Better Error Handling (Complementary)

Transparently retry on SSL errors (use WITH any solution above).

### Implementation:

**File**: `claude_mcp_hybrid_sessions.py` (or wherever tools execute)

Wrap database operations:

```python
def with_connection_retry(func):
    """
    Decorator to retry database operations on transient connection failures.

    Handles Neon autosuspend SSL errors transparently.
    """
    def wrapper(*args, **kwargs):
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                is_connection_error = any(keyword in error_msg for keyword in [
                    'ssl', 'connection closed', 'connection reset', 'broken pipe'
                ])

                if is_connection_error and attempt < max_retries - 1:
                    print(f"⚠️  Connection error (attempt {attempt + 1}/{max_retries}): {e}", file=sys.stderr)
                    print(f"🔄 Retrying with fresh connection...", file=sys.stderr)

                    # Force pool recreation by getting new adapter
                    global _db_adapter
                    _db_adapter = None  # Clear cached adapter

                    time.sleep(0.5)  # Brief delay before retry
                    last_error = e
                    continue
                else:
                    raise

        # All retries exhausted
        raise last_error

    return wrapper


# Apply to all tool functions:
@with_connection_retry
async def wake_up(project: Optional[str] = None) -> str:
    """Initialize session and load available context..."""
    # ... existing implementation
```

**Benefits**:
- User never sees the error
- Works with any solution above
- Handles other transient connection issues too

**Trade-offs**:
- Hides the underlying problem (acceptable if combined with Solution 1 or 2)
- Small delay on retry (0.5s + connection time)

---

## Recommended Approach

**Combine Solutions 1 + 4** for best results:

### For stdio/Claude Desktop (current issue):
1. **Implement Solution 1** - Connection validation before use
2. **Implement Solution 4** - Retry decorator on tool functions
3. **Result**: User never sees SSL errors, connections validated automatically

### For HTTP/cloud deployment:
1. Same as above (Solution 1 + 4)
2. **Consider Solution 2** - Age limit if validation overhead becomes issue
3. **Result**: Resilient to Neon autosuspend in production

### Implementation Priority:

**Phase 1 (15 minutes)**: Solution 4 - Error retry
- Quick fix, immediate user benefit
- Hides SSL errors while we implement proper fix

**Phase 2 (30 minutes)**: Solution 1 - Connection validation
- Proper fix, prevents stale connections
- Minimal overhead, works for all transports

**Phase 3 (optional)**: Solution 2 or 3 if needed
- Only if performance becomes issue
- Or if we want different behavior for stdio vs HTTP

---

## Testing the Fix

### Test Stale Connection Scenario:

```python
# test_stale_connection.py
import time
from postgres_adapter import PostgreSQLAdapter

# Create adapter (connection pool initialized)
adapter = PostgreSQLAdapter()

# Execute query (works)
with adapter.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        print("✅ First query succeeded")

# Wait for Neon to autosuspend (5+ minutes)
print("⏳ Waiting 6 minutes for Neon autosuspend...")
time.sleep(360)

# Try to use stale connection (should transparently handle)
try:
    with adapter.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            print("✅ Second query succeeded (stale connection handled)")
except Exception as e:
    print(f"❌ Second query failed: {e}")
```

**Expected result**:
- Without fix: `SSL connection has been closed unexpectedly`
- With Solution 1: `⚠️ Detected stale connection` → `🔄 Refreshing` → `✅ Second query succeeded`

---

## Summary

**User's observation**: ✅ Correct - SSL errors on Claude Desktop startup
**User's hypothesis**: ❌ Incorrect - Not Neon cold start (< 1 second), it's stale connection pools

**Actual problem**: Connection pool keeps stale connections after Neon autosuspends (5 min idle)

**Best fix**: Connection validation (Solution 1) + Retry decorator (Solution 4)

**Expected outcome**: Zero SSL errors for users, connections automatically refreshed

**Neon config improvement**: Increase `autosuspend_delay_seconds` from 300s to max on paid tier
