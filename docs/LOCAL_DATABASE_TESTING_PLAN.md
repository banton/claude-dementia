# Local Database Testing Plan

**Purpose**: Build and test all database-level cloud migration features locally using `claude_mcp_hybrid_sessions.py` before focusing on HTTP/MCP/SSE transport layer.

**Goal**: Maximize database capability development so later we only need to focus on authentication, authorization, and transport.

---

## ✅ Already Implemented and Tested

### 1. Session Creation with __PENDING__
- ✅ Sessions created on startup
- ✅ `project_name='__PENDING__'` sentinel value
- ✅ PostgreSQL persistence verified
- ✅ Session ID tracking working

**Test Results**: `docs/SESSION_FORK_TEST_RESULTS.md`

---

## 🔬 Database Features to Test (No HTTP Required)

All these features use **database only** - no HTTP, no MCP/SSE transport needed.

### 1. Project Selection Workflow

**Tool**: `select_project_for_session(project_name: str)`

**What to Test**:
- [x] Session starts with `project_name='__PENDING__'`
- [ ] Call `select_project_for_session('test_project')`
- [ ] Verify session updates in database
- [ ] Verify project context becomes active
- [ ] Verify handover loads for selected project
- [ ] Test selecting non-existent project (should offer to create)
- [ ] Test selecting existing project with previous handovers

**Database Operations**:
```sql
-- Before selection
SELECT project_name FROM mcp_sessions WHERE session_id = '...'
→ '__PENDING__'

-- After selection
SELECT project_name FROM mcp_sessions WHERE session_id = '...'
→ 'test_project'
```

**Why This Matters**: Foundation for multi-project isolation.

---

### 2. Session Handover System

**Tools**:
- `sleep(project: Optional[str] = None)` - Create handover on session end
- `wake_up(project: Optional[str] = None)` - Load handover on session start
- `get_last_handover(project: Optional[str] = None)` - Retrieve previous session

**What to Test**:
- [ ] Call `sleep()` after doing work
- [ ] Verify handover created in database
- [ ] Verify handover contains work summary
- [ ] Start new session, call `wake_up()`
- [ ] Verify handover loaded correctly
- [ ] Test `get_last_handover()` retrieves correct data
- [ ] Test project-specific handovers
- [ ] Test handover for non-existent project

**Database Operations**:
```sql
-- Check handover storage
SELECT session_id, project_name, session_summary
FROM mcp_sessions
WHERE project_name = 'test_project'
ORDER BY last_active DESC
LIMIT 1
```

**Why This Matters**: Enables continuity between sessions.

---

### 3. Multi-Project Context Isolation

**Tools**:
- `lock_context(content: str, topic: str, project: Optional[str] = None)`
- `recall_context(topic: str, project: Optional[str] = None)`
- `explore_context_tree(project: Optional[str] = None)`

**What to Test**:
- [ ] Create session, select project 'projectA'
- [ ] Lock contexts in 'projectA'
- [ ] Switch to 'projectB'
- [ ] Verify contexts from 'projectA' not visible
- [ ] Lock different contexts in 'projectB'
- [ ] Switch back to 'projectA'
- [ ] Verify 'projectA' contexts still exist
- [ ] Verify 'projectB' contexts not visible

**Database Verification**:
```python
# Check contexts are project-scoped
adapter = PostgreSQLAdapter()
with adapter.pool.getconn() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT label, project_name
            FROM context_locks
            WHERE project_name IN ('projectA', 'projectB')
        """)
        print(cur.fetchall())
```

**Why This Matters**: Prevents context leakage between projects.

---

### 4. Project Switching

**Tool**: `switch_project(name: str)`

**What to Test**:
- [ ] Start session with 'projectA'
- [ ] Lock some contexts
- [ ] Call `switch_project('projectB')`
- [ ] Verify session updated in database
- [ ] Verify context tree shows only 'projectB' contexts
- [ ] Verify handover loaded for 'projectB'
- [ ] Switch back to 'projectA'
- [ ] Verify contexts restored

**Database Operations**:
```sql
-- Check current project
SELECT project_name, last_active
FROM mcp_sessions
WHERE session_id = '...'

-- Check context distribution
SELECT project_name, COUNT(*) as context_count
FROM context_locks
GROUP BY project_name
```

**Why This Matters**: Enables working on multiple projects without session restart.

---

### 5. Project Creation

**Tool**: `create_project(name: str)`

**What to Test**:
- [ ] Create new project 'new_project'
- [ ] Verify project appears in project list
- [ ] Select the new project
- [ ] Lock contexts in new project
- [ ] Verify isolation from other projects

**Database Verification**:
```python
# List all projects with stats
adapter = PostgreSQLAdapter()
session_store = PostgreSQLSessionStore(adapter.pool)
projects = session_store.get_projects_with_stats()
print(projects)
```

**Why This Matters**: Users can create projects on-demand.

---

### 6. Context Operations Respect Project Boundaries

**Tools to Test**:
- `lock_context()` - Should use current session's project
- `unlock_context()` - Should only unlock in current project
- `search_contexts()` - Should search only current project
- `batch_lock_contexts()` - Should batch lock in current project
- `batch_recall_contexts()` - Should recall from current project

**What to Test**:
- [ ] Project 'A': Lock contexts 'api_spec', 'db_schema'
- [ ] Project 'B': Lock contexts 'api_spec', 'ui_design'
- [ ] In project 'A': `recall_context('api_spec')` → Returns A's version
- [ ] In project 'B': `recall_context('api_spec')` → Returns B's version
- [ ] In project 'A': `search_contexts('api')` → Only finds A's contexts
- [ ] In project 'B': `unlock_context('api_spec')` → Only unlocks B's version

**Why This Matters**: Ensures complete project isolation.

---

### 7. Session Cleanup and Expiry

**What to Test**:
- [ ] Create session with expiry time
- [ ] Verify session marked as expired after timeout
- [ ] Test cleanup script removes expired sessions
- [ ] Verify handovers preserved after session cleanup
- [ ] Test session restoration from expired session's handover

**Database Operations**:
```sql
-- Mark session as expired
UPDATE mcp_sessions
SET expires_at = NOW() - INTERVAL '1 hour'
WHERE session_id = '...'

-- Run cleanup (manually or via script)
-- Check session deleted but handover preserved
```

**Why This Matters**: Prevents database bloat, maintains continuity.

---

### 8. Session Summary Updates

**What to Test**:
- [ ] Session starts with empty `session_summary`
- [ ] Use tools (lock_context, recall_context, etc.)
- [ ] Call `sleep()` to create handover
- [ ] Verify `session_summary` updated with:
  - Work done
  - Tools used
  - Next steps
  - Important context

**Database Verification**:
```sql
SELECT session_summary
FROM mcp_sessions
WHERE session_id = '...'
```

**Why This Matters**: Provides context continuity between sessions.

---

## 🧪 Test Execution Plan

### Phase 1: Project Selection (2 hours)

**Test File**: `/tmp/test_project_selection.py`

1. Start session-aware fork
2. Call `select_project_for_session('test1')`
3. Verify database update
4. Lock test contexts
5. Create new session
6. Select 'test2'
7. Verify isolation

**Success Criteria**:
- ✅ Session project updated correctly
- ✅ Contexts scoped by project
- ✅ Project list shows stats

---

### Phase 2: Handover System (3 hours)

**Test File**: `/tmp/test_handovers.py`

1. Start session, select project
2. Lock contexts, use tools
3. Call `sleep()` to create handover
4. Verify handover in database
5. Start new session
6. Call `wake_up()`
7. Verify handover loaded
8. Test `get_last_handover()`

**Success Criteria**:
- ✅ Handover created with work summary
- ✅ Handover loaded on new session
- ✅ get_last_handover() returns correct data
- ✅ Project-specific handovers work

---

### Phase 3: Multi-Project Isolation (2 hours)

**Test File**: `/tmp/test_multi_project.py`

1. Create 3 projects (A, B, C)
2. In each: Lock different contexts
3. Verify contexts isolated by project
4. Switch between projects
5. Verify correct contexts visible
6. Search contexts in each project

**Success Criteria**:
- ✅ Contexts completely isolated
- ✅ No cross-project leakage
- ✅ Project switching works seamlessly
- ✅ Search respects project boundaries

---

### Phase 4: Project Switching (1 hour)

**Test File**: `/tmp/test_project_switching.py`

1. Start with project A
2. Lock contexts
3. Switch to project B
4. Verify context tree empty
5. Lock different contexts
6. Switch back to A
7. Verify contexts restored

**Success Criteria**:
- ✅ switch_project() updates session
- ✅ Context visibility changes
- ✅ Handovers load on switch
- ✅ No context loss

---

### Phase 5: Comprehensive Integration Test (3 hours)

**Test File**: `/tmp/test_cloud_db_features.py`

**Scenario**: Simulate real multi-project workflow

1. **Session 1 (Project: innkeeper)**
   - Create session
   - Select 'innkeeper' project
   - Lock 10 contexts (API specs, DB schemas, etc.)
   - Use tools (scan_project_files, query_files)
   - Create handover with `sleep()`

2. **Session 2 (Project: linkedin)**
   - New session
   - Select 'linkedin' project
   - Verify 'innkeeper' contexts not visible
   - Lock different contexts
   - Create handover

3. **Session 3 (Project: innkeeper - Resume)**
   - New session
   - Select 'innkeeper'
   - Call `wake_up()`
   - Verify handover loaded
   - Verify contexts still exist
   - Continue work

4. **Session 4 (Project Switching)**
   - Start with 'innkeeper'
   - Switch to 'linkedin' mid-session
   - Verify context change
   - Switch back
   - Verify restoration

**Success Criteria**:
- ✅ All projects work independently
- ✅ Handovers preserve state
- ✅ Context isolation maintained
- ✅ No database errors
- ✅ Performance acceptable

---

## 🎯 What This Achieves

### Before Transport Implementation

After completing these tests, we'll have validated:

1. **Session Management** ✅
   - Creation, persistence, expiry
   - Project selection workflow
   - Session cleanup

2. **Project Isolation** ✅
   - Multi-project support
   - Context scoping
   - Project switching

3. **Handover System** ✅
   - Creation on sleep
   - Loading on wake_up
   - Project-specific handovers

4. **Context Operations** ✅
   - lock/unlock/recall respect project
   - Search scoped to project
   - Batch operations work

5. **Database Schema** ✅
   - All tables working correctly
   - Indexes performing well
   - No schema issues

### After Transport Implementation

We'll only need to add:

1. **HTTP Layer**
   - FastAPI endpoints
   - Request/response handling
   - Error serialization

2. **MCP/SSE Transport**
   - WebSocket connections
   - Server-Sent Events
   - Protocol compliance

3. **Authentication/Authorization**
   - API key validation
   - Rate limiting
   - CORS headers

**All database logic will already be proven to work.**

---

## 🛠️ Test Tooling

### Automated Test Runner

Create `/tmp/run_all_db_tests.sh`:

```bash
#!/bin/bash
set -e

echo "=== Running Database Feature Tests ==="
echo ""

export DATABASE_URL="..."
export DEMENTIA_API_KEY="test_key"

echo "1. Testing project selection..."
python3 /tmp/test_project_selection.py

echo "2. Testing handover system..."
python3 /tmp/test_handovers.py

echo "3. Testing multi-project isolation..."
python3 /tmp/test_multi_project.py

echo "4. Testing project switching..."
python3 /tmp/test_project_switching.py

echo "5. Running integration test..."
python3 /tmp/test_cloud_db_features.py

echo ""
echo "=== All Tests Passed ==="
```

### Database Inspection Helper

Create `/tmp/inspect_db_state.py`:

```python
#!/usr/bin/env python3
"""
Quick database state inspector for debugging tests.
"""
import sys
sys.path.insert(0, '/Users/banton/Sites/claude-dementia')

from postgres_adapter import PostgreSQLAdapter
from mcp_session_store import PostgreSQLSessionStore

adapter = PostgreSQLAdapter()
session_store = PostgreSQLSessionStore(adapter.pool)

print("=== Current Database State ===\n")

# List sessions
with adapter.pool.getconn() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT session_id, project_name, created_at, last_active
            FROM mcp_sessions
            ORDER BY last_active DESC
            LIMIT 10
        """)
        print("Recent Sessions:")
        for row in cur.fetchall():
            print(f"  {row['session_id'][:16]}... | {row['project_name']:15} | {row['last_active']}")

        print()

        # List contexts by project
        cur.execute("""
            SELECT project_name, label, version, created_at
            FROM context_locks
            ORDER BY project_name, created_at DESC
        """)
        print("Context Locks by Project:")
        current_project = None
        for row in cur.fetchall():
            if row['project_name'] != current_project:
                print(f"\n  Project: {row['project_name']}")
                current_project = row['project_name']
            print(f"    - {row['label']} v{row['version']}")

adapter.close()
```

---

## 📊 Success Metrics

### Test Coverage
- [ ] 100% of database-level tools tested
- [ ] All project isolation scenarios verified
- [ ] All handover workflows validated

### Performance
- [ ] Project selection < 100ms
- [ ] Context operations < 50ms
- [ ] Handover creation < 200ms
- [ ] Database queries optimized

### Reliability
- [ ] Zero context leakage between projects
- [ ] No orphaned data
- [ ] Cleanup works correctly
- [ ] Concurrent session handling

---

## 🎬 Getting Started

### Step 1: Verify Session Fork Works

```bash
export DATABASE_URL="postgresql://..."
export DEMENTIA_API_KEY="test_key"
python3 claude_mcp_hybrid_sessions.py
```

Expected: Session created with `__PENDING__` project.

### Step 2: Run First Test

```bash
python3 /tmp/test_project_selection.py
```

Expected: All tests pass, session project updated.

### Step 3: Continue Through Phases

Work through Phases 1-5 systematically, documenting results.

---

## 📝 Documentation

After testing, create:
- `docs/DATABASE_FEATURE_TEST_RESULTS.md` - Test outcomes
- `docs/CLOUD_MIGRATION_READINESS.md` - What's ready for transport layer
- `docs/KNOWN_ISSUES.md` - Any problems found

---

## ✅ Next Steps

1. **Immediate**: Start Phase 1 (Project Selection)
2. **This Week**: Complete Phases 1-3
3. **Next Week**: Complete Phases 4-5
4. **After Testing**: Begin HTTP/transport layer implementation

**Ready to start testing?**
