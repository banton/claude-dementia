# Missing Database Features for Cloud Migration

**Date**: 2025-11-07
**Status**: Gap Analysis

---

## ✅ What's Already Built

### 1. Session Management
- ✅ Session creation with `__PENDING__` sentinel
- ✅ PostgreSQL session storage
- ✅ Session expiry and cleanup
- ✅ Session summary tracking

### 2. Project Tools
- ✅ `select_project_for_session(project_name)` - Select project
- ✅ `switch_project(name)` - Switch active project
- ✅ `create_project(name)` - Create new project
- ✅ Project validation (checks if project exists)

### 3. Handover System
- ✅ `sleep(project)` - Create handover on session end
- ✅ `wake_up(project)` - Load handover on session start
- ✅ `get_last_handover(project)` - Retrieve previous session
- ✅ Project-specific handovers

### 4. Context Operations
- ✅ `lock_context(content, topic, project)` - Lock with project
- ✅ `recall_context(topic, project)` - Recall from project
- ✅ All context tools accept `project` parameter

### 5. Database Schema
- ✅ `mcp_sessions` table with `project_name` column
- ✅ `project_name` defaults to `'default'` (not `'__PENDING__'`!)
- ✅ `session_summary` JSONB column
- ✅ All migrations applied

---

## ❌ What's NOT Built Yet

### 1. **CRITICAL: Tool Project Validation**

**Problem**: Tools don't check if session project is `__PENDING__` before executing.

**What happens now:**
```python
# Session created with project_name='__PENDING__'
# User calls lock_context() WITHOUT selecting project first
lock_context("API spec", "api_v1")
# → Tool tries to execute with project='__PENDING__'
# → May fail or create data in wrong project
```

**What SHOULD happen:**
```python
lock_context("API spec", "api_v1")
# → Tool checks session's project_name
# → If '__PENDING__': Returns error with project list
# → User must call select_project_for_session() first
```

**Where to add:**
Every tool that uses `_get_project_for_context()` should validate:

```python
async def lock_context(...):
    """Lock context..."""

    # NEW: Check if project selection pending
    session_id = getattr(config, '_current_session_id', None)
    if session_id:
        adapter = _get_db_adapter()
        session_store = PostgreSQLSessionStore(adapter.pool)
        session = session_store.get_session(session_id)

        if session and session.get('project_name') == '__PENDING__':
            # Get available projects
            projects = session_store.get_projects_with_stats()

            return json.dumps({
                "error": "PROJECT_SELECTION_REQUIRED",
                "message": "Please select a project before using tools",
                "available_projects": [p['project_name'] for p in projects],
                "instruction": "Call select_project_for_session('project_name') first"
            }, indent=2)

    # ... rest of lock_context implementation
```

**Affected Tools** (need validation added):
- `lock_context`
- `unlock_context`
- `recall_context`
- `search_contexts`
- `explore_context_tree`
- `wake_up`
- `sleep`
- `get_last_handover`
- `scan_project_files`
- `query_files`
- All other tools that use project context

**Estimated Work**: 2-3 hours to add to all tools

---

### 2. **Default `project_name` Mismatch**

**Problem**: Database schema defaults to `'default'` instead of `'__PENDING__'`

**Current schema:**
```sql
project_name TEXT DEFAULT 'default'
```

**Should be:**
```sql
project_name TEXT DEFAULT '__PENDING__'
```

**Impact**:
- New sessions created via HTTP/cloud won't have `__PENDING__` unless explicitly set
- Session-aware fork manually sets it in code, but cloud version doesn't

**Where to fix:**
- `postgres_adapter.py` - Migration that creates `mcp_sessions` table
- `mcp_session_middleware.py` - Ensure `create_session()` uses `'__PENDING__'`

**Estimated Work**: 30 minutes

---

### 3. **Project Statistics Helper Not Verified**

**Problem**: Not sure if `get_projects_with_stats()` is fully implemented

**What it should do:**
```python
session_store.get_projects_with_stats()
# Returns:
[
    {
        "project_name": "innkeeper",
        "context_locks": 124,
        "last_used": "2025-11-05 10:30:00",
        "last_used_ago": "2 days ago"
    },
    {
        "project_name": "linkedin",
        "context_locks": 4,
        "last_used": "2025-11-07 06:15:00",
        "last_used_ago": "4 hours ago"
    }
]
```

**Need to verify:**
- Does method exist in `PostgreSQLSessionStore`?
- Does it return correct stats?
- Does it handle empty projects?

**Estimated Work**: 1 hour to verify/implement

---

### 4. **Automated Test Suite**

**Problem**: No automated tests for database features

**What's needed:**
- Unit tests for project selection workflow
- Integration tests for multi-project isolation
- Tests for handover system
- Tests for context scoping by project
- Performance tests for database queries

**Files to create:**
- `/tmp/test_project_selection.py` ✅ (Created but basic)
- `/tmp/test_handovers.py` ❌ (Not created)
- `/tmp/test_multi_project.py` ❌ (Not created)
- `/tmp/test_project_switching.py` ❌ (Not created)
- `/tmp/test_cloud_db_features.py` ❌ (Not created - comprehensive)

**Estimated Work**: 8-10 hours for comprehensive test suite

---

### 5. **Session Cleanup Doesn't Preserve Handovers**

**Problem**: When sessions are cleaned up, handovers might be lost

**What should happen:**
```python
# Session expires after 120 minutes
# Cleanup runs
# Session deleted from mcp_sessions
# BUT: Handover should be preserved in session_summary or separate table
```

**Need to verify:**
- Are handovers stored separately from sessions?
- Does cleanup preserve handovers?
- Can new session load handover from deleted session?

**Estimated Work**: 2 hours to verify/implement

---

### 6. **Middleware Project Checking (HTTP Only)**

**Status**: NOT NEEDED FOR LOCAL TESTING

This is HTTP/cloud layer, not database:
- `mcp_session_middleware.py` intercepts tool calls
- Checks session's `project_name`
- Returns 400 error if `__PENDING__`

**For local testing**: Tools check themselves (see #1)

**For cloud deployment**: Middleware handles it

---

## 🎯 Priority Order

### Phase 1: Critical (Must Have) - 4 hours

1. **Add tool project validation** (2-3 hours)
   - Add `__PENDING__` check to all tools
   - Return helpful error with project list
   - Prevent tools from executing without project

2. **Fix default `project_name`** (30 min)
   - Update migration to default to `'__PENDING__'`
   - Update session creation to use `'__PENDING__'`

3. **Verify `get_projects_with_stats()`** (1 hour)
   - Test it returns correct data
   - Add tests for edge cases

### Phase 2: Important (Should Have) - 10 hours

4. **Create automated test suite** (8-10 hours)
   - Comprehensive database feature tests
   - Multi-project isolation tests
   - Handover system tests
   - Performance benchmarks

5. **Verify handover preservation** (2 hours)
   - Ensure handovers survive cleanup
   - Test continuity after session expiry

### Phase 3: Nice to Have (Later)

6. **Middleware project checking** (After HTTP layer exists)
7. **Optimize database queries** (After performance testing)
8. **Add monitoring/metrics** (After deployment)

---

## 📊 Summary

### Database Features Status

| Feature | Built? | Tested? | Priority |
|---------|--------|---------|----------|
| Session with `__PENDING__` | ✅ Yes | ✅ Yes | - |
| Project selection tool | ✅ Yes | ⚠️  Basic | HIGH |
| Handover system | ✅ Yes | ❌ No | HIGH |
| Multi-project isolation | ✅ Yes | ❌ No | CRITICAL |
| **Tool validation** | **❌ No** | **❌ No** | **CRITICAL** |
| Project statistics | ⚠️  Unknown | ❌ No | HIGH |
| Automated tests | ❌ No | ❌ No | HIGH |
| Handover preservation | ⚠️  Unknown | ❌ No | MEDIUM |

### Readiness for Cloud Migration

**Database Layer**: 70% complete
- ✅ Core functionality exists
- ❌ Validation layer missing
- ❌ Testing incomplete

**Transport Layer**: 0% complete (HTTP/MCP/SSE)

**Auth Layer**: 0% complete (API keys/rate limiting)

---

## 🚀 Recommendation

**Start with Phase 1 (Critical)** - 4 hours

This will give us:
1. **Fully validated database layer** - Tools prevent invalid state
2. **Correct default behavior** - New sessions require project selection
3. **Verified project stats** - Project list works correctly

After Phase 1:
- **All database features work correctly**
- **Ready for comprehensive testing (Phase 2)**
- **Then add HTTP/transport layer with confidence**

**Would you like to start with Phase 1?**
