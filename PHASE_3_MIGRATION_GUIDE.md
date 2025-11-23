# Phase 3 Migration Guide: Async Tool Conversion

**Objective:** Convert all MCP tools in `claude_mcp_hybrid_sessions.py` to use `PostgreSQLAdapterAsync` and `asyncpg`.

## 1. Core Infrastructure Changes

### 1.1 New Async Context Manager
We need an async equivalent of `AutoClosingPostgreSQLConnection` to handle connection pooling and lifecycle management.

```python
class AsyncAutoClosingConnection:
    """Async wrapper for asyncpg connections with auto-cleanup."""
    def __init__(self, pool, schema):
        self.pool = pool
        self.schema = schema
        self.conn = None

    async def __aenter__(self):
        self.conn = await self.pool.acquire()
        # Set schema for this session
        await self.conn.execute(f"SET search_path TO {self.schema}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            await self.pool.release(self.conn)

    async def execute(self, query: str, params: list = None):
        """Execute query and return list of dict-like records."""
        # OPTIONAL: Placeholder conversion helper could go here
        # query = convert_placeholders(query) 
        if params:
            return await self.conn.fetch(query, *params)
        return await self.conn.fetch(query)
        
    async def execute_update(self, query: str, params: list = None):
        """Execute INSERT/UPDATE/DELETE."""
        if params:
            return await self.conn.execute(query, *params)
        return await self.conn.execute(query)
```

### 1.2 Refactor `_get_db_for_project`
Needs to be async and return the async wrapper.

```python
async def _get_db_for_project(project: str = None):
    target_project = _get_project_for_context(project)
    adapter = _get_cached_async_adapter(target_project) # Need async adapter cache
    pool = await adapter.get_pool()
    return AsyncAutoClosingConnection(pool, adapter.schema)
```

## 2. Tool Conversion Pattern

### Before (Sync)
```python
@mcp.tool()
def example_tool(arg: str, project: str = None):
    # ... checks ...
    with _get_db_for_project(project) as conn:
        conn.execute("INSERT INTO table (col) VALUES (%s)", (arg,))
        conn.commit() # AutoClosingPostgreSQLConnection handles commit on exit
```

### After (Async)
```python
@mcp.tool()
async def example_tool(arg: str, project: str = None):
    # ... checks ...
    async with await _get_db_for_project(project) as conn:
        await conn.execute_update("INSERT INTO table (col) VALUES ($1)", [arg])
        # asyncpg auto-commits by default outside of transaction blocks
```

## 3. Key Challenges & Solutions

### 3.1 SQL Placeholders (`%s` -> `$1`)
- **Challenge:** `psycopg2` uses `%s`, `asyncpg` uses `$1, $2`.
- **Solution:** Manual update is recommended for safety.
- **Regex Helper:**
  ```python
  def convert_sql(sql):
      parts = sql.split('%s')
      if len(parts) == 1: return sql
      return "".join(p + f"${i+1}" for i, p in enumerate(parts[:-1])) + parts[-1]
  ```
  *Use with caution.*

### 3.2 Transaction Management
- `psycopg2` requires explicit `commit()`.
- `asyncpg` is in auto-commit mode by default.
- **Action:** Remove `conn.commit()` calls. Use `async with conn.transaction():` if atomicity is required across multiple statements.

### 3.3 Result Access
- `psycopg2` (RealDictCursor): `row['column']`
- `asyncpg` (Record): `row['column']` (compatible!)
- **Action:** No change needed for row access, but `fetchall()` becomes `await conn.fetch()`.

## 4. Step-by-Step Plan

1.  **Implement Infrastructure:** Add `AsyncAutoClosingConnection` and async adapter caching to `claude_mcp_hybrid_sessions.py`.
2.  **Convert Helper Functions:** Update `_get_session_id_for_project`, `_fetch_context_by_version`, etc., to be async.
3.  **Batch Convert Tools:**
    - Batch A: Read-only tools (`search_contexts`, `recall_context`).
    - Batch B: Write tools (`lock_context`, `update_context`).
    - Batch C: Project management tools (`create_project`, `switch_project`).
4.  **Verify:** Run `test_systematic_tool_check.py` (needs update for async).

## 5. Risk Mitigation
- Keep the sync adapter and `AutoClosingPostgreSQLConnection` during migration to allow incremental conversion if possible (though mixing sync/async in one file is messy).
- **Recommendation:** Create a new file `claude_mcp_async_sessions.py` and migrate tools there one by one, then swap the import in `server_hosted.py`. This avoids breaking the existing file during the process.
