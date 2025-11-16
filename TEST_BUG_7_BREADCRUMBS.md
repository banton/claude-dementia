# Test Prompt for Bug #7 Investigation (Deployment 05fdb48b)

## Deployment Info
- **Deployment ID**: 05fdb48b
- **Status**: ACTIVE (since 20:08 UTC)
- **Purpose**: Trace UPDATE statement execution with STEP 4d-4h breadcrumbs

## Test Instructions

Copy and paste this into Claude.ai Desktop:

---

Please test the `select_project_for_session()` function by running:

```
select_project_for_session("linkedin")
```

I need to see if the UPDATE statement is executing correctly. The system should now have additional logging.

---

## Expected Breadcrumb Flow

If the UPDATE is working correctly, production logs should show:

```
🔵 STEP 4: select_project_for_session ENTERED with project_name='linkedin'
🔵 STEP 4a: Got session_id from config: xxxxxxxx
🔵 STEP 4b: Sanitized project name: 'linkedin' → 'linkedin'
🔵 STEP 4c: Got database adapter and session store
🔵 STEP 4d: About to UPDATE mcp_sessions for session xxxxxxxx, project: 'linkedin'
🔵 STEP 4e: Executing UPDATE statement...
🔵 STEP 4f: UPDATE executed, rowcount=1, committing...
🔵 STEP 4g: Commit completed successfully
🔵 STEP 4h: Setting _active_projects[xxxxxxxx] = 'linkedin'
🔵 STEP 5: Handover loaded (or failed, not critical)
🔵 STEP 6: Response received from FastMCP, status: 200
```

## What to Look For

### Scenario 1: Early Return (Code Never Reaches UPDATE)
**Symptoms**: See STEP 4c but NOT 4d
**Meaning**: Code returns early before UPDATE, some condition blocks execution

### Scenario 2: UPDATE Execution Fails
**Symptoms**: See STEP 4d-4e but NOT 4f
**Meaning**: The `cur.execute()` call is failing (SQL error, connection issue, etc.)

### Scenario 3: No Rows Updated (Wrong session_id?)
**Symptoms**: See STEP 4f with `rowcount=0`
**Meaning**: UPDATE executes but WHERE clause doesn't match any rows
**Action**: Check if session_id is correct

### Scenario 4: Commit Fails
**Symptoms**: See STEP 4f with `rowcount=1` but NOT 4g
**Meaning**: UPDATE succeeds but commit fails

### Scenario 5: Everything Works (But Still Broken)
**Symptoms**: See all STEP 4d-4h successfully
**Meaning**: UPDATE is executing and committing, problem is elsewhere
**Action**: Check if middleware is querying different database/table

## After Running Test

After you test `select_project_for_session("linkedin")`:

1. **Try a follow-up tool** to see if it still blocks:
   ```
   get_last_handover()
   ```
   or
   ```
   explore_context_tree()
   ```

2. **Report which STEP breadcrumbs you see** - This will tell us exactly where the UPDATE flow is breaking.

## Success Criteria

The bug is FIXED when:
- ✅ All STEP 4d-4h breadcrumbs appear in logs
- ✅ STEP 4f shows `rowcount=1`
- ✅ `get_last_handover()` succeeds (no longer blocked)
- ✅ Database shows `project_name = 'linkedin'` (not `__PENDING__`)

---

**Investigation**: Bug #7 - Session project_name Not Persisting
**Method**: Incremental breadcrumb logging to trace UPDATE execution
**Deployment**: 05fdb48b (ACTIVE since 20:08 UTC)
