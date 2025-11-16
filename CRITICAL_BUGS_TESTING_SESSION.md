# CRITICAL BUGS DISCOVERED - MCP Testing Session

**Date**: 2025-11-16
**Session**: Systematic testing of 10 MCP tools with Claude.ai Desktop
**Deployment**: d98fca84 (ACTIVE) - Breadcrumb integration + MCP documentation fixes

## Test Results Summary

### Tests PASSED ✅
1. list_projects() - Retrieved 24 projects including linkedin
2. select_project_for_session('linkedin') - Successfully selected linkedin project
3. get_last_handover() - Retrieved handover (2.9 hours ago, session 9ca91daa) - "No 'Pending session'" error resolved
4. explore_context_tree() - Found 5 locked contexts (fewer than expected from project stats showing 20 contexts)

### Test 5 FAILED ❌
5. context_dashboard() - "No approval received" error
   - **UNEXPECTED**: Deployment d98fca84 should have included MCP documentation fixes

## CRITICAL BUGS DISCOVERED

### Bug #1: switch_project Tool Confusion 🐛

**Scenario**:
User attempted to switch from linkedin to innkeeper_claude project

**Issue**:
```
switch_project('innkeeper_claude') → FAILED
Error: "No active session - session store not initialized"
```

**Workaround**:
Had to use `select_project_for_session('innkeeper_claude')` instead, which worked.

**Root Cause**:
Two separate tools doing similar things:
- `switch_project` - For switching projects mid-session (requires active session)
- `select_project_for_session` - For initial project selection

**User Feedback**:
> "The switch project and select project for session should be merged to do both scenarios"

**Recommendation**:
Merge into single intelligent tool that:
- Creates session if none exists
- Switches project if session exists
- Single tool name: `select_project` or `use_project`

---

### Bug #2: PROJECT ISOLATION FAILURE ⚠️  **CRITICAL**

**Scenario**:
After successfully calling `select_project_for_session('innkeeper_claude')`, tools still queried linkedin project data.

**Evidence**:

1. **Successful Project Selection**:
   ```
   select_project_for_session('innkeeper_claude')
   ✅ Response: "Project switched to innkeeper_claude"
   ```

2. **explore_context_tree() - WRONG DATA**:
   ```
   explore_context_tree()
   ❌ Showed: 5 contexts (linkedin data!)
   ✅ Expected: 147 contexts (innkeeper_claude has 147!)
   ```

3. **get_last_handover() - WRONG DATA**:
   ```
   get_last_handover()
   ❌ Still showing: linkedin session (9ca91daa)
   ✅ Expected: innkeeper_claude session data
   ```

**Impact**:
🚨 **SEVERE** - Project isolation is completely broken! Users cannot reliably switch between projects. All tools continue querying the old project's schema despite reporting successful project switch.

**Root Cause Hypothesis**:

The likely issue is in how we manage the "active project" context. Possibilities:

1. **Session-level project storage bug**:
   - `select_project_for_session` updates the session record in PostgreSQL
   - But subsequent tool calls are not reading this updated project from the session
   - They're using cached or default project

2. **PostgreSQL adapter not switching schemas**:
   - Session has correct project name
   - But PostgreSQL adapter is not actually changing to the new schema
   - All queries still executing against old schema

3. **Middleware/Tool context mismatch**:
   - Middleware has correct project
   - Tools have stale project reference
   - Not syncing properly

**Investigation Steps**:

1. Check production logs for `select_project_for_session('innkeeper_claude')` call:
   - Did it actually UPDATE the session record?
   - What schema did it switch to?

2. Check production logs for `explore_context_tree()` call after switch:
   - What project context was it using?
   - What schema was it querying?
   - Was it reading the session's project field?

3. Review `_get_project_for_context()` implementation:
   - How does it determine which project to use?
   - Is it reading from session?
   - Is there caching?

4. Review PostgreSQL adapter schema switching:
   - Does it actually change schemas?
   - Is there a `SET search_path` command?
   - Are queries prefixed with schema name?

**Files to Investigate**:
- claude_mcp_hybrid_sessions.py:~2400 (select_project_for_session implementation)
- claude_mcp_hybrid_sessions.py:~400 (_get_project_for_context implementation)
- claude_mcp_hybrid_sessions.py:~2900 (explore_context_tree implementation)
- mcp_session_middleware.py (session management)
- postgres_adapter.py (schema switching)

---

## Additional Observations

### Test 5: context_dashboard() Still Failing
Despite deployment d98fca84 including MCP documentation fixes, context_dashboard() still returns "No approval received" error.

**Hypothesis**:
- Client-side cache in Claude.ai Desktop
- Need to restart Claude Desktop application
- Or actual deployment doesn't have the fixes (verify commit)

---

## Deployment Status

**Current Deployment**: d98fca84
**Status**: ACTIVE (deployed at 15:39:09 UTC)
**Branch**: feature/dem-30-persistent-sessions
**Commit**: 0241122 (breadcrumb integration + MCP docs)

**Expected Fixes**:
- ✅ Breadcrumb trail integration (all 10 tools)
- ✅ MCP documentation Args sections
- ❓ Context dashboard still failing (may need client restart)

---

## Next Steps

### Priority 1: Fix Project Isolation Bug (Bug #2) 🔥
This is CRITICAL and blocks all multi-project workflows.

1. Investigate production logs for the innkeeper_claude switch
2. Add debug logging to `_get_project_for_context()`
3. Add debug logging to schema selection in tools
4. Root cause the schema mismatch
5. Deploy fix
6. Re-test with systematic test plan

### Priority 2: Merge Project Selection Tools (Bug #1)
User experience issue - confusing to have two tools.

1. Design unified API: `select_project(name)` or `use_project(name)`
2. Handle both scenarios:
   - No session → Create session + select project
   - Existing session → Switch project (update session record)
3. Update documentation
4. Deploy
5. Re-test

### Priority 3: Resolve context_dashboard Approval Error
May just need client restart, but need to verify.

1. Confirm deployment d98fca84 has correct Args documentation
2. Ask user to restart Claude Desktop application
3. Re-test context_dashboard()
4. If still failing, investigate MCP schema validation

---

## Test Continuation Plan

Once bugs are fixed, resume systematic testing:

- [ ] Test 5: context_dashboard() (RETRY after client restart)
- [ ] Test 6: lock_context()
- [ ] Test 7: recall_context()
- [ ] Test 8: search_contexts()
- [ ] Test 9: query_database()
- [ ] Test 10: health_check_and_repair()

---

## References

- Previous session summary: BREADCRUMB_INTEGRATION_COMPLETE.md
- Screenshots: Multiple screenshots showing test results and errors
- Deployment logs: Deployment d98fca84 build and runtime logs

---

**Session End**: Running low on context tokens (62K remaining)
**Status**: Critical bugs documented, investigation plan created
**Next Session**: Focus on fixing project isolation bug (Bug #2)
