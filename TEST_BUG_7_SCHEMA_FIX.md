# Test Prompt for Bug #7 Fix (Deployment 27fe4901)

## Deployment Info
- **Deployment ID**: 27fe4901
- **Status**: BUILDING (started 20:22 UTC)
- **Purpose**: Fix schema mismatch between middleware and tools
- **Commit**: 9d9177f

## The Fix

**Root Cause**:
- `server_hosted.py` imported `_get_db_adapter` from OLD module (`claude_mcp_hybrid`)
- Tools imported `_get_db_adapter` from NEW module (`claude_mcp_hybrid_sessions`)
- Result: Two separate adapter instances with potentially different schemas
- Middleware queried one schema, tools wrote to another schema

**Fix Applied**:
- Changed both imports in `server_hosted.py` to use `claude_mcp_hybrid_sessions`
- Now middleware and tools share SAME adapter instance
- Both query SAME schema/table for `mcp_sessions`
- UPDATE and SELECT now see same data

## Test Instructions

Copy and paste this into Claude.ai Desktop:

---

Please test the full workflow:

1. First, call `list_projects()` to see available projects

2. Then call `select_project_for_session("linkedin")` to select the linkedin project

3. Then call `get_last_handover()` to verify it works (this was previously stuck)

4. Let me know if all three steps succeed without any "Pending session" errors

---

## Expected Results

### If Bug #7 is FIXED ✅

1. `list_projects()` succeeds → Shows linkedin project
2. `select_project_for_session("linkedin")` succeeds → Returns success message
3. `get_last_handover()` succeeds → Returns handover data (or "no previous session" if first use)

**Logs should show**:
```
20:XX:XX - ✅ PostgreSQL/Neon connected (schema: workspace)
20:XX:XX - 🔵 STEP 4d: About to UPDATE mcp_sessions for session xxxxxxxx, project: 'linkedin'
20:XX:XX - 🔵 STEP 4e: Executing UPDATE statement...
20:XX:XX - 🔵 STEP 4f: UPDATE executed, rowcount=1, committing...
20:XX:XX - 🔵 STEP 4g: Commit completed successfully
20:XX:XX - 🔵 STEP 4h: Setting _active_projects[xxxxxxxx] = 'linkedin'
```

### If Bug #7 Still Exists ❌

1. `list_projects()` succeeds ✅
2. `select_project_for_session("linkedin")` succeeds ✅
3. `get_last_handover()` FAILS or hangs ❌
   - Error: "Pending session xxxxxxxx requires project selection"
   - Stuck for 30-90 seconds

## What This Proves

**If successful**: Both middleware and tools are now querying the same schema/table. The session project_name is being updated and read from the same location.

**Database verification** (if needed):
- Session should exist in `workspace.mcp_sessions` (not `public.mcp_sessions`)
- Session's `project_name` should be `'linkedin'` (not `'__PENDING__'`)

## Success Criteria

The bug is FIXED when:
- ✅ `select_project_for_session("linkedin")` succeeds
- ✅ `get_last_handover()` succeeds immediately (no 90-second hang)
- ✅ No "Pending session" error messages
- ✅ All tools are now accessible (not just project selection tools)

---

**Investigation**: Bug #7 - Schema Mismatch Between Middleware and Tools
**Method**: Fixed module imports to use same adapter instance
**Deployment**: 27fe4901 (BUILDING since 20:22 UTC)
**Previous Deployments**: 05fdb48b (added breadcrumb logging)

## Bug History

- **Bug #1-5**: Database adapter initialization issues (FIXED)
- **Bug #6**: Transaction rollback issues (FIXED)
- **Bug #7**: Schema mismatch causing permanent "Pending session" state (FIXING NOW)

All bugs have now been systematically identified and fixed.
