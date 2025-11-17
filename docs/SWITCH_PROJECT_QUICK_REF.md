# switch_project() Quick Reference Card

**Critical for refactoring - keep this handy!**

---

## Function Summary

```python
@mcp.tool()
async def switch_project(name: str) -> str
```

**Purpose:** Change active project for current MCP session
**Location:** `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py:1995-2106`

---

## Critical Dependencies (DO NOT BREAK)

### Global Variables

| Variable | Type | Read/Write | Purpose |
|----------|------|------------|---------|
| `_session_store` | PostgreSQLSessionStore | Read | Database operations |
| `_local_session_id` | str | Read | Current session ID (SINGLE SOURCE OF TRUTH) |
| `_active_projects` | dict[str, str] | Write | In-memory cache: {session_id → project_name} |
| `config.database_url` | str | Read | PostgreSQL connection string |

### Must-Preserve Operations

```python
# 1. Sanitize name (MUST happen first)
safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]

# 2. Update database (MUST use _local_session_id)
updated = _session_store.update_session_project(_local_session_id, safe_name)

# 3. Update cache (MUST use same _local_session_id)
_active_projects[_local_session_id] = safe_name
```

---

## Data Flow (One-Way Street)

```
USER: switch_project("my-project")
  ↓
SANITIZE: "my-project" → "my_project"
  ↓
UPDATE DB: mcp_sessions.project_name = "my_project"
  ↓
UPDATE CACHE: _active_projects[session_id] = "my_project"
  ↓
CHECK SCHEMA: Does "my_project" schema exist?
  ↓
GET STATS: Count sessions & contexts (if exists)
  ↓
RETURN: JSON success/error
```

**⚠️ Order Matters:** Database → Cache → Stats
**⚠️ Same Session ID:** Must use `_local_session_id` for both updates

---

## Integration Impact

### Consumers (Functions that read project state)

**ALL** tools with `project: Optional[str]` parameter:

```
lock_context()
recall_context()
check_contexts()
wake_up()
sleep()
batch_lock_contexts()
batch_recall_contexts()
get_last_handover()
semantic_search_contexts()
... and 15+ more
```

**How they consume:**

```python
def some_tool(project: Optional[str] = None):
    target_project = _get_project_for_context(project)
    #                     ↑
    #                     This reads from switch_project's state:
    #                     1. _active_projects[_local_session_id]
    #                     2. mcp_sessions.project_name
```

**🚨 If switch_project breaks, ALL tools break!**

---

## Database Impact

### Tables Updated

```sql
-- Global session store (1 UPDATE per switch)
UPDATE mcp_sessions
SET project_name = 'my_project'
WHERE session_id = '3b68d4a...';
```

### Tables Read

```sql
-- Schema existence check
SELECT schema_name FROM information_schema.schemata
WHERE schema_name = 'my_project';

-- Project stats (if exists)
SELECT COUNT(*) FROM "my_project".sessions;
SELECT COUNT(*) FROM "my_project".context_locks;
```

---

## Side Effects Checklist

When refactoring, ensure these still happen:

- [ ] Name sanitized (lowercase, alphanumeric + underscore only, max 32 chars)
- [ ] Database updated (`mcp_sessions.project_name`)
- [ ] Cache updated (`_active_projects[session_id]`)
- [ ] Same session ID used for both updates
- [ ] Schema existence checked
- [ ] Stats retrieved (if schema exists)
- [ ] Success/error JSON returned
- [ ] Status printed to stderr (✅/⚠️/❌)

---

## Error Cases to Handle

| Case | Check | Return |
|------|-------|--------|
| No session | `not _session_store or not _local_session_id` | `{"success": False, "error": "No active session"}` |
| Session not found | `updated == False` | `{"success": False, "error": "Session ... not found"}` |
| Update failed | `Exception in update_session_project()` | `{"success": False, "error": "Failed to update"}` |
| Any other error | `Exception in try block` | `{"success": False, "error": str(e)}` |

---

## Testing Requirements

### Must Pass Tests

```bash
# Existing test
python3 test_project_isolation_fix.py

# Manual verification
1. Switch to project → should succeed
2. Clear _active_projects → simulate stateless
3. Call lock_context → should use correct project
4. Verify project stats → should match database
```

### Test Cases

```python
# Test 1: Basic functionality
await switch_project('test_proj')  # Should succeed

# Test 2: Persistence (critical!)
await switch_project('proj_a')
_active_projects.clear()  # Simulate new request
assert _get_project_for_context() == 'proj_a'  # Should read from DB

# Test 3: Name sanitization
await switch_project('My Project-2024!')
# Should become: 'my_project_2024'

# Test 4: Error handling
_local_session_id = None
await switch_project('test')  # Should return error

# Test 5: Downstream integration
await switch_project('proj_b')
await lock_context('test', 'topic')  # Should use proj_b
```

---

## Refactoring Safety

### ✅ SAFE to Change

- Variable names (internal to function)
- Error message text
- Comment wording
- Console output format
- Query optimization (same results)

### 🚫 MUST NOT Change

- Function signature
- Global state updates
- Database operations
- Update order (DB → cache)
- Session ID source (`_local_session_id`)
- Return type (JSON string)

### ⚠️ Change with Caution

- Connection management (currently creates new conn)
- Error handling logic (return format)
- Sanitization regex (affects schema names)

---

## Common Failure Modes

| Symptom | Root Cause | Debug |
|---------|------------|-------|
| "PROJECT_SELECTION_REQUIRED" after switch | Cache not updated OR wrong session ID | Check `_active_projects` dict |
| Tools use wrong project | DB update failed | Check `mcp_sessions.project_name` |
| "No active session" error | Session not initialized | Check `_local_session_id` is set |
| "Session not found" error | Session deleted OR wrong ID | Query `mcp_sessions` table |
| SQL syntax error | Name not sanitized | Check `safe_name` regex |

---

## Quick Debug Commands

```python
# Check session state
print(f"Session ID: {_local_session_id}", file=sys.stderr)
print(f"Cache: {_active_projects}", file=sys.stderr)

# Check database state
session = _session_store.get_session(_local_session_id)
print(f"DB project: {session['project_name']}", file=sys.stderr)

# Check what tools will use
project = _get_project_for_context()
print(f"Active project: {project}", file=sys.stderr)
```

```sql
-- Check session in database
SELECT session_id, project_name, last_active
FROM mcp_sessions
WHERE session_id = '3b68d4a...';

-- Check schema exists
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'my_project';
```

---

## Related Functions to Review

When refactoring switch_project, also check:

| Function | File | Lines | Why |
|----------|------|-------|-----|
| `_get_project_for_context()` | claude_mcp_hybrid_sessions.py | 396-465 | Reads switch_project's state |
| `_check_project_selection_required()` | claude_mcp_hybrid_sessions.py | 321-394 | Validates project selected |
| `update_session_project()` | mcp_session_store.py | 259-285 | DB update implementation |
| `_init_local_session()` | claude_mcp_hybrid_sessions.py | 184-235 | Session initialization |
| `create_project()` | claude_mcp_hybrid_sessions.py | 2200 | Creates schemas |

---

## Extraction Opportunities

These can be extracted to helpers:

```python
# Extract #1: Name sanitization
def _sanitize_project_name(name: str) -> str:
    safe = re.sub(r'[^a-z0-9]', '_', name.lower())
    return re.sub(r'_+', '_', safe).strip('_')[:32]

# Extract #2: Schema existence check
def _schema_exists(schema_name: str) -> bool:
    conn = psycopg2.connect(config.database_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name = %s
        """, (schema_name,))
        return cur.fetchone() is not None
    finally:
        conn.close()

# Extract #3: Project stats
def _get_project_stats(schema_name: str) -> dict:
    conn = psycopg2.connect(config.database_url)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f'SELECT COUNT(*) as count FROM "{schema_name}".sessions')
        sessions = cur.fetchone()['count']
        cur.execute(f'SELECT COUNT(*) as count FROM "{schema_name}".context_locks')
        contexts = cur.fetchone()['count']
        return {"sessions": sessions, "contexts": contexts}
    finally:
        conn.close()

# Refactored switch_project would then be:
async def switch_project(name: str) -> str:
    safe_name = _sanitize_project_name(name)
    # ... validation ...
    updated = _session_store.update_session_project(_local_session_id, safe_name)
    _active_projects[_local_session_id] = safe_name
    exists = _schema_exists(safe_name)
    if exists:
        stats = _get_project_stats(safe_name)
        return json.dumps({...})
    else:
        return json.dumps({...})
```

**Benefits:**
- Each helper is testable in isolation
- Clearer separation of concerns
- Easier to maintain

**Risks:**
- Must preserve exact behavior
- Connection lifecycle must be correct
- Error handling must be consistent

---

## Success Criteria

Before merging refactored code:

- [ ] All existing tests pass
- [ ] New tests for helpers pass (if extracted)
- [ ] Manual test: switch + lock_context works
- [ ] Manual test: switch + clear cache + lock_context works
- [ ] Project stats displayed correctly
- [ ] Error messages unchanged (or improved)
- [ ] Performance maintained (no regression)
- [ ] Documentation updated
- [ ] Code review completed

---

## Emergency Rollback

```bash
# Restore original function
git show HEAD:claude_mcp_hybrid_sessions.py | \
    sed -n '1995,2106p' > switch_project_rollback.py

# Copy back to main file
# Manually replace lines 1995-2106 with rollback version

# Verify
python3 test_project_isolation_fix.py
```

---

## Key Insights

1. **Single Source of Truth:** `_local_session_id` MUST be used for both DB and cache updates
2. **Order Matters:** Database update → Cache update → Stats query
3. **Stateless Operation:** Must work even if `_active_projects` is cleared
4. **Critical Path:** ALL memory tools depend on this working correctly
5. **Bug History:** Using different session IDs was Bug #1 (Nov 2025)

---

## Questions to Ask During Refactoring

1. Does the refactored code use `_local_session_id` for both updates?
2. Is the update order preserved (DB → cache)?
3. Are all error cases still handled?
4. Is the return format still JSON with same schema?
5. Does it pass `test_project_isolation_fix.py`?
6. Does it work after clearing `_active_projects`?
7. Do downstream tools (lock_context, etc.) still work?
8. Is name sanitization still applied?
9. Are database connections properly closed?
10. Is performance maintained or improved?

---

**Remember:** This function is the **gateway** for project selection. If it breaks, the entire system breaks.

**Refactoring Risk Level:** 🔴 **HIGH** - Test thoroughly!
