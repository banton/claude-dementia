# Test Prompt for Bug #7 Fix - CORRECTED WORKFLOW

## Current Status
- **Deployment**: 27fe4901 (ACTIVE since 20:24 UTC)
- **Bug #7 Fix**: Schema mismatch between middleware and tools - DEPLOYED ✅
- **Issue**: User hasn't tested the correct workflow since fix deployed

## Why Tools Seem Broken

Looking at production logs, the tools being blocked are:
- `get_last_handover` (20:28 UTC) → NOT in whitelist
- `explore_context_tree` (20:28 UTC) → NOT in whitelist

These tools **REQUIRE** a project to be selected first! They are being correctly blocked.

The whitelisted tools that work WITHOUT project selection are:
- `list_projects()`
- `get_project_info(project_name)`
- `select_project_for_session(project_name)`

## Correct Test Workflow

Copy and paste this into Claude.ai Desktop (fresh session):

---

Please test the Dementia MCP server by following these exact steps in order:

**Step 1:** Call `list_projects()` to see available projects.

**Step 2:** Call `select_project_for_session("linkedin")` to select the linkedin project.

**Step 3:** Call `get_last_handover()` to verify it works after project selection.

If all three steps succeed without errors, the system is fixed!

---

## Expected Results

### ✅ If Bug #7 is FIXED

**Step 1 - `list_projects()`**:
- Returns: List of available projects including "linkedin"
- Logs show: `🔵 STEP 1: Allowing project selection tool 'list_projects'...`

**Step 2 - `select_project_for_session("linkedin")`**:
- Returns: Success message
- Logs show:
  ```
  🔵 STEP 4d: About to UPDATE mcp_sessions...
  🔵 STEP 4e: Executing UPDATE statement...
  🔵 STEP 4f: UPDATE executed, rowcount=1, committing...
  🔵 STEP 4g: Commit completed successfully
  🔵 STEP 4h: Setting _active_projects[xxxxxxxx] = 'linkedin'
  ```

**Step 3 - `get_last_handover()`**:
- Returns: Handover data (or "no previous session" if first use)
- NO "Pending session" error
- NO 90-second hang
- Completes in <5 seconds

### ❌ If Bug #7 Still Exists

**Step 1**: Works ✅
**Step 2**: Appears to work ✅ (logs show UPDATE succeeded)
**Step 3**: FAILS ❌
- Error: "Pending session xxxxxxxx requires project selection"
- Stuck for 30-90 seconds
- Returns 400 status

## Why This Test Is Important

Previous tests were incomplete:
1. Old sessions from before the fix were being tested
2. Tools were called WITHOUT selecting a project first
3. Expected behavior (blocking tools before project selection) looked like bugs

This test ensures:
1. Fresh session with Bug #7 fix deployed
2. Correct workflow (list → select → use tools)
3. Both middleware and tools using same database schema
4. Session updates are visible to both components

## Technical Details

**Bug #7 Root Cause**: `server_hosted.py` imported `_get_db_adapter` from wrong module

**Before (BROKEN)**:
```python
# Line 236, 414 in server_hosted.py
from claude_mcp_hybrid import _get_db_adapter
```

**After (FIXED)**:
```python
# Line 236, 414 in server_hosted.py
from claude_mcp_hybrid_sessions import _get_db_adapter
```

**Impact**:
- Middleware used adapter from old module → Instance A
- Tools used adapter from new module → Instance B
- Different instances = different database connections
- UPDATE went to Instance B's connections
- Middleware checked Instance A's connections → Didn't see update!

**Fix deployed**: Commit 9d9177f, Deployment 27fe4901, ACTIVE at 20:24 UTC

---

**Status**: READY FOR USER TESTING
**Created**: 2025-11-15 20:40 UTC
**Test Required**: Follow exact 3-step workflow above
