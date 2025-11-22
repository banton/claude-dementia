# Bug #1: Project Selection Tool Confusion

**Date Discovered**: 2025-11-16
**Session**: Systematic MCP testing with Claude.ai Desktop
**Priority**: HIGH (User Experience Issue)
**Status**: DOCUMENTED, NOT YET FIXED

---

## Summary

Two separate tools perform overlapping project selection functions, causing user confusion and workflow friction. Users must know which tool to use based on whether they have an active session or not.

---

## Current State: Two Tools

### Tool 1: `switch_project(name)`
**Purpose**: Switch projects mid-session (requires existing active session)

**Behavior**:
- Requires active session to exist
- Fails with "No active session - session store not initialized" if no session exists
- Updates existing session's project field

**Use Case**: User already working in one project, wants to switch to another

### Tool 2: `select_project_for_session(project_name)`
**Purpose**: Select initial project for session

**Behavior**:
- Can create new session if needed
- Can also switch projects on existing sessions
- More flexible, works in both scenarios

**Use Case**: Initial project selection OR switching projects

---

## The Problem

**User Confusion**: Users don't know which tool to use

**Failure Scenario** (from testing):
```
1. User starts work on linkedin project
2. User attempts: switch_project('innkeeper_claude')
3. ❌ Error: "No active session - session store not initialized"
4. User confused: "But I just selected linkedin project!"
5. User tries: select_project_for_session('innkeeper_claude')
6. ✅ Success: Project switched to innkeeper_claude
```

**Root Cause**: The names imply different functions, but users expect one unified interface:
- "switch_project" sounds like it should work anytime
- "select_project_for_session" sounds like initial selection only
- In reality, select_project_for_session works for both cases!

---

## User Feedback (Direct Quote)

> "The switch project and select project for session should be merged to do both scenarios"

---

## Proposed Solution

### Merge Into Single Intelligent Tool: `select_project(name)`

**Name Options** (in order of preference):
1. `select_project(name)` - Clear, simple, covers both use cases
2. `use_project(name)` - Natural language feel
3. `set_project(name)` - More technical
4. Keep `select_project_for_session(name)` - Already works for both

**Recommended**: `select_project(name)` (shortest, clearest)

**Behavior**:
```python
@server.call_tool()
async def select_project(arguments: dict) -> Sequence[TextContent]:
    """
    Select the active project for this session.

    Works in two scenarios:
    - No active session: Creates session and selects project
    - Existing session: Switches project for current session

    Args:
        name: Project name to select/switch to

    Returns:
        JSON with project info and session details
    """
    project_name = arguments.get("name")

    # Get or create session
    session_id = get_current_session_id()
    if not session_id:
        # No session - create one
        session_id = await create_session()

    # Switch project (works for both new and existing sessions)
    await update_session_project(session_id, project_name)

    return success_response(
        message=f"Selected project: {project_name}",
        session_id=session_id,
        project=project_name
    )
```

**Deprecation Plan**:
1. Create unified `select_project()` tool
2. Mark `switch_project()` as DEPRECATED with helpful message:
   ```
   "⚠️ This tool is deprecated. Use select_project() instead."
   ```
3. Keep `select_project_for_session()` as alias (for backward compatibility)
4. Update all documentation to use `select_project()`
5. After 1 month, remove deprecated tools

---

## Implementation Files

### Current Implementation (to be refactored)

**File**: `claude_mcp_hybrid_sessions.py`

**Lines to investigate**:
- `switch_project()` definition - Line ~2300
- `select_project_for_session()` definition - Line ~2400

**Related functions**:
- `get_current_session_id()` - Session detection
- `create_session()` - Session creation
- `update_session_project()` - Project switching logic
- `_get_db_adapter()` - Schema switching

---

## Testing Plan

After implementing the fix, test these scenarios:

### Test 1: Fresh Start (No Session)
```
1. Fresh MCP connection (no prior session)
2. Call: select_project('test_alpha')
3. Expected: ✅ Session created, project selected
4. Call: list_projects()
5. Expected: ✅ test_alpha shows as active
```

### Test 2: Mid-Session Switch
```
1. Working session on 'linkedin' project
2. Call: select_project('innkeeper_claude')
3. Expected: ✅ Project switched to innkeeper_claude
4. Call: explore_context_tree()
5. Expected: ✅ Shows innkeeper_claude contexts (147)
```

### Test 3: Multiple Switches
```
1. select_project('alpha')
2. lock_context(topic="alpha_test", content="Alpha data")
3. select_project('beta')
4. lock_context(topic="beta_test", content="Beta data")
5. select_project('alpha')
6. recall_context('alpha_test')
7. Expected: ✅ Returns "Alpha data" (not beta_test)
```

### Test 4: Error Handling
```
1. select_project('nonexistent_project')
2. Expected: ✅ Clear error: "Project 'nonexistent_project' does not exist"
3. Suggestion: "Use list_projects() to see available projects"
```

---

## Impact Assessment

**Severity**: MEDIUM
- Not a functional bug (workaround exists)
- But significant UX friction
- Confuses new users
- Requires documentation to explain two tools

**User Impact**: HIGH
- Every user encounters this confusion
- Slows down workflow
- Requires trial-and-error to discover correct tool

**Fix Complexity**: LOW
- Merge existing logic into one tool
- Add deprecation warnings
- Update documentation
- Simple refactoring, no architectural changes

**Risk**: VERY LOW
- select_project_for_session() already works for both cases
- Just renaming and adding deprecation warnings
- No changes to underlying session/project logic

---

## Success Criteria

After implementing the fix:

1. ✅ Single tool `select_project()` works in all scenarios
2. ✅ Deprecated tools show clear migration message
3. ✅ All 4 test scenarios pass
4. ✅ Documentation updated (README.md, CLAUDE.md, tool descriptions)
5. ✅ No regression in existing project switching functionality
6. ✅ User doesn't need to know about sessions to switch projects

---

## Related Bugs

**Bug #2**: PROJECT ISOLATION FAILURE (CRITICAL)
- Affects project switching after select_project_for_session() is called
- Must be fixed BEFORE Bug #1 (otherwise merged tool won't work correctly)
- Status: ✅ FIXED in deployment 171b1068 (commit 7f4cf92)

**Bug #2 Extended**: search_contexts() session filter
- Same root cause as Bug #2
- Status: ✅ FIXED in deployment cacebdd3 (commit 68725b3)

---

## Timeline

**Discovery**: 2025-11-16 (during systematic testing)
**Documentation**: 2025-11-16 (this file)
**Target Fix**: After Bug #2 verification complete
**Estimated Effort**: 1-2 hours (simple refactoring)

---

## References

- **CRITICAL_BUGS_TESTING_SESSION.md** - Original bug discovery and user feedback
- **claude_mcp_hybrid_sessions.py** - Implementation file
- **mcp_session_store.py** - Session management
- **TESTING_PROMPT.md** - Comprehensive test suite

---

## Notes

**Why Not Fixed Yet**:
- Bug #2 (PROJECT ISOLATION FAILURE) is CRITICAL and must be fixed first
- Bug #1 is a UX issue, not a functionality blocker
- Workaround exists (use select_project_for_session)

**User Workaround Until Fixed**:
```
Always use: select_project_for_session(project_name)
Never use: switch_project(project_name)

select_project_for_session() works in all scenarios:
- ✅ First project selection (creates session)
- ✅ Switching projects mid-session
```

---

**Next Steps**:
1. Verify Bug #2 Extended Fix is working (multi-project testing)
2. Implement unified `select_project()` tool
3. Add deprecation warnings to old tools
4. Update documentation
5. Deploy and test
6. Monitor user feedback

---

**Status**: 📋 DOCUMENTED, READY FOR IMPLEMENTATION
