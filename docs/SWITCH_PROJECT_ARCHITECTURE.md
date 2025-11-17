# switch_project() Architecture & Dependencies

**File:** `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py`
**Lines:** 1995-2106
**Purpose:** Switch active project for current MCP session
**Date:** 2025-11-17

---

## Executive Summary

`switch_project()` is a **critical session management function** that changes which PostgreSQL schema is used for all subsequent memory operations. It updates both persistent storage (database) and in-memory cache, then queries the project schema to verify existence and return statistics.

**Critical for Refactoring:** This function is a **state mutation point** that affects ALL downstream tools. Any changes must preserve the exact update sequence and side effects.

---

## 1. Function Signature

```python
@mcp.tool()
async def switch_project(name: str) -> str
```

**Parameters:**
- `name: str` - Project name to switch to (will be sanitized)

**Returns:**
- `str` - JSON string with switch status and project info

---

## 2. Dependencies Graph

```
switch_project()
├── IMPORTS (local)
│   ├── json (stdlib)
│   └── re (stdlib)
│
├── GLOBAL VARIABLES (read)
│   ├── _session_store: PostgreSQLSessionStore
│   ├── _local_session_id: str
│   └── _active_projects: dict[str, str]
│
├── GLOBAL VARIABLES (write)
│   └── _active_projects[_local_session_id] = safe_name
│
├── EXTERNAL MODULES
│   ├── sys (stderr output)
│   ├── config (config.database_url)
│   ├── psycopg2 (connection, cursor)
│   └── psycopg2.extras.RealDictCursor
│
├── EXTERNAL OBJECTS
│   ├── _session_store.update_session_project()
│   └── conn/cursor (psycopg2)
│
└── DATABASE TABLES
    ├── mcp_sessions (UPDATE project_name)
    └── information_schema.schemata (SELECT)
    └── {schema}.sessions (SELECT COUNT)
    └── {schema}.context_locks (SELECT COUNT)
```

---

## 3. Data Flow Diagram

```
INPUT: name="innkeeper"
   ↓
[1] SANITIZE: name → safe_name="innkeeper"
   │   • Convert to lowercase
   │   • Replace non-alphanumeric with underscore
   │   • Collapse multiple underscores
   │   • Truncate to 32 chars
   ↓
[2] VALIDATE GLOBALS
   │   • Check _session_store exists
   │   • Check _local_session_id exists
   │   → FAIL: Return error JSON
   ↓
[3] UPDATE DATABASE (mcp_sessions table)
   │   _session_store.update_session_project(_local_session_id, safe_name)
   │   → UPDATE mcp_sessions SET project_name = 'innkeeper' WHERE session_id = ?
   │   → Returns: boolean (updated)
   ↓
[4] UPDATE IN-MEMORY CACHE
   │   _active_projects[_local_session_id] = safe_name
   │   → For backwards compatibility with legacy code
   ↓
[5] QUERY PROJECT EXISTENCE
   │   • Create NEW psycopg2 connection (config.database_url)
   │   • Query: information_schema.schemata
   │   → Returns: boolean (exists)
   ↓
[6a] IF EXISTS: GET STATS
   │    • Query: SELECT COUNT(*) FROM "{safe_name}".sessions
   │    • Query: SELECT COUNT(*) FROM "{safe_name}".context_locks
   │    • Close connection
   │    → Return success JSON with stats
   ↓
[6b] IF NOT EXISTS:
      • Close connection
      → Return success JSON (will be created on first use)
   ↓
OUTPUT: JSON string with success/error status
```

---

## 4. Side Effects (CRITICAL)

### 4.1 Database Writes

```sql
-- Effect #1: Update global session project
UPDATE mcp_sessions
SET project_name = 'innkeeper'
WHERE session_id = '3b68d4a...'
```

**Impact:** Changes project for ALL subsequent tool calls in this session

### 4.2 Global State Mutations

```python
# Effect #2: Update in-memory cache
_active_projects[_local_session_id] = safe_name
```

**Impact:** Fast lookup for `_get_project_for_context()` without DB query

### 4.3 Database Reads

```sql
-- Effect #3: Schema existence check
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'innkeeper'

-- Effect #4: Count sessions (if exists)
SELECT COUNT(*) as count
FROM "innkeeper".sessions

-- Effect #5: Count contexts (if exists)
SELECT COUNT(*) as count
FROM "innkeeper".context_locks
```

**Impact:** Read-only queries for user feedback

### 4.4 Console Output

```python
# Effect #6: Status messages to stderr
print(f"✅ Switched to project: {safe_name} (session: {_local_session_id[:8]})",
      file=sys.stderr)
```

**Impact:** User visibility in MCP logs

---

## 5. Integration Points

### 5.1 UPSTREAM: Functions that Call switch_project

**Direct Calls:**
- User via MCP tool invocation
- Tests: `test_project_isolation_fix.py`

**No internal function calls this** - it's a leaf tool called by users only.

### 5.2 DOWNSTREAM: Functions that Read Project State

**All tools that accept `project: Optional[str]` parameter:**

```python
# Core memory tools
lock_context(content, topic, project=None)          # Line 3554
recall_context(topic, project=None)                 # Line 3807
check_contexts(text, project=None)                  # Line 6141

# Session tools
wake_up(project=None)                               # Line 2717
sleep(project=None)                                 # Line 2990
get_last_handover(project=None)                     # Line 3298

# Batch tools
batch_lock_contexts(contexts, project=None)         # Line 4293
batch_recall_contexts(topics, project=None)         # Line 4394

# And 15+ more tools...
```

**All these tools call:**

```python
def _get_project_for_context(project: str = None) -> str:
    """
    Priority:
    1. Explicit project parameter
    2. Session active project (from database) ← switch_project sets this
    3. Auto-detect from filesystem
    4. Fall back to "default"
    """
    if project:
        return project

    # READ from switch_project's state:
    session_id = _get_local_session_id()
    if session_id in _active_projects:
        return _active_projects[session_id]  # In-memory cache

    # Fallback: read from database
    result = conn.execute(
        "SELECT active_project FROM sessions WHERE id = ?",
        (session_id,)
    )
    # ...
```

**Critical Dependency:** If `switch_project` doesn't update correctly, ALL tools will use wrong schema!

---

## 6. Database Schema Relationships

### 6.1 Global Session Store (mcp_sessions table)

```sql
-- Located in: public.mcp_sessions
CREATE TABLE mcp_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    expires_at TIMESTAMP,
    capabilities TEXT[],
    client_info JSONB,
    project_name TEXT,  ← switch_project updates this
    session_summary TEXT
);
```

**Updated by:** `_session_store.update_session_project()`

### 6.2 Project Schemas (per-project isolation)

```sql
-- Located in: {project_name} schema (e.g., "innkeeper")
CREATE SCHEMA innkeeper;

-- Each schema has:
CREATE TABLE innkeeper.sessions (...);        ← switch_project counts this
CREATE TABLE innkeeper.context_locks (...);   ← switch_project counts this
CREATE TABLE innkeeper.memory_entries (...);
CREATE TABLE innkeeper.file_tags (...);
```

**Read by:** switch_project for statistics

---

## 7. Call Hierarchy

### 7.1 switch_project's Internal Calls

```
switch_project(name)
├── re.sub()                                          # Sanitize name
├── _session_store.update_session_project()
│   └── PostgreSQLSessionStore.update_session_project()
│       ├── adapter.get_connection()
│       ├── cur.execute("UPDATE mcp_sessions SET...")
│       ├── conn.commit()
│       └── adapter.release_connection()
│
├── psycopg2.connect(config.database_url)
├── conn.cursor(cursor_factory=RealDictCursor)
├── cur.execute("SELECT FROM information_schema...")
├── cur.fetchone()
├── cur.execute(f'SELECT COUNT(*) FROM "{safe_name}".sessions')
├── cur.execute(f'SELECT COUNT(*) FROM "{safe_name}".context_locks')
└── conn.close()
```

### 7.2 Consumers of switch_project's State

```
_get_project_for_context()
├── _get_local_session_id() → _local_session_id
├── Check: session_id in _active_projects  ← switch_project sets this
└── Query: sessions.active_project         ← legacy, not used by switch_project

_get_db_for_project(project=None)
└── _get_project_for_context(project) → schema_name
    └── Used by ALL tools that access database

_check_project_selection_required(project=None)
├── _session_store.get_session(_local_session_id)
└── Check: session.project_name == '__PENDING__'  ← switch_project changes this
```

---

## 8. Critical Connections (DO NOT BREAK)

### 8.1 Session ID Must Match

```python
# CRITICAL: Must use same session_id for both operations
_session_store.update_session_project(_local_session_id, safe_name)  # Update DB
_active_projects[_local_session_id] = safe_name                       # Update cache
```

**Why:** If different IDs are used, tools will read from DB but cache won't match

**History:** This was Bug #1 (Nov 2025) - using different session IDs caused PROJECT_SELECTION_REQUIRED errors

### 8.2 Update Order Matters

```python
# 1. MUST update database first
updated = _session_store.update_session_project(...)
if not updated:
    return error  # Don't update cache if DB update failed

# 2. THEN update in-memory cache
_active_projects[_local_session_id] = safe_name
```

**Why:** If cache is updated but DB update fails, next request reads wrong project from DB

### 8.3 Project Name Sanitization

```python
# MUST sanitize BEFORE any database operations
safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]
```

**Why:** PostgreSQL schema names have strict rules; unsanitized names cause SQL errors

### 8.4 Connection Management

```python
# MUST create new connection (don't reuse _postgres_adapter)
conn = psycopg2.connect(config.database_url)
# ... queries ...
conn.close()  # MUST close explicitly
```

**Why:** switch_project needs to query schemas that may not exist yet; reusing cached adapter would fail

---

## 9. Error Handling Patterns

### 9.1 Session Not Initialized

```python
if not _session_store or not _local_session_id:
    return json.dumps({
        "success": False,
        "error": "No active session - session store not initialized"
    })
```

**When:** MCP server started without session initialization

### 9.2 Database Update Failed

```python
try:
    updated = _session_store.update_session_project(_local_session_id, safe_name)
    if not updated:
        return json.dumps({
            "success": False,
            "error": f"Session {_local_session_id[:8]} not found in database"
        })
except Exception as e:
    return json.dumps({
        "success": False,
        "error": f"Failed to update session: {str(e)}"
    })
```

**When:** Session was deleted or DB connection lost

### 9.3 Schema Query Failed

```python
try:
    # All switch logic
except Exception as e:
    return json.dumps({
        "success": False,
        "error": str(e)
    })
```

**When:** Database unavailable or permission error

---

## 10. Testing Strategy

### 10.1 Existing Tests

**File:** `/home/user/claude-dementia/test_project_isolation_fix.py`

**Tests:**
1. Switch to project 'test_project_a'
2. Clear in-memory cache (simulate stateless HTTP)
3. Verify `_get_project_for_context()` reads from DB
4. Lock context without explicit project parameter
5. Switch to project 'test_project_b'
6. Verify project isolation (contexts don't cross projects)

### 10.2 Critical Test Cases for Refactoring

```python
# Test 1: Basic switch succeeds
result = await switch_project('my_project')
assert json.loads(result)['success'] == True

# Test 2: Database persistence
await switch_project('project_a')
_active_projects.clear()  # Simulate stateless
assert _get_project_for_context() == 'project_a'

# Test 3: Downstream tools respect switch
await switch_project('project_b')
result = await lock_context('test', 'topic')
assert 'project_b' in result  # Verify correct schema used

# Test 4: Error handling
_local_session_id = None
result = await switch_project('test')
assert json.loads(result)['success'] == False

# Test 5: Name sanitization
result = await switch_project('My-Project 2024!')
data = json.loads(result)
assert data['schema'] == 'my_project_2024'
```

---

## 11. Refactoring Guidelines

### 11.1 Safe to Change

✅ **Variable names** (internal to function)
✅ **Error messages** (user-facing strings)
✅ **Comment improvements**
✅ **Console output format** (stderr prints)
✅ **Query optimization** (as long as results are same)

### 11.2 MUST PRESERVE

🚫 **Function signature** - `async def switch_project(name: str) -> str`
🚫 **Global state updates** - `_active_projects[_local_session_id] = safe_name`
🚫 **Database update call** - `_session_store.update_session_project()`
🚫 **Update order** - Database THEN cache
🚫 **Session ID source** - Must use `_local_session_id`
🚫 **Return type** - JSON string with specific schema

### 11.3 Extraction Candidates

These can be extracted to helper functions:

```python
# Can extract:
def _sanitize_project_name(name: str) -> str:
    safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
    return re.sub(r'_+', '_', safe_name).strip('_')[:32]

def _get_project_stats(schema_name: str) -> dict:
    conn = psycopg2.connect(config.database_url)
    # ... query stats ...
    conn.close()
    return {"sessions": count1, "contexts": count2}

def _check_schema_exists(schema_name: str) -> bool:
    conn = psycopg2.connect(config.database_url)
    # ... check existence ...
    conn.close()
    return exists
```

**Benefits:**
- Easier to test in isolation
- Clearer separation of concerns
- Better error handling per operation

**Risks:**
- Must preserve exact behavior
- Must maintain connection lifecycle (open/close)
- Must handle errors consistently

---

## 12. Related Functions (Refactoring Context)

### 12.1 Functions in Same Domain

```python
# Project management tools
create_project(name)              # Line 2200 - Creates new project schema
list_projects()                   # Line 2276 - Lists all projects
get_project_info(name)            # Line 2357 - Get project details
delete_project(name, confirm)     # Line 2466 - Delete project
select_project_for_session(name)  # Line 2540 - Alternative to switch_project

# Project resolution helpers
_get_project_for_context(project) # Line 396  - Resolve which project to use
_check_project_selection_required() # Line 321 - Validate project selected
_get_db_for_project(project)      # Line 599  - Get DB connection for project
```

**Recommendation:** Refactor as a group to ensure consistency

### 12.2 Session Management Functions

```python
_init_local_session()             # Line 184  - Initialize session
_get_local_session_id()           # Line 237  - Get session ID
_auto_load_handover()             # Line 241  - Load previous session
```

**Dependency:** switch_project requires session to be initialized first

---

## 13. Monitoring & Debugging

### 13.1 Debug Logging Points

```python
# Add these to debug switch_project issues:
print(f"[DEBUG] switch_project called: name={name}", file=sys.stderr)
print(f"[DEBUG] sanitized: {safe_name}", file=sys.stderr)
print(f"[DEBUG] session_id: {_local_session_id}", file=sys.stderr)
print(f"[DEBUG] DB update result: {updated}", file=sys.stderr)
print(f"[DEBUG] cache updated: {_local_session_id in _active_projects}", file=sys.stderr)
print(f"[DEBUG] schema exists: {exists}", file=sys.stderr)
```

### 13.2 Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No active session" error | Session not initialized | Call `_init_local_session()` first |
| "Session not found" error | Session ID mismatch | Verify `_local_session_id` is correct |
| "PROJECT_SELECTION_REQUIRED" after switch | Cache not updated | Check `_active_projects` dictionary |
| Wrong schema used by tools | DB update failed | Check `_session_store.update_session_project()` return value |
| Schema not found error | Project doesn't exist | Create with `create_project()` first |

### 13.3 State Inspection Queries

```sql
-- Check session's current project
SELECT session_id, project_name, last_active
FROM mcp_sessions
WHERE session_id = '3b68d4a...';

-- List all projects
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name NOT IN ('public', 'pg_catalog', 'information_schema');

-- Check project stats
SELECT
    (SELECT COUNT(*) FROM "innkeeper".sessions) as sessions,
    (SELECT COUNT(*) FROM "innkeeper".context_locks) as contexts;
```

---

## 14. Performance Considerations

### 14.1 Current Performance

- **Database writes:** 1 UPDATE statement (mcp_sessions)
- **Database reads:** 1-3 SELECT statements (schema check + stats)
- **Connection overhead:** Creates new connection (not pooled)
- **Typical latency:** 50-200ms (depends on DB location)

### 14.2 Optimization Opportunities

```python
# BEFORE: Creates new connection every time
conn = psycopg2.connect(config.database_url)

# AFTER: Reuse adapter's connection pool
conn = _postgres_adapter.get_connection()
try:
    # ... queries ...
finally:
    _postgres_adapter.release_connection(conn)
```

**Benefits:**
- Faster (no connection overhead)
- Better connection pooling
- Consistent with other tools

**Risks:**
- Adapter may be schema-specific
- Need to ensure queries don't affect search_path

### 14.3 Caching Strategy

```python
# Current: No caching of project existence
# Every switch_project call queries information_schema

# Potential: Cache project existence
_project_exists_cache = {}  # {schema_name: (exists, timestamp)}

def _check_schema_exists_cached(schema_name: str) -> bool:
    if schema_name in _project_exists_cache:
        exists, cached_at = _project_exists_cache[schema_name]
        if time.time() - cached_at < 300:  # 5 min cache
            return exists

    # Query DB and cache result
    exists = _check_schema_exists(schema_name)
    _project_exists_cache[schema_name] = (exists, time.time())
    return exists
```

**Caution:** Cache invalidation needed when projects are created/deleted

---

## 15. Security Considerations

### 15.1 SQL Injection Prevention

```python
# ✅ SAFE: Parameterized query
cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
            (safe_name,))

# ❌ UNSAFE: F-string with user input (NOT USED)
# cur.execute(f"SELECT * FROM {name}.sessions")  # DON'T DO THIS
```

**Current Status:** ✅ All queries are safe

**Special Case:** Schema name in query requires sanitization:

```python
# Schema names can't be parameterized in PostgreSQL
cur.execute(f'SELECT COUNT(*) FROM "{safe_name}".sessions')

# MUST sanitize before using in f-string
safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())  # Only alphanum + underscore
```

### 15.2 Access Control

**Current:** No project-level access control - any session can switch to any project

**Future Consideration:**
```python
# Check if user has access to project
if not _session_store.user_has_project_access(user_id, safe_name):
    return json.dumps({
        "success": False,
        "error": f"Access denied to project '{name}'"
    })
```

---

## 16. Documentation Requirements

### 16.1 Update These Docs After Refactoring

- ✅ `/home/user/claude-dementia/README.md` - Tool descriptions
- ✅ `/home/user/claude-dementia/docs/PROJECT_SELECTION_REFACTOR.md` - Architecture notes
- ✅ `/home/user/claude-dementia/TOOL_INTEROP_MAP.md` - Call graph
- ✅ `/home/user/claude-dementia/docs/SESSION_MANAGEMENT_ENHANCEMENTS.md` - Session flows

### 16.2 Code Comments to Preserve

```python
# UNIVERSAL PROJECT SELECTION: Use _local_session_id as single source of truth
# This comment explains critical design decision (Bug #1 fix)

# Also update in-memory cache for backwards compatibility
# Explains why _active_projects is still maintained
```

---

## 17. Rollback Plan

### 17.1 Pre-Refactor Backup

```bash
# Create backup of current function
git show HEAD:claude_mcp_hybrid_sessions.py | \
    sed -n '1995,2106p' > /tmp/switch_project_backup.py
```

### 17.2 Rollback Procedure

If refactored version breaks:

1. **Immediate:** Restore from backup
2. **Verify:** Run `test_project_isolation_fix.py`
3. **Check:** Ensure `_active_projects` is updated
4. **Test:** Manual switch + tool call flow

### 17.3 Validation Checklist

- [ ] All tests pass
- [ ] Manual switch + lock_context works
- [ ] Project stats are displayed correctly
- [ ] Error handling works (invalid session, missing project)
- [ ] Stateless operation works (cache cleared between calls)
- [ ] Downstream tools use correct project

---

## 18. Conclusion

`switch_project()` is a **critical state mutation function** that:

1. **Updates persistent storage** (mcp_sessions.project_name)
2. **Updates in-memory cache** (_active_projects dictionary)
3. **Affects ALL downstream tools** via `_get_project_for_context()`

**Key Insight:** This function is the **single source of truth** for project selection in a session.

**Refactoring Risk Level:** 🔴 **HIGH**

**Recommended Approach:**
1. Extract helper functions (name sanitization, stats, schema check)
2. Add comprehensive unit tests for each helper
3. Refactor main function to use helpers
4. Run integration tests to verify whole system
5. Document all changes

**Success Criteria:**
- All existing tests pass
- New unit tests for helpers pass
- Manual testing confirms correct behavior
- No breaking changes to API contract
- Performance maintained or improved

---

## Appendix A: Full Function Listing

```python
@mcp.tool()
async def switch_project(name: str) -> str:
    """
    Switch to a different project for this conversation.

    All subsequent memory operations (lock_context, recall_context, etc.)
    will use this project unless explicitly overridden.

    Args:
        name: Project name to switch to

    Returns:
        JSON with switch status and project info

    Example:
        User: "Switch to my innkeeper project"
        Claude: switch_project(name="innkeeper")
        Claude: "Switched to innkeeper project!"

        User: "Switch to linkedin"
        Claude: switch_project(name="linkedin")
        Claude: "Switched! (Project will be created if it doesn't exist)"
    """
    import json
    import re

    try:
        # Sanitize project name
        safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]

        # UNIVERSAL PROJECT SELECTION: Use _local_session_id as single source of truth
        if not _session_store or not _local_session_id:
            return json.dumps({
                "success": False,
                "error": "No active session - session store not initialized"
            })

        # Update the global session store's project_name field (SINGLE SOURCE OF TRUTH)
        try:
            updated = _session_store.update_session_project(_local_session_id, safe_name)
            if updated:
                print(f"✅ Switched to project: {safe_name} (session: {_local_session_id[:8]})", file=sys.stderr)
            else:
                print(f"⚠️  Session not found: {_local_session_id[:8]}", file=sys.stderr)
                return json.dumps({
                    "success": False,
                    "error": f"Session {_local_session_id[:8]} not found in database"
                })
        except Exception as e:
            print(f"❌ Failed to update session project: {e}", file=sys.stderr)
            return json.dumps({
                "success": False,
                "error": f"Failed to update session: {str(e)}"
            })

        # Also update in-memory cache for backwards compatibility
        _active_projects[_local_session_id] = safe_name

        # Check if project exists
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(config.database_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = %s
        """, (safe_name,))

        exists = cur.fetchone() is not None

        if exists:
            # Get project stats
            cur.execute(f'SELECT COUNT(*) as count FROM "{safe_name}".sessions')
            sessions = cur.fetchone()['count']

            cur.execute(f'SELECT COUNT(*) as count FROM "{safe_name}".context_locks')
            contexts = cur.fetchone()['count']

            conn.close()

            return json.dumps({
                "success": True,
                "message": f"✅ Switched to project '{name}'",
                "project": name,
                "schema": safe_name,
                "exists": True,
                "stats": {
                    "sessions": sessions,
                    "contexts": contexts
                },
                "note": "All memory operations will now use this project"
            })
        else:
            conn.close()

            return json.dumps({
                "success": True,
                "message": f"✅ Switched to project '{name}' (will be created on first use)",
                "project": name,
                "schema": safe_name,
                "exists": False,
                "note": "Project schema will be created automatically when you use memory tools"
            })

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })
```

---

## Appendix B: Related Code References

### PostgreSQLSessionStore.update_session_project()
**File:** `/home/user/claude-dementia/mcp_session_store.py`
**Lines:** 259-285

```python
def update_session_project(self, session_id: str, project_name: str) -> bool:
    """
    Update session's project_name field (e.g., from __PENDING__ to actual project).

    Args:
        session_id: Session identifier
        project_name: New project name to set

    Returns:
        True if session was updated, False if session not found
    """
    conn = self.adapter.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE mcp_sessions
                SET project_name = %s
                WHERE session_id = %s
            """, (project_name, session_id))

            updated = cur.rowcount > 0
            conn.commit()

            return updated

    finally:
        self.adapter.release_connection(conn)
```

### _get_project_for_context()
**File:** `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py`
**Lines:** 396-465

```python
def _get_project_for_context(project: str = None) -> str:
    """
    Determine which project to use for this operation.

    Priority:
    1. Explicit project parameter
    2. Session active project (from database, set via switch_project)
    3. Auto-detect from filesystem (Claude Code with git repo)
    4. Fall back to "default"

    Returns:
        str: Project name/schema to use
    """
    # Priority 1: Explicit parameter
    if project:
        return project

    # Priority 2: Session active project (from database for MCP server persistence)
    try:
        session_id = _get_local_session_id()

        if not session_id:
            pass  # Fall through to Priority 3
        else:
            # First check in-memory cache
            if session_id in _active_projects:
                return _active_projects[session_id]

            # Then check database (for MCP server statelessness)
            try:
                adapter = _get_db_adapter()
                with adapter.get_connection() as conn:
                    result = conn.execute_with_conversion(
                        "SELECT active_project FROM sessions WHERE id = ? AND active_project IS NOT NULL",
                        (session_id,),
                        fetchone=True
                    )
                    if result:
                        active_project = result[0] if isinstance(result, tuple) else result.get('active_project')
                        if active_project:
                            # Cache it in memory for faster subsequent lookups
                            _active_projects[session_id] = active_project
                            return active_project
            except:
                pass
    except:
        pass

    # Priority 3: Auto-detect from filesystem (Claude Code only)
    if _get_db_adapter().schema and _get_db_adapter().schema != 'default':
        return _get_db_adapter().schema

    # Priority 4: Default project
    return "default"
```

---

**END OF DOCUMENT**
