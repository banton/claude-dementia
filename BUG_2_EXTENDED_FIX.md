# Bug #2 Extended Fix - search_contexts() Session Filter

**Date**: 2025-11-16
**Session**: Post-deployment verification
**Previous Fix**: Commit 7f4cf92 (explore_context_tree + context_dashboard)
**Current Deployment**: 171b1068 (ACTIVE)

## Discovery

During systematic code review to verify Bug #2 fix was complete, found one additional instance of the same bug pattern in `search_contexts()` function.

## Root Cause (Same as Bug #2)

PostgreSQL schema isolation already provides project-level filtering. Adding `WHERE session_id = ?` creates mismatch when switching projects:

1. User switches from `linkedin` to `innkeeper_claude`
2. PostgreSQL adapter switches to `dementia_innkeeper_claude` schema ✅
3. MCP session_id remains from linkedin session (`9ca91daa`) ❌
4. Query filters by session_id that doesn't exist in new schema ❌
5. Returns empty/wrong results ❌

## Affected Function

### search_contexts() - claude_mcp_hybrid_sessions.py:4628

**Location**: claude_mcp_hybrid_sessions.py:4628-4637

**Buggy Code**:
```python
# Fall back to keyword search
# Build SQL query
sql = """
    SELECT
        label, version, content, preview, key_concepts,
        locked_at, metadata, last_accessed, access_count
    FROM context_locks
    WHERE session_id = ?    # ❌ BUG - Redundant filter!
      AND (
          content LIKE ?
          OR preview LIKE ?
          OR key_concepts LIKE ?
          OR label LIKE ?
      )
"""

params = [session_id, f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%']
```

**Impact**:
- User calls `search_contexts("api")` after switching to new project
- Returns empty results even though contexts exist in new project
- Same symptom as Bug #2 in explore_context_tree()

**Fix**:
```python
# Fall back to keyword search
# Build SQL query
# NOTE: No session_id filter needed - schema isolation provides project-level isolation
sql = """
    SELECT
        label, version, content, preview, key_concepts,
        locked_at, metadata, last_accessed, access_count
    FROM context_locks
    WHERE (
        content LIKE ?
        OR preview LIKE ?
        OR key_concepts LIKE ?
        OR label LIKE ?
    )
"""

params = [f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%']
```

## Session_id Filters Review Summary

**Reviewed all session_id filters** in claude_mcp_hybrid_sessions.py:

### ✅ CORRECT (Keep as-is):

1. **Line 1102** - `health_check_and_repair()` validation
   - Checking for foreign session contexts (isolation violation detection)
   - PURPOSE: Verify no cross-session data leaks
   - Status: **CORRECT** - This filter is intentional

2. **Line 1764** - `load_stored_file_model()`
   - Loading file semantic model for specific session
   - PURPOSE: Track file changes per-session (not per-project)
   - Status: **CORRECT** - Session-level feature

3. **Line 1851** - `mark_file_deleted()`
   - Marking file as deleted in file semantic model
   - PURPOSE: Session-level file tracking
   - Status: **CORRECT** - Session-level feature

4. **Line 3338** - `get_last_handover()` querying mcp_sessions table
   - Getting session's handover from mcp_sessions table
   - PURPOSE: Retrieve specific session's data
   - Status: **CORRECT** - This is the sessions table itself

### ❌ BUGS FOUND (Fixed):

1. **Line 6387** - `explore_context_tree()` ✅ **FIXED** in commit 7f4cf92
2. **Line 6537-6595** - `context_dashboard()` (5 queries) ✅ **FIXED** in commit 7f4cf92
3. **Line 4628** - `search_contexts()` ❌ **NEEDS FIX** (this commit)

### ✅ ALREADY COMMENTED OUT (Historical fixes):

Lines 2910, 3073, 3145, 3234, 3486, 3506, 4788, 4812, 4832, 4851, 4871, 4892, 5395, 5413 - Previously removed in earlier refactorings

## Testing Plan

After deploying this fix, re-test the multi-project switching scenario:

```
1. list_projects()
2. select_project_for_session('linkedin')
3. search_contexts("authentication")  # Should return linkedin contexts
4. select_project_for_session('innkeeper_claude')
5. search_contexts("authentication")  # ← Should return innkeeper_claude contexts (not empty!)
```

## Deployment

- **Branch**: feature/dem-30-persistent-sessions
- **Files Changed**: claude_mcp_hybrid_sessions.py:4628-4637
- **Testing**: Systematic re-test after deployment
- **Risk**: LOW - Same fix pattern as Bug #2, already validated

---

**Session**: Continuing from CRITICAL_BUGS_TESTING_SESSION.md
**Previous Deployment**: 171b1068 (Bug #2 fix for explore_context_tree + context_dashboard)
**Next**: Deploy extended fix for search_contexts()
