# Async Migration - Comprehensive Task List & Implementation Guide

**Date:** 2025-11-22
**Objective:** Convert entire codebase from blocking (psycopg2) to non-blocking (asyncpg)
**Estimated Time:** 3-5 days
**Status:** READY TO EXECUTE

---

## Pre-Migration Checklist

- [ ] Read `ASYNC_MIGRATION_PLAN.md` completely
- [ ] Understand current architecture and blocking issues
- [ ] Verify PostgreSQL database is accessible
- [ ] Backup current database (if needed)
- [ ] Create feature branch
- [ ] Install asyncpg: `pip install asyncpg`

---

## PHASE 1: CORE INFRASTRUCTURE (Day 1)

### Task 1.1: Create Feature Branch

**Objective:** Set up isolated branch for async migration

**Commands:**
```bash
git checkout main
git pull origin main
git checkout -b feature/async-migration
git push -u origin feature/async-migration
```

**Verification:**
```bash
git branch --show-current
# Should output: feature/async-migration
```

---

### Task 1.2: Install asyncpg

**Objective:** Add asyncpg dependency

**Commands:**
```bash
# Install asyncpg
pip install asyncpg

# Update requirements.txt
echo "asyncpg>=0.29.0" >> requirements.txt
```

**Verification:**
```bash
python3 -c "import asyncpg; print(asyncpg.__version__)"
# Should output version number (e.g., 0.29.0)
```

---

### Task 1.3: Create postgres_adapter_async.py

**Objective:** Create new async database adapter using asyncpg

**File:** `/Users/banton/Sites/claude-dementia/postgres_adapter_async.py`

**Implementation:**
```python
"""
Async PostgreSQL Adapter for Claude Dementia
Uses asyncpg for non-blocking database operations.
"""

import os
import asyncpg
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
import subprocess
import hashlib

load_dotenv()


class PostgreSQLAdapterAsync:
    """
    Fully async PostgreSQL adapter using asyncpg.

    Replaces the blocking psycopg2-based PostgreSQLAdapter with non-blocking
    asyncpg implementation to eliminate event loop blocking in async middleware.
    """

    def __init__(self, database_url: Optional[str] = None, schema: Optional[str] = None):
        """
        Initialize async adapter.

        Args:
            database_url: PostgreSQL connection string (default: from DATABASE_URL env)
            schema: Schema name (default: auto-detect from project)
        """
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        self.schema = schema or self._get_schema_name()
        self._pool: Optional[asyncpg.Pool] = None

    def _get_schema_name(self) -> str:
        """Auto-detect schema from project directory (same logic as sync adapter)."""
        schema = os.getenv('DEMENTIA_SCHEMA')
        if schema:
            return schema

        project_name = self._detect_project_name()
        return self._sanitize_identifier(project_name)

    def _detect_project_name(self) -> str:
        """Detect project name from git repo or directory."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                capture_output=True,
                text=True,
                check=True
            )
            repo_path = result.stdout.strip()
            return os.path.basename(repo_path)
        except:
            return os.path.basename(os.getcwd())

    def _sanitize_identifier(self, name: str) -> str:
        """Sanitize identifier for PostgreSQL schema name."""
        import re
        safe_name = re.sub(r'[^a-z0-9_]', '_', name.lower())
        safe_name = re.sub(r'_+', '_', safe_name)
        safe_name = safe_name.strip('_')[:63]
        return safe_name or 'default'

    async def get_pool(self) -> asyncpg.Pool:
        """
        Get or create connection pool.

        Returns:
            asyncpg.Pool: Connection pool
        """
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
                server_settings={
                    'application_name': 'claude_dementia_async'
                }
            )
        return self._pool

    async def execute_query(
        self,
        query: str,
        params: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return rows as list of dicts.

        Args:
            query: SQL query with $1, $2, $3 placeholders (asyncpg style)
            params: Query parameters

        Returns:
            List of dictionaries (one per row)

        Example:
            rows = await adapter.execute_query(
                "SELECT * FROM contexts WHERE label = $1",
                ["api_spec"]
            )
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Set search_path to project schema
            await conn.execute(f"SET search_path TO {self.schema}")

            # Execute query
            rows = await conn.fetch(query, *(params or []))

            # Convert asyncpg.Record to dict
            return [dict(row) for row in rows]

    async def execute_update(
        self,
        query: str,
        params: Optional[List[Any]] = None
    ) -> str:
        """
        Execute INSERT/UPDATE/DELETE query.

        Args:
            query: SQL query with $1, $2, $3 placeholders
            params: Query parameters

        Returns:
            Result status string (e.g., "INSERT 0 1")

        Example:
            result = await adapter.execute_update(
                "INSERT INTO contexts (label, content) VALUES ($1, $2)",
                ["api_spec", "API documentation..."]
            )
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"SET search_path TO {self.schema}")
            result = await conn.execute(query, *(params or []))
            return result

    async def ensure_schema_exists(self):
        """Create schema and tables if they don't exist."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Create schema
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            await conn.execute(f"SET search_path TO {self.schema}")

            # Create tables (copied from sync adapter)
            await self._create_tables(conn)

    async def _create_tables(self, conn):
        """Create all required tables."""
        # Sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
                status TEXT DEFAULT 'active',
                client_info JSONB DEFAULT '{}'::jsonb
            )
        """)

        # Context locks table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS context_locks (
                id SERIAL PRIMARY KEY,
                label TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0',
                content TEXT NOT NULL,
                preview TEXT,
                key_concepts TEXT[],
                tags TEXT[],
                priority TEXT DEFAULT 'reference',
                locked_at TIMESTAMPTZ DEFAULT NOW(),
                session_id TEXT,
                embedding vector(1024),
                UNIQUE(label, version)
            )
        """)

        # Memory entries table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # File tags table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS file_tags (
                id SERIAL PRIMARY KEY,
                path TEXT NOT NULL,
                tag TEXT NOT NULL,
                value TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(path, tag)
            )
        """)

        # Context archives table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS context_archives (
                id SERIAL PRIMARY KEY,
                label TEXT NOT NULL,
                version TEXT NOT NULL,
                content TEXT NOT NULL,
                deleted_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_by TEXT
            )
        """)

    async def test_connection(self) -> bool:
        """Test database connection."""
        try:
            pool = await self.get_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def get_info(self) -> dict:
        """Get adapter info (non-async for compatibility)."""
        return {
            'database_url': self.database_url.split('@')[1] if '@' in self.database_url else 'unknown',
            'schema': self.schema,
            'pool_active': self._pool is not None,
            'adapter_type': 'async'
        }
```

**Verification:**
```python
# Test the new adapter
python3 -c "
import asyncio
from postgres_adapter_async import PostgreSQLAdapterAsync

async def test():
    adapter = PostgreSQLAdapterAsync()
    connected = await adapter.test_connection()
    print(f'Connection test: {connected}')
    await adapter.close()

asyncio.run(test())
"
```

**Commit:**
```bash
git add postgres_adapter_async.py requirements.txt
git commit -m "feat(database): create async PostgreSQL adapter using asyncpg

- New PostgreSQLAdapterAsync class using asyncpg
- Fully async methods (execute_query, execute_update)
- Connection pooling with asyncpg.create_pool
- Schema isolation preserved from sync adapter
- Non-blocking database operations
- Fixes event loop blocking issue from psycopg2"
```

---

### Task 1.4: Write Unit Tests for Async Adapter

**Objective:** Ensure async adapter works correctly

**File:** `/Users/banton/Sites/claude-dementia/tests/test_postgres_adapter_async.py`

**Implementation:**
```python
"""
Unit tests for PostgreSQLAdapterAsync.
"""

import pytest
import asyncio
from postgres_adapter_async import PostgreSQLAdapterAsync


@pytest.mark.asyncio
async def test_adapter_initialization():
    """Test adapter initializes correctly."""
    adapter = PostgreSQLAdapterAsync()
    assert adapter.database_url is not None
    assert adapter.schema is not None
    await adapter.close()


@pytest.mark.asyncio
async def test_connection():
    """Test database connection."""
    adapter = PostgreSQLAdapterAsync()
    connected = await adapter.test_connection()
    assert connected is True
    await adapter.close()


@pytest.mark.asyncio
async def test_execute_query():
    """Test SELECT query execution."""
    adapter = PostgreSQLAdapterAsync()
    result = await adapter.execute_query("SELECT 1 as test")
    assert len(result) == 1
    assert result[0]['test'] == 1
    await adapter.close()


@pytest.mark.asyncio
async def test_schema_creation():
    """Test schema and table creation."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()

    # Verify tables exist
    result = await adapter.execute_query("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1
    """, [adapter.schema])

    table_names = [row['table_name'] for row in result]
    assert 'sessions' in table_names
    assert 'context_locks' in table_names
    assert 'memory_entries' in table_names

    await adapter.close()


@pytest.mark.asyncio
async def test_execute_update():
    """Test INSERT query execution."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()

    # Insert test data
    result = await adapter.execute_update("""
        INSERT INTO sessions (id, project_name)
        VALUES ($1, $2)
        ON CONFLICT (id) DO NOTHING
    """, ["test_session_123", "test_project"])

    assert "INSERT" in result or "DO NOTHING" in result

    # Verify inserted
    rows = await adapter.execute_query("""
        SELECT * FROM sessions WHERE id = $1
    """, ["test_session_123"])

    assert len(rows) > 0
    assert rows[0]['project_name'] == 'test_project'

    # Cleanup
    await adapter.execute_update("""
        DELETE FROM sessions WHERE id = $1
    """, ["test_session_123"])

    await adapter.close()
```

**Run Tests:**
```bash
python3 -m pytest tests/test_postgres_adapter_async.py -v
```

**Commit:**
```bash
git add tests/test_postgres_adapter_async.py
git commit -m "test(database): add unit tests for async adapter

- Test initialization and connection
- Test query execution (SELECT)
- Test update execution (INSERT/DELETE)
- Test schema creation
- All tests passing"
```

---

### Task 1.5: Convert mcp_session_store.py to Async

**Objective:** Convert all session store methods to async

**File:** `/Users/banton/Sites/claude-dementia/mcp_session_store.py`

**Changes Required:**

**1. Update imports:**
```python
# ADD at top
from postgres_adapter_async import PostgreSQLAdapterAsync
```

**2. Convert create_session (lines 39-96):**
```python
# BEFORE
def create_session(
    self,
    session_id: str,
    project_name: str = 'default',
    client_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    conn = self.db_adapter.get_connection()
    # ... rest of sync code

# AFTER
async def create_session(
    self,
    session_id: str,
    project_name: str = 'default',
    client_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    # Execute insert query
    await self.db_adapter.execute_update("""
        INSERT INTO sessions (id, project_name, client_info, created_at, last_accessed_at, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (id) DO UPDATE SET
            last_accessed_at = $5,
            client_info = $3
    """, [
        session_id,
        project_name,
        json.dumps(client_info or {}),
        datetime.now(timezone.utc),
        datetime.now(timezone.utc),
        'active'
    ])

    return {
        'session_id': session_id,
        'project_name': project_name,
        'status': 'active',
        'created_at': datetime.now(timezone.utc).isoformat()
    }
```

**3. Convert get_session (lines 160-185):**
```python
# BEFORE
def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
    conn = self.db_adapter.get_connection()
    # ... sync code

# AFTER
async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
    rows = await self.db_adapter.execute_query("""
        SELECT id, project_name, created_at, last_accessed_at, status, client_info
        FROM sessions
        WHERE id = $1
    """, [session_id])

    if not rows:
        return None

    row = rows[0]
    return {
        'session_id': row['id'],
        'project_name': row['project_name'],
        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        'last_accessed_at': row['last_accessed_at'].isoformat() if row['last_accessed_at'] else None,
        'status': row['status'],
        'client_info': row['client_info'] if isinstance(row['client_info'], dict) else {}
    }
```

**4. Convert update_activity (lines 233-252):**
```python
# BEFORE
def update_activity(self, session_id: str, accessed_at: Optional[datetime] = None):
    # ... sync code

# AFTER
async def update_activity(self, session_id: str, accessed_at: Optional[datetime] = None):
    timestamp = accessed_at or datetime.now(timezone.utc)
    await self.db_adapter.execute_update("""
        UPDATE sessions
        SET last_accessed_at = $1
        WHERE id = $2
    """, [timestamp, session_id])
```

**5. Convert get_active_sessions (lines 254-271):**
```python
# BEFORE
def get_active_sessions(self) -> List[Dict[str, Any]]:
    # ... sync code

# AFTER
async def get_active_sessions(self) -> List[Dict[str, Any]]:
    rows = await self.db_adapter.execute_query("""
        SELECT id, project_name, created_at, last_accessed_at, status
        FROM sessions
        WHERE status = 'active'
        ORDER BY last_accessed_at DESC
    """)

    return [{
        'session_id': row['id'],
        'project_name': row['project_name'],
        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        'last_accessed_at': row['last_accessed_at'].isoformat() if row['last_accessed_at'] else None,
        'status': row['status']
    } for row in rows]
```

**6. Convert cleanup_expired_sessions (lines 273-303):**
```python
# BEFORE
def cleanup_expired_sessions(self, expiry_hours: int = 24) -> int:
    # ... sync code

# AFTER
async def cleanup_expired_sessions(self, expiry_hours: int = 24) -> int:
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=expiry_hours)

    # Get count first
    count_rows = await self.db_adapter.execute_query("""
        SELECT COUNT(*) as count
        FROM sessions
        WHERE last_accessed_at < $1 AND status = 'active'
    """, [cutoff_time])

    count = count_rows[0]['count'] if count_rows else 0

    # Mark as expired
    await self.db_adapter.execute_update("""
        UPDATE sessions
        SET status = 'expired'
        WHERE last_accessed_at < $1 AND status = 'active'
    """, [cutoff_time])

    return count
```

**Test Conversion:**
```python
# Test async session store
python3 -c "
import asyncio
from mcp_session_store import PostgreSQLSessionStore
from postgres_adapter_async import PostgreSQLAdapterAsync

async def test():
    adapter = PostgreSQLAdapterAsync()
    store = PostgreSQLSessionStore(db_pool=adapter)

    # Test create
    result = await store.create_session('test_123', 'test_project')
    print(f'Created: {result}')

    # Test get
    session = await store.get_session('test_123')
    print(f'Retrieved: {session}')

    # Test update
    await store.update_activity('test_123')
    print('Updated activity')

    # Cleanup
    await adapter.execute_update('DELETE FROM sessions WHERE id = \$1', ['test_123'])
    await adapter.close()

asyncio.run(test())
"
```

**Commit:**
```bash
git add mcp_session_store.py
git commit -m "refactor(sessions): convert session store to async methods

- create_session() → async create_session()
- get_session() → async get_session()
- update_activity() → async update_activity()
- get_active_sessions() → async get_active_sessions()
- cleanup_expired_sessions() → async cleanup_expired_sessions()
- All methods now use asyncpg via PostgreSQLAdapterAsync
- No more blocking database calls"
```

---

## PHASE 2: MIDDLEWARE & SERVER (Day 2)

### Task 2.1: Convert mcp_session_middleware.py to Async

**Objective:** Add await to all async session store calls

**File:** `/Users/banton/Sites/claude-dementia/mcp_session_middleware.py`

**Changes Required:**

**1. Line 130 - get_session:**
```python
# BEFORE
existing_session = self.session_store.get_session(stable_session_id)

# AFTER
existing_session = await self.session_store.get_session(stable_session_id)
```

**2. Line 137 - update_activity:**
```python
# BEFORE
self.session_store.update_activity(stable_session_id)

# AFTER
await self.session_store.update_activity(stable_session_id)
```

**3. Line 152 - create_session:**
```python
# BEFORE
result = self.session_store.create_session(
    session_id=stable_session_id,
    project_name='__PENDING__',
    client_info={'user_agent': user_agent}
)

# AFTER
result = await self.session_store.create_session(
    session_id=stable_session_id,
    project_name='__PENDING__',
    client_info={'user_agent': user_agent}
)
```

**Commit:**
```bash
git add mcp_session_middleware.py
git commit -m "fix(middleware): add await to async session store calls

- await get_session() - no longer blocks event loop
- await update_activity() - non-blocking update
- await create_session() - non-blocking creation
- Fixes 7-12s delay issue from blocking sync calls"
```

---

### Task 2.2: Update server_hosted.py for Async

**Objective:** Initialize async adapter in lifespan

**File:** `/Users/banton/Sites/claude-dementia/server_hosted.py`

**Changes Required:**

**1. Update imports (around line 94):**
```python
# BEFORE
from postgres_adapter import PostgreSQLAdapter

# AFTER
from postgres_adapter_async import PostgreSQLAdapterAsync
```

**2. Remove global adapter initialization (around line 95):**
```python
# BEFORE
adapter = PostgreSQLAdapter() if os.getenv('DATABASE_URL') else None

# AFTER
adapter = None  # Will be initialized in lifespan
```

**3. Update lifespan_with_keepalive (around line 506):**
```python
# BEFORE
@asynccontextmanager
async def lifespan_with_keepalive(app_instance):
    """Wrap FastMCP's lifespan to add database keep-alive task."""
    # Start database keep-alive task
    keepalive_task = None
    if adapter is not None:
        keepalive_task = asyncio.create_task(...)

# AFTER
@asynccontextmanager
async def lifespan_with_keepalive(app_instance):
    """Wrap FastMCP's lifespan to add async database initialization and keep-alive."""
    global adapter

    # Initialize async database pool
    if os.getenv('DATABASE_URL'):
        adapter = PostgreSQLAdapterAsync()
        await adapter.get_pool()  # Create connection pool
        logger.info("async_database_pool_initialized", schema=adapter.schema)

    # Start database keep-alive task
    keepalive_task = None
    if adapter is not None:
        keepalive_task = asyncio.create_task(
            start_keepalive_scheduler(adapter, interval_seconds=15)
        )
        logger.info("database_keepalive_task_started")

    try:
        # Run FastMCP's original lifespan
        async with original_lifespan(app_instance) as state:
            yield state
    finally:
        # Cleanup
        if keepalive_task:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass

        # Close database pool
        if adapter:
            await adapter.close()
            logger.info("async_database_pool_closed")
```

**4. Re-enable session middleware (around line 573):**
```python
# BEFORE (disabled)
# DISABLED: Session middleware causes blocking database calls
# if adapter is not None:
#     app.add_middleware(MCPSessionPersistenceMiddleware,
#                        db_pool=adapter)

# AFTER (re-enabled with async)
if adapter is not None:
    app.add_middleware(MCPSessionPersistenceMiddleware,
                       db_pool=adapter)  # Now async - no blocking!
```

**Commit:**
```bash
git add server_hosted.py
git commit -m "feat(server): initialize async database pool in lifespan

- Create PostgreSQLAdapterAsync on startup
- Initialize connection pool with await adapter.get_pool()
- Close pool on shutdown
- Re-enable session middleware (now async, no blocking)
- Async initialization ensures proper cleanup"
```

---

### Task 2.3: Convert database_keepalive.py to Async

**Objective:** Make keep-alive pings async

**File:** `/Users/banton/Sites/claude-dementia/database_keepalive.py`

**Changes Required:**

**1. Convert ping_database_once (lines 29-72):**
```python
# BEFORE
def ping_database_once(db_adapter) -> tuple[bool, float]:
    """Execute a lightweight query to keep database connection alive."""
    import time
    try:
        start_time = time.time()
        conn = db_adapter.get_connection()
        # ... sync code

# AFTER
async def ping_database_once(db_adapter) -> tuple[bool, float]:
    """Execute a lightweight query to keep database connection alive."""
    import time
    try:
        start_time = time.time()

        # Execute lightweight query
        await db_adapter.execute_query("SELECT 1")

        elapsed_ms = (time.time() - start_time) * 1000

        if elapsed_ms > 1000:
            logger.warning("slow_database_keepalive",
                         elapsed_ms=round(elapsed_ms, 2),
                         threshold_ms=1000)
        else:
            logger.debug("database_keepalive_success",
                       elapsed_ms=round(elapsed_ms, 2))

        return (True, elapsed_ms)

    except Exception as e:
        logger.error("database_keepalive_failed",
                    error=str(e),
                    error_type=type(e).__name__)
        return (False, 0.0)
```

**2. Update start_keepalive_scheduler (line 107):**
```python
# BEFORE
success, elapsed_ms = ping_database_once(db_adapter)

# AFTER
success, elapsed_ms = await ping_database_once(db_adapter)
```

**Commit:**
```bash
git add database_keepalive.py
git commit -m "refactor(keepalive): convert to async ping function

- ping_database_once() → async ping_database_once()
- Use async execute_query instead of sync get_connection
- Non-blocking database pings
- Maintains 15-second interval"
```

---

## PHASE 3: TOOLS MIGRATION (Day 3-4)

### Task 3.1: Create SQL Conversion Utility

**Objective:** Helper to convert psycopg2 SQL to asyncpg SQL

**File:** `/Users/banton/Sites/claude-dementia/sql_converter.py`

**Implementation:**
```python
"""
SQL Query Converter: psycopg2 (%s) → asyncpg ($1, $2, $3)
"""

def convert_psycopg2_to_asyncpg(query: str) -> str:
    """
    Convert psycopg2-style placeholders (%s) to asyncpg-style ($1, $2, $3).

    Example:
        >>> convert_psycopg2_to_asyncpg("SELECT * FROM table WHERE id = %s AND name = %s")
        'SELECT * FROM table WHERE id = $1 AND name = $2'
    """
    count = 0
    result = []
    i = 0

    while i < len(query):
        if i < len(query) - 1 and query[i:i+2] == '%s':
            count += 1
            result.append(f'${count}')
            i += 2
        else:
            result.append(query[i])
            i += 1

    return ''.join(result)


if __name__ == '__main__':
    # Test cases
    tests = [
        ("SELECT * FROM table WHERE id = %s", "SELECT * FROM table WHERE id = $1"),
        ("INSERT INTO table (a, b) VALUES (%s, %s)", "INSERT INTO table (a, b) VALUES ($1, $2)"),
        ("UPDATE table SET name = %s WHERE id = %s", "UPDATE table SET name = $1 WHERE id = $2"),
    ]

    for input_sql, expected in tests:
        result = convert_psycopg2_to_asyncpg(input_sql)
        assert result == expected, f"Failed: {input_sql}"
        print(f"✅ {input_sql[:50]}...")

    print("\nAll tests passed!")
```

**Run:**
```bash
python3 sql_converter.py
```

---

### Task 3.2: Convert lock_context Tool

**Objective:** Migrate first high-priority tool to async

**File:** `/Users/banton/Sites/claude-dementia/claude_mcp_hybrid_sessions.py`

**Find lock_context (search for "async def lock_context"):**

**Pattern to Apply:**

**Before:**
```python
async def lock_context(...):
    # Get connection
    conn = adapter.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO context_locks (...) VALUES (%s, %s, %s)", [...])
            conn.commit()
    finally:
        conn.close()
```

**After:**
```python
async def lock_context(...):
    # Convert SQL
    query = """
        INSERT INTO context_locks (label, version, content, preview, key_concepts, tags, priority, locked_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (label, version) DO UPDATE SET
            content = $3,
            preview = $4,
            locked_at = $8
    """

    # Execute async
    await adapter.execute_update(query, [
        topic,
        version,
        content,
        preview,
        key_concepts,
        tags,
        priority,
        datetime.now(timezone.utc)
    ])
```

**Steps:**
1. Find all `cur.execute()` calls in the function
2. Convert SQL using `sql_converter.py`
3. Replace with `await adapter.execute_query()` or `await adapter.execute_update()`
4. Remove `conn = adapter.get_connection()` and `conn.close()`
5. Remove `with conn.cursor() as cur:` blocks

**Test:**
```python
python3 -c "
import asyncio
from claude_mcp_hybrid_sessions import lock_context

async def test():
    result = await lock_context(
        content='Test content',
        topic='test_async_lock',
        tags='test',
        priority='reference'
    )
    print(result)

asyncio.run(test())
"
```

**Commit:**
```bash
git add claude_mcp_hybrid_sessions.py
git commit -m "refactor(tools): convert lock_context to async database calls

- Replace psycopg2 with asyncpg
- Convert %s to $1, $2, $3 placeholders
- Use await adapter.execute_update()
- No more blocking database calls"
```

---

### Task 3.3: Convert recall_context Tool

**Follow same pattern as lock_context:**

1. Find function `async def recall_context`
2. Find all `cur.execute()` calls
3. Convert SQL placeholders
4. Replace with `await adapter.execute_query()`
5. Test

**Commit:**
```bash
git commit -m "refactor(tools): convert recall_context to async"
```

---

### Task 3.4: Convert search_contexts Tool

**Same pattern - convert all database calls to async**

**Commit:**
```bash
git commit -m "refactor(tools): convert search_contexts to async"
```

---

### Task 3.5: Convert Remaining Tools (Batch Approach)

**Tools to Convert (30+ tools):**
- unlock_context
- batch_lock_contexts
- batch_recall_contexts
- semantic_search_contexts
- generate_embeddings
- ai_summarize_context
- check_contexts
- explore_context_tree
- context_dashboard
- query_database
- execute_sql
- manage_workspace_table
- get_last_handover
- create_project
- list_projects
- switch_project
- get_project_info
- delete_project
- export_project
- import_project
- health_check_and_repair
- inspect_schema
- apply_migrations
- And more...

**For Each Tool:**
1. Search for function definition
2. Find all database operations
3. Convert SQL placeholders (%s → $1, $2)
4. Replace sync calls with async
5. Test tool individually
6. Commit

**Batch Commit After Every 5 Tools:**
```bash
git commit -m "refactor(tools): convert batch of tools to async (unlock, batch_lock, batch_recall, semantic_search, generate_embeddings)"
```

---

## PHASE 4: TESTING & DEPLOYMENT (Day 5)

### Task 4.1: Run Unit Tests

**Objective:** Ensure all tests pass with async adapter

**Commands:**
```bash
# Run all unit tests
python3 -m pytest tests/unit/ -v

# Run integration tests
python3 -m pytest tests/integration/ -v

# Run specific async tests
python3 -m pytest tests/test_postgres_adapter_async.py -v
```

**Expected:** All tests pass

---

### Task 4.2: Run Systematic Tool Test

**Objective:** Verify all tools work end-to-end

**Test Sequence:**
```
1. list_projects() - ✅ Should pass
2. switch_project('linkedin') - ✅ Should pass (FIXED!)
3. get_last_handover() - ✅ Should pass
4. explore_context_tree() - ✅ Should pass
5. context_dashboard() - ✅ Should pass
6. lock_context() - ✅ Should pass
7. recall_context() - ✅ Should pass
8. search_contexts() - ✅ Should pass
9. query_database() - ✅ Should pass
10. health_check_and_repair() - ✅ Should pass
```

**Expected:** 10/10 PASS

---

### Task 4.3: Performance Testing

**Objective:** Verify response times <1s

**Load Test:**
```bash
# Install apache bench if needed
# brew install httpd (macOS)
# apt-get install apache2-utils (Linux)

# Test /tools endpoint (100 requests, 10 concurrent)
ab -n 100 -c 10 -H "Authorization: Bearer sk-ant-api03-dementia" \
   https://dementia-mcp-7f4vf.ondigitalocean.app/tools

# Check results
# Time per request: <1000ms (target)
# Failed requests: 0
```

**Manual Test:**
```bash
# Test individual request timing
time curl -s -H "Authorization: Bearer sk-ant-api03-dementia" \
     https://dementia-mcp-7f4vf.ondigitalocean.app/tools | head -20
```

**Expected:**
- 95th percentile: <1000ms
- Average: <500ms
- No timeouts
- No errors

---

### Task 4.4: Deploy to Production

**Objective:** Deploy async architecture to DigitalOcean

**Steps:**

**1. Final Testing:**
```bash
# Run all tests one more time
python3 -m pytest tests/ -v

# Check git status
git status
git log --oneline -10
```

**2. Merge to Deployment Branch:**
```bash
# Merge feature branch to deployment branch
git checkout claude/refactor-functions-01WQfcDL5fD8twQRvp6evAJj
git merge feature/async-migration
```

**3. Push to Production:**
```bash
git push origin claude/refactor-functions-01WQfcDL5fD8twQRvp6evAJj
```

**4. Trigger Deployment:**
```bash
APP_ID="20c874aa-0ed2-44e3-a433-699f17d88a44"
doctl apps create-deployment $APP_ID --force-rebuild
```

**5. Monitor Deployment:**
```bash
# Wait for deployment
sleep 120

# Check deployment status
doctl apps list-deployments $APP_ID --format ID,Phase,Progress | head -3

# Check logs
doctl apps logs $APP_ID --type run --tail 50
```

**6. Verify Production:**
```bash
# Test /tools endpoint
curl -s -H "Authorization: Bearer sk-ant-api03-dementia" \
     https://dementia-mcp-7f4vf.ondigitalocean.app/tools | jq '.tools | length'

# Should return: 31
```

---

### Task 4.5: Post-Deployment Validation

**Objective:** Confirm everything works in production

**Validation Checklist:**
- [ ] Custom Connector shows 31 tools
- [ ] Tools load in <1 second
- [ ] No auto-disconnect/reconnect loop
- [ ] `select_project_for_session('linkedin')` works
- [ ] Project switching persists
- [ ] Database keep-alive running (check logs)
- [ ] No errors in production logs
- [ ] Response times consistently <1s

**Monitor for 1 Hour:**
```bash
# Watch logs for errors
doctl apps logs $APP_ID --type run --follow
```

**If All Green:**
```bash
# Create release tag
git tag -a v5.0.0-async -m "Async architecture migration complete

- Fully async database layer with asyncpg
- Non-blocking session middleware
- All tools converted to async
- Response times <1s
- Session persistence working
- Project selection fixed"

git push origin v5.0.0-async
```

---

## Post-Migration Cleanup

### Task 5.1: Remove Old Sync Adapter

**After 1 Week of Validation:**

```bash
# Remove old sync adapter
git rm postgres_adapter.py

# Update imports if any stragglers
grep -r "from postgres_adapter import" .
# Should find none (all should use postgres_adapter_async)

# Commit cleanup
git commit -m "chore: remove deprecated sync PostgreSQL adapter

All code migrated to async adapter (postgres_adapter_async).
Old sync adapter (postgres_adapter.py) no longer needed."
```

---

## Rollback Procedures

### Immediate Rollback (If Critical Issue)

**Step 1: Stop Deployment**
```bash
APP_ID="20c874aa-0ed2-44e3-a433-699f17d88a44"
# Note current deployment ID
CURRENT_DEPLOYMENT=$(doctl apps list-deployments $APP_ID --format ID | head -2 | tail -1)

# Get previous deployment
PREVIOUS_DEPLOYMENT=$(doctl apps list-deployments $APP_ID --format ID | head -3 | tail -1)

# Redeploy previous version
doctl apps create-deployment $APP_ID --force-rebuild
```

**Step 2: Revert Git**
```bash
git revert HEAD
git push origin claude/refactor-functions-01WQfcDL5fD8twQRvp6evAJj
```

---

## Success Criteria Summary

**Migration is successful when:**
- ✅ All 31 tools functional
- ✅ Systematic tool test: 10/10 pass
- ✅ Response times: 95th percentile <1s
- ✅ Session persistence working
- ✅ Project selection working
- ✅ No event loop blocking
- ✅ No database errors
- ✅ Custom Connector stable
- ✅ Production stable for 1 week

---

## Estimated Timeline

- **Phase 1 (Infrastructure):** 4-6 hours
- **Phase 2 (Middleware):** 2-3 hours
- **Phase 3 (Tools):** 12-16 hours (30+ tools)
- **Phase 4 (Testing):** 4-6 hours
- **Total:** 22-31 hours (3-5 days)

---

## Notes & Tips

**Debugging Async Issues:**
```python
# Add logging to track async calls
logger.info("before_db_call", query=query[:50])
result = await adapter.execute_query(query)
logger.info("after_db_call", rows=len(result))
```

**Common Mistakes:**
- ❌ Forgetting `await` before async calls
- ❌ Using `%s` instead of `$1, $2` in SQL
- ❌ Not converting return types (asyncpg.Record → dict)
- ❌ Forgetting to close pool in lifespan

**Best Practices:**
- ✅ Test each tool individually after conversion
- ✅ Commit after every 3-5 tool conversions
- ✅ Run tests frequently
- ✅ Monitor logs during deployment
- ✅ Keep rollback plan ready

---

**Ready to Execute!** 🚀

This comprehensive guide covers every step of the async migration. Follow tasks sequentially, test thoroughly, and commit frequently.

**Start with:** Task 1.1 - Create Feature Branch
