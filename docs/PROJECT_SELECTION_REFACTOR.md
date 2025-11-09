# Project Selection Refactor (2025-11-09)

## Problem

The project selection system had **three different session ID mechanisms** that didn't synchronize:

1. **`_session_store`** (mcp_sessions table) - Global session with `project_name` field
2. **`_active_projects`** dict - In-memory cache mapping session → project
3. **Project-specific sessions tables** - Each schema's sessions table with `active_project` field

### Symptoms
- `switch_project()` would succeed but tools still failed with "PROJECT_SELECTION_REQUIRED"
- `context_dashboard()` worked but `lock_context()` didn't (inconsistent checks)
- Three different session IDs in play: `get_current_session_id()`, `_local_session_id`, `session_id_for_project`

### Root Cause
`switch_project()` was updating:
- ✅ In-memory cache: `_active_projects[session_id]`
- ✅ Project-specific table: `UPDATE sessions SET active_project = ?`
- ✅ Global session store: `UPDATE mcp_sessions SET project_name = ?`

BUT it was using DIFFERENT session IDs for each update! The `_local_session_id` (used by tool checks) was never getting updated with the project selection.

## Solution

**Single Source of Truth**: `mcp_sessions.project_name` field, keyed by `_local_session_id`

### Changes Made

**File**: `claude_mcp_hybrid_sessions.py`
**Function**: `switch_project()` (lines 1997-2028)

#### Before:
```python
session_id = get_current_session_id()  # Project-specific ID
_active_projects[session_id] = safe_name  # Update in-memory
_session_store.update_session_project(_local_session_id, safe_name)  # Different ID!
# Also update project-specific sessions table with yet another ID
```

#### After:
```python
# Use _local_session_id as SINGLE source of truth
updated = _session_store.update_session_project(_local_session_id, safe_name)
_active_projects[_local_session_id] = safe_name  # Backwards compat only
# Removed confusing project-specific session updates
```

### Benefits

1. **Consistency**: All tools check the same session/project mapping
2. **Simplicity**: One session ID, one project field, one update
3. **Reliability**: No more sync issues between different session stores
4. **Debuggability**: Easy to trace which project a session is using

### Testing

After restart, the flow should be:
1. Server creates session with `_local_session_id` and `project_name='__PENDING__'`
2. User calls `switch_project("my_project")`
3. Session's `project_name` updated to `"my_project"`
4. All subsequent tools work without "PROJECT_SELECTION_REQUIRED" error

## Migration Notes

**No data migration needed** - this is a logic refactor only.

**Backwards compatibility**: The `_active_projects` in-memory cache is still updated for any legacy code that might reference it.

## Future Work

Consider removing:
- The confusing `get_current_session_id()` function
- Project-specific sessions tables (duplicative)
- The `_active_projects` in-memory dict (no longer needed)

Keep it simple: **One session store, one project field, one truth.**
