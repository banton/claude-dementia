# Bug #7: Session project_name Not Persisting After UPDATE

## Date: Nov 15, 2025, 20:05 UTC
## Deployment: 05fdb48b (BUILDING)
## Investigation Status: IN PROGRESS

## Summary

`select_project_for_session('linkedin')` reports success, but the database still shows `project_name = '__PENDING__'` for all sessions. This blocks all subsequent tool calls because middleware checks for pending sessions.

## Evidence

### User Testing Results (19:46 UTC)

1. ✅ `list_projects()` - succeeded, shows linkedin with 3/20/25
2. ✅ `select_project_for_session("linkedin")` - succeeded with message "Project 'linkedin' selected"
3. ❌ `get_last_handover()` - FAILED, blocked with "Pending session 6a10f2b6"
4. ❌ `explore_context_tree()` - FAILED, blocked with "Pending session"

### Production Logs (19:46 UTC)

```
19:46:18 - 🔵 STEP 4: select_project_for_session ENTERED with project_name='linkedin'
19:46:18 - 🔵 STEP 4a: Got session_id from config: 31f8dfec
19:46:18 - 🔵 STEP 4b: Sanitized project name: 'linkedin' → 'linkedin'
19:46:22 - 🔵 STEP 4c: Got database adapter and session store
19:46:32 - {"event": "🔵 STEP 6: Response received from FastMCP, status: 200", ...}
```

**Critical Observation**: No breadcrumbs logged between STEP 4c and STEP 6, which is where the UPDATE statement should execute.

### Database State

```sql
-- Query: SELECT session_id, project_name, created_at FROM public.mcp_sessions ORDER BY created_at DESC LIMIT 10;
-- Result: ALL sessions show project_name = '__PENDING__'

Session: a5f54ad889da4eb8...
  Project: '__PENDING__'  # Should be 'linkedin' after selection
  Created: 2025-11-09 12:34:56.913110+00:00
  Active:  2025-11-09 12:34:56.913110+00:00
```

## The UPDATE Statement

**Location**: `claude_mcp_hybrid_sessions.py:2601-2612`

```python
# Update session with selected project
conn = adapter.get_connection()
try:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE mcp_sessions
            SET project_name = %s
            WHERE session_id = %s
        """, (safe_name, session_id))
        conn.commit()
finally:
    conn.close()
```

## Hypotheses

### Hypothesis 1: UPDATE Not Executing
- Code may be returning early before reaching UPDATE
- Exception may be caught silently
- Control flow may bypass UPDATE section

### Hypothesis 2: UPDATE Executing But Failing
- UPDATE may be executing but failing silently
- `cur.rowcount` would be 0 if WHERE clause doesn't match
- PostgreSQL error may be swallowed

### Hypothesis 3: Commit Not Working
- UPDATE may execute successfully
- Commit may fail silently
- Transaction may be rolled back later

### Hypothesis 4: Wrong Table/Schema
- UPDATE may be hitting wrong table
- Different schema than middleware is querying
- Connection to wrong database

## Investigation Strategy

### Phase 1: Add Breadcrumb Logging (CURRENT)

**Commit**: d687d6d

**Added breadcrumbs**:
- STEP 4d: About to UPDATE mcp_sessions for session {session_id[:8]}, project: '{safe_name}'
- STEP 4e: Executing UPDATE statement...
- STEP 4f: UPDATE executed, rowcount={cur.rowcount}, committing...
- STEP 4g: Commit completed successfully
- STEP 4h: Setting _active_projects[{session_id[:8]}] = '{safe_name}'

**Expected Results**:
- If we see STEP 4d but not 4e → Code returns early, never reaches UPDATE
- If we see STEP 4e but not 4f → UPDATE execution fails
- If we see STEP 4f with rowcount=0 → WHERE clause doesn't match (wrong session_id?)
- If we see STEP 4f with rowcount=1 but not 4g → Commit fails
- If we see all STEP 4d-4h → UPDATE succeeds, problem is elsewhere

### Phase 2: Verify Database (Next)

If UPDATE appears to succeed (all breadcrumbs present):
1. Check which database connection is used
2. Verify table schema matches
3. Query session immediately after UPDATE to confirm change
4. Check if middleware is querying different table/schema

### Phase 3: Check Middleware (If Needed)

If UPDATE succeeds but middleware still sees `__PENDING__`:
1. Verify middleware is querying same database
2. Check if middleware is caching session state
3. Verify timing (is middleware checking before UPDATE completes?)

## Deployment Timeline

1. **03857273** (15:00:27 UTC) - All previous bugs fixed, ACTIVE
2. **05fdb48b** (20:05:39 UTC) - Added STEP 4d-4h breadcrumbs, BUILDING

## Success Criteria

UPDATE is working correctly when:
1. Logs show all STEP 4d-4h breadcrumbs
2. STEP 4f shows `rowcount=1`
3. Database query shows `project_name = 'linkedin'` after selection
4. Subsequent tool calls (`get_last_handover`, etc.) succeed
5. Middleware no longer blocks tools with "Pending session" message

## Current Status

**Phase**: Investigation Phase 1 (Breadcrumb Logging)
**Deployment**: 05fdb48b building
**Next Step**: Wait for deployment to ACTIVE, then request user to test again and check logs

---

**Investigated By**: Claude Code (Sonnet 4.5)
**Investigation Started**: 2025-11-15 20:05 UTC
**Method**: Incremental breadcrumb logging to trace execution flow
