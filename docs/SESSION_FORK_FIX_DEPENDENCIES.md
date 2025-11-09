# Session Fork Fix - Task Dependencies

**Date**: 2025-11-08
**Related**: SESSION_FORK_CRITICAL_ISSUES.md

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Code Cleanup (No Dependencies)                    │
└─────────────────────────────────────────────────────────────┘
    │
    ├─► [1] Remove dead SQLite code (600+ lines)
    │   ├─ No dependencies
    │   ├─ Benefits: Reduces file from 303KB to ~50KB
    │   └─ Makes code readable for remaining fixes
    │

┌─────────────────────────────────────────────────────────────┐
│ Phase 2: Import-Time Fixes (Must Complete Before Testing)  │
└─────────────────────────────────────────────────────────────┘
    │
    ├─► [2] Move AutoClosingPostgreSQLConnection class
    │   ├─ No dependencies
    │   ├─ Fixes: Issue #14 (NameError on import)
    │   ├─ Unblocks: [13] Module import test
    │   └─ CRITICAL: Module won't import without this
    │
    └─► [13] Test module import
        ├─ Depends on: [2]
        └─ Validates: Can import claude_mcp_hybrid_sessions

┌─────────────────────────────────────────────────────────────┐
│ Phase 3: Critical Runtime Fixes (Sequential Order)         │
└─────────────────────────────────────────────────────────────┘
    │
    ├─► [3] Fix get_current_session_id() → _get_local_session_id()
    │   ├─ Depends on: [2] (module must import)
    │   ├─ Fixes: Issue #8 (undefined function)
    │   ├─ Unblocks: [4], [6], [7]
    │   └─ Impact: Enables session-aware project selection
    │
    ├─► [4] Add connection cleanup in _get_project_for_context()
    │   ├─ Depends on: [3] (function must work)
    │   ├─ Fixes: Issue #3 (connection leak)
    │   ├─ Unblocks: [15] (connection pool test)
    │   └─ Impact: Prevents pool exhaustion
    │
    ├─► [5] Add commit/rollback to __exit__()
    │   ├─ Depends on: [2] (class must be defined)
    │   ├─ Fixes: Issue #12 (no transaction management)
    │   ├─ Conflicts with: [10] (both modify same code)
    │   ├─ Unblocks: [16] (transaction test)
    │   └─ Impact: Ensures data persistence
    │
    └─► [10] Remove automatic rollback from execute()
        ├─ Depends on: [5] (transaction management must exist first)
        ├─ Fixes: Issue #5 (automatic rollback breaks multi-statement)
        ├─ Conflicts with: [5] (coordinate changes)
        └─ Impact: Allows multi-statement transactions

┌─────────────────────────────────────────────────────────────┐
│ Phase 4: Session Management                                │
└─────────────────────────────────────────────────────────────┘
    │
    ├─► [11] Verify config supports _current_session_id
    │   ├─ No dependencies (read-only check)
    │   ├─ Informs: [6] (may need to modify approach)
    │   └─ Action: Read src/config.py
    │
    ├─► [6] Find and call _init_local_session()
    │   ├─ Depends on: [3] (session functions must work)
    │   ├─- Depends on: [11] (config must support attribute)
    │   ├─ Fixes: Issue #1 (session never initialized)
    │   ├─ Unblocks: [14] (session init test)
    │   └─ Research needed: FastMCP startup hooks
    │
    └─► [12] Remove or integrate _update_session_activity()
        ├─ Depends on: [6] (understand session lifecycle first)
        ├─ Decision: Remove if not needed, or call from middleware
        └─ Low priority: Doesn't break functionality

┌─────────────────────────────────────────────────────────────┐
│ Phase 5: Data Safety                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ├─► [7] Add project validation in _check_project_selection_required()
    │   ├─ Depends on: [3] (project lookup must work)
    │   ├─ Fixes: Issue #4 (validation bypass)
    │   ├─ Unblocks: [17] (project validation test)
    │   └─ Impact: Prevents accidental schema creation
    │
    ├─► [8] Add HTTP mode detection
    │   ├─ No dependencies
    │   ├─ Fixes: Issue #10 (global state in cloud)
    │   ├─ Unblocks: [18] (HTTP mode test)
    │   └─ Location: Top of file or _init_local_session()
    │
    └─► [9] Fix exception handling in _get_cached_adapter()
        ├─ No dependencies
        ├─ Fixes: Issue #2 (silent exception swallowing)
        └─ Impact: Prevents broken adapter caching

┌─────────────────────────────────────────────────────────────┐
│ Phase 6: Testing (All Fixes Must Be Complete)              │
└─────────────────────────────────────────────────────────────┘
    │
    ├─► [13] Test module import
    │   └─ Depends on: [2]
    │
    ├─► [14] Test session initialization
    │   └─ Depends on: [6], [11]
    │
    ├─► [15] Test connection pool resilience (20+ calls)
    │   └─ Depends on: [4]
    │
    ├─► [16] Test transaction commit behavior
    │   └─ Depends on: [5], [10]
    │
    ├─► [17] Test project validation
    │   └─ Depends on: [7]
    │
    ├─► [18] Test HTTP mode blocked
    │   └─ Depends on: [8]
    │
    └─► [19] Create comprehensive test suite
        └─ Depends on: [13-18] (all individual tests)

┌─────────────────────────────────────────────────────────────┐
│ Phase 7: Documentation                                     │
└─────────────────────────────────────────────────────────────┘
    │
    └─► [20] Document all fixes
        └─ Depends on: ALL previous tasks
```

---

## Critical Path

**Shortest path to working system**:

```
[1] → [2] → [13] → [3] → [4] → [5] → [10] → [11] → [6] → [14]
 │     │      │      │      │      │      │      │      │      │
 │     │      │      │      │      │      │      │      │      └─ Session works
 │     │      │      │      │      │      │      │      └─ Session initialized
 │     │      │      │      │      │      │      └─ Config verified
 │     │      │      │      │      │      └─ Transactions work
 │     │      │      │      │      └─ Data persists
 │     │      │      │      └─ Pool doesn't exhaust
 │     │      │      └─ Project selection works
 │     │      └─ Module imports
 │     └─ Class defined before use
 └─ Code readable
```

**Estimated time**: 2-3 hours for critical path

---

## Task Conflict Matrix

| Task | Conflicts With | Resolution |
|------|---------------|------------|
| [5] Commit/rollback in __exit__() | [10] Remove rollback from execute() | Do [5] first, then [10] |
| [6] Init session | [11] Config verification | Check [11] before implementing [6] |

---

## Parallel Work Opportunities

Tasks that can be done **simultaneously** (no dependencies):

**Group A - Independent Code Changes**:
- [1] Remove SQLite code
- [8] HTTP mode detection
- [9] Fix _get_cached_adapter() exception handling
- [11] Check config.py (read-only)

**Group B - After Module Imports** (all depend on [2]):
- [3] Fix get_current_session_id()
- [7] Add project validation
- [12] Remove _update_session_activity()

**Group C - Testing** (after all fixes):
- [13-19] Can be done in any order

---

## Pre-Flight Checklist

Before starting fixes, verify:

- [ ] Git branch created: `feature/dem-30-fix-session-fork`
- [ ] Backup made: `cp claude_mcp_hybrid_sessions.py claude_mcp_hybrid_sessions.py.backup`
- [ ] File readable: Check file size after [1] removes dead code
- [ ] Tests exist: Create failing tests first (TDD)

---

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| Phase 1 | Delete too much code | Diff before commit, git history backup |
| Phase 2 | Break other imports | Test import after each change |
| Phase 3 | Connection pool config wrong | Test with 20+ calls ([15]) |
| Phase 4 | Session lifecycle unclear | Read FastMCP docs first |
| Phase 5 | Break existing projects | Test with real project data |

---

## Definition of Done (Per Task)

Each task is complete when:

1. ✅ Code change implemented
2. ✅ No new linter errors
3. ✅ Module still imports (python3 -c "import claude_mcp_hybrid_sessions")
4. ✅ Related test passes (if applicable)
5. ✅ Git commit with descriptive message
6. ✅ Todo marked as completed

---

## Emergency Rollback Plan

If changes break system:

```bash
# Option 1: Revert to backup
cp claude_mcp_hybrid_sessions.py.backup claude_mcp_hybrid_sessions.py

# Option 2: Git reset
git checkout HEAD -- claude_mcp_hybrid_sessions.py

# Option 3: Use working version
cp claude_mcp_hybrid.py claude_mcp_hybrid_sessions.py
# (Note: Loses session-aware features)
```

---

## Next Steps

1. Start with [1]: Remove dead SQLite code
2. Verify file size reduction (303KB → ~50KB)
3. Test import still works
4. Proceed to [2]: Move class definition
5. Continue following critical path

**Status**: Ready to begin Phase 1
