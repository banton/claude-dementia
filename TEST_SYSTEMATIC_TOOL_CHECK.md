# Systematic Tool Test for Deployment 026b125d

## Deployment Info
- **Deployment ID**: 026b125d
- **Fix**: get_current_session_id() now checks config._current_session_id first
- **Expected**: ALL tools use same MCP session ID from middleware

---

## Test Instructions

Copy and paste this into Claude.ai Desktop (in a fresh conversation):

---

**SYSTEMATIC TOOL TEST**

Please test the Dementia MCP tools in the exact sequence below. After each tool call, record whether it succeeded or failed. Stop after 3 broken tools and provide a final report.

**Test Sequence:**

**Phase 1: Project Selection (Required First)**

1. **list_projects()**
   - Record: Success/Failure
   - Expected: Returns list of available projects
   - If fails: STOP and report

2. **select_project_for_session('linkedin')**
   - Record: Success/Failure
   - Expected: Returns success message
   - If fails: STOP and report

**Phase 2: Core Memory Tools**

3. **get_last_handover()**
   - Record: Success/Failure
   - Expected: Returns handover data (or "no previous session")
   - Should NOT get "Pending session" error
   - Should complete in <10 seconds

4. **explore_context_tree()**
   - Record: Success/Failure
   - Expected: Returns tree of locked contexts
   - Should NOT get "Pending session" error

5. **context_dashboard()**
   - Record: Success/Failure
   - Expected: Returns dashboard with statistics
   - Should NOT get "Pending session" error

**Phase 3: Context Operations**

6. **lock_context(content="Test context for systematic check", topic="test_systematic")**
   - Record: Success/Failure
   - Expected: Returns confirmation with version number

7. **recall_context(topic="test_systematic", preview_only=True)**
   - Record: Success/Failure
   - Expected: Returns preview of just-locked context

8. **search_contexts(query="test")**
   - Record: Success/Failure
   - Expected: Returns search results including test_systematic

**Phase 4: Database Tools**

9. **query_database(query="SELECT COUNT(*) as count FROM context_locks")**
   - Record: Success/Failure
   - Expected: Returns count of locked contexts

10. **health_check_and_repair()**
    - Record: Success/Failure
    - Expected: Returns health status

**Stopping Condition:**
- If 3 tools fail, STOP testing and provide report immediately
- Do NOT continue testing after 3 failures

**Final Report Format:**

After testing is complete (or after 3 failures), provide this report:

```
=== SYSTEMATIC TOOL TEST REPORT ===

Deployment: 026b125d
Test Date: [timestamp]
Total Tools Tested: [number]

RESULTS:
✅ Passed: [count]
❌ Failed: [count]

PHASE 1 - Project Selection:
1. list_projects: [✅/❌] [details]
2. select_project_for_session: [✅/❌] [details]

PHASE 2 - Core Memory Tools:
3. get_last_handover: [✅/❌] [details]
4. explore_context_tree: [✅/❌] [details]
5. context_dashboard: [✅/❌] [details]

PHASE 3 - Context Operations:
6. lock_context: [✅/❌] [details]
7. recall_context: [✅/❌] [details]
8. search_contexts: [✅/❌] [details]

PHASE 4 - Database Tools:
9. query_database: [✅/❌] [details]
10. health_check_and_repair: [✅/❌] [details]

CRITICAL OBSERVATIONS:
- Session consistency: [Did all tools use same session ID?]
- Response times: [Any tools >10 seconds?]
- Error patterns: [Any recurring error messages?]

VERDICT:
[PASS/FAIL - System ready for production]

RECOMMENDATION:
[What should happen next]
```

**Important Notes:**
- Test in a FRESH Claude.ai Desktop conversation
- Do NOT retry failed tools (record failure and move on)
- Stop immediately after 3 failures
- Provide the final report even if testing stops early

---

## Expected Results (If Fix Works)

All 10 tools should **PASS** with these characteristics:

1. **list_projects**: Returns project list ✅
2. **select_project_for_session**: Success message ✅
3. **get_last_handover**: Returns data, completes quickly ✅
4. **explore_context_tree**: Returns tree, no blocking ✅
5. **context_dashboard**: Returns dashboard ✅
6. **lock_context**: Creates context successfully ✅
7. **recall_context**: Returns preview ✅
8. **search_contexts**: Returns results ✅
9. **query_database**: Returns count ✅
10. **health_check_and_repair**: Returns health status ✅

**All tools should**:
- Use same session ID (visible in logs)
- NOT get "Pending session" errors
- Complete in reasonable time (<10 seconds each)

## Expected Results (If Fix Doesn't Work)

**Failure Pattern Would Be**:
1. **list_projects**: ✅ PASS (whitelisted)
2. **select_project_for_session**: ✅ PASS (whitelisted)
3. **get_last_handover**: ❌ FAIL ("Pending session" or timeout)
4. **explore_context_tree**: ❌ FAIL ("Pending session" or timeout)
5. **context_dashboard**: ❌ FAIL ("Pending session" or timeout)

Testing would STOP after tool #5 (3 failures reached).

## How to Verify Session Consistency (For Developer)

While user is testing, check production logs:

```bash
# Watch for session IDs in logs
doctl apps logs 20c874aa-0ed2-44e3-a433-699f17d88a44 --type run --tail 50 | grep -E "session|Session"
```

**Success Pattern** (all same session):
```
21:XX:XX - MCP session created: abc12345
21:XX:XX - list_projects using session: abc12345 ✅
21:XX:XX - select_project_for_session using session: abc12345 ✅
21:XX:XX - get_last_handover using session: abc12345 ✅
21:XX:XX - explore_context_tree using session: abc12345 ✅
```

**Failure Pattern** (different sessions):
```
21:XX:XX - MCP session created: abc12345
21:XX:XX - list_projects using session: abc12345
21:XX:XX - select_project_for_session using session: abc12345
21:XX:XX - get_last_handover created session: def67890 ❌ DIFFERENT!
```

---

## After Testing

**If All Tests Pass**:
- Bug #7 is FULLY FIXED ✅
- System is production-ready ✅
- Can merge to main and tag release ✅

**If Tests Fail**:
- Investigate which tools failed
- Check production logs for session ID patterns
- Identify if more tools need explicit session ID handling
- Deploy another fix iteration

---

**Test Prompt Created**: 2025-11-15 21:05 UTC
**For Deployment**: 026b125d (DEPLOYING)
**Purpose**: Verify REAL Bug #7 fix (get_current_session_id middleware integration)
