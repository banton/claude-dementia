# Unlock Context Test Strategy
**Function:** `unlock_context`
**Location:** `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py:4089`
**Lines:** ~175 lines (4089-4264)
**Created:** 2025-11-17
**Branch:** `claude/refactor-functions-01WQfcDL5fD8twQRvp6evAJj`

---

## Executive Summary

This document defines a comprehensive test strategy for the `unlock_context` function refactoring. The function currently has **6 basic tests** but requires **30+ additional tests** to cover edge cases, error scenarios, PostgreSQL operations, session isolation, and helper function extraction.

### Current Test Status
- ✅ **Basic functionality:** 6 tests (PASSING)
- ⚠️ **Edge cases:** 0 tests (MISSING)
- ⚠️ **Error handling:** 0 tests (MISSING)
- ⚠️ **PostgreSQL-specific:** 0 tests (MISSING)
- ⚠️ **Concurrency:** 0 tests (MISSING)
- ⚠️ **Helper functions:** 0 tests (NOT YET EXTRACTED)

### Test Coverage Goals
| Category | Current | Target | Gap |
|----------|---------|--------|-----|
| Version deletion modes | 3 | 5 | +2 |
| Critical context protection | 2 | 4 | +2 |
| Archive operations | 1 | 5 | +4 |
| Error scenarios | 1 | 8 | +7 |
| Session isolation | 0 | 3 | +3 |
| PostgreSQL operations | 0 | 4 | +4 |
| Edge cases | 0 | 6 | +6 |
| Helper functions | 0 | 10 | +10 |
| **TOTAL** | **7** | **45** | **+38** |

---

## Part 1: Current Test Coverage Analysis

### Existing Tests (test_unlock_context.py)

#### ✅ Test 1: Delete All Versions
**Function:** `test_delete_all_versions()`
**Coverage:** Basic "all" version mode
**What it tests:**
- Delete all versions of a context (3 versions: v1.0, v1.1, v1.2)
- Verify success message includes version count
- Verify all versions removed from database

**What it DOESN'T test:**
- Archive creation during deletion
- Audit trail creation
- Session isolation
- PostgreSQL schema operations

---

#### ✅ Test 2: Delete Specific Version
**Function:** `test_delete_specific_version()`
**Coverage:** Specific version mode
**What it tests:**
- Delete only version 1.1 of a context
- Verify versions 1.0 and 1.2 remain
- Verify only specified version deleted

**What it DOESN'T test:**
- Non-existent version handling
- Version string validation (malformed versions)

---

#### ✅ Test 3: Delete Latest Version
**Function:** `test_delete_latest_version()`
**Coverage:** "latest" version mode
**What it tests:**
- Delete only the most recent version
- Verify older versions preserved
- Verify correct version identification

**What it DOESN'T test:**
- Tie-breaking when multiple versions have same timestamp
- Latest with only one version

---

#### ✅ Test 4: Critical Context Protection
**Function:** `test_delete_critical_requires_force()`
**Coverage:** Critical context (priority=always_check) protection
**What it tests:**
- Deletion without force=True fails
- Error message includes warning
- Context not deleted without force
- Deletion with force=True succeeds

**What it DOESN'T test:**
- Mixed batch (some critical, some not)
- Force flag on non-critical contexts
- Multiple critical contexts at once

---

#### ✅ Test 5: Archive Creation
**Function:** `test_archive_created()`
**Coverage:** Default archive behavior
**What it tests:**
- Archive record created before deletion
- Archived content matches original
- Archived version matches original

**What it DOESN'T test:**
- Archive creation failure (what happens?)
- No-archive mode (archive=False)
- Archive content completeness (metadata, preview, key_concepts)
- Multiple versions archived at once

---

#### ✅ Test 6: Non-Existent Context
**Function:** `test_delete_nonexistent()`
**Coverage:** Error handling for missing context
**What it tests:**
- Error returned for non-existent topic
- Error message mentions "not found"

**What it DOESN'T test:**
- Non-existent version of existing topic
- Empty topic string
- Null/None topic

---

### Test Quality Assessment

#### Strengths
- ✅ Tests use SQLite for deterministic results
- ✅ Clean setup/teardown with temporary databases
- ✅ Tests are independent (separate DB per test)
- ✅ Uses asyncio.run() for async function testing
- ✅ Assertions include helpful error messages

#### Weaknesses
- ❌ **SQLite-only:** Tests use SQLite but production uses PostgreSQL
- ❌ **No session isolation tests:** All tests use same session_id
- ❌ **No transaction tests:** No verification of rollback on failure
- ❌ **No concurrency tests:** No testing of simultaneous deletions
- ❌ **Limited error scenarios:** Only tests one error case
- ❌ **No audit trail verification:** Tests don't check memory_entries
- ❌ **Incomplete archive tests:** Only checks basic archive creation

---

## Part 2: Required Test Scenarios

### 2.1 Version Deletion Modes (Priority: P0)

#### Test 2.1.1: Delete All Versions (Empty Result)
**Status:** ⚠️ NEW
**Priority:** P0 (Critical)
**Scenario:** Delete "all" when only 1 version exists
**Input:**
```python
# Context: api_spec v1.0 (only one version)
unlock_context(topic="api_spec", version="all")
```
**Expected Output:**
- Success message: "Deleted 1 version(s)"
- All versions removed
- Archive contains 1 record

**Why it matters:** Edge case for "all" mode behavior

---

#### Test 2.1.2: Delete Latest (Only Version)
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Delete "latest" when only 1 version exists
**Input:**
```python
# Context: api_spec v1.0 (only version)
unlock_context(topic="api_spec", version="latest")
```
**Expected Output:**
- Success message
- Context completely removed
- No versions remain

**Why it matters:** Edge case - latest = only = all

---

#### Test 2.1.3: Delete Non-Existent Version
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Try to delete specific version that doesn't exist
**Input:**
```python
# Context: api_spec v1.0, v1.1 exist (no v2.0)
unlock_context(topic="api_spec", version="2.0")
```
**Expected Output:**
- Error: "Context 'api_spec' (version: 2.0) not found"
- No deletion occurs
- No archive created

**Why it matters:** Prevents silent failures

---

#### Test 2.1.4: Delete Latest with Timestamp Ties
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** Multiple versions have identical locked_at timestamp
**Setup:**
```python
# Create 3 versions with same timestamp
fixed_time = time.time()
for v in ["1.0", "1.1", "1.2"]:
    insert_with_timestamp(version=v, locked_at=fixed_time)
```
**Expected Output:**
- Deletes exactly 1 version (deterministic selection)
- Error or well-defined tie-breaking behavior

**Why it matters:** Timestamp collisions can happen in batch imports

---

#### Test 2.1.5: Delete Version with Malformed String
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** Version parameter contains invalid characters
**Input:**
```python
unlock_context(topic="api_spec", version="'; DROP TABLE --")
unlock_context(topic="api_spec", version="../../etc/passwd")
unlock_context(topic="api_spec", version="1.0 OR 1=1")
```
**Expected Output:**
- No SQL injection
- Safe parameterized query execution
- Not found error (version doesn't exist)

**Why it matters:** Security - SQL injection prevention

---

### 2.2 Critical Context Protection (Priority: P0)

#### Test 2.2.1: Force Flag on Non-Critical Context
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Use force=True on regular (non-critical) context
**Input:**
```python
# Context: api_spec (priority=reference, not critical)
unlock_context(topic="api_spec", version="all", force=True)
```
**Expected Output:**
- Deletion succeeds
- No warning about critical context
- Archive created
- No mention of "force" in success message

**Why it matters:** Force flag should be harmless on non-critical

---

#### Test 2.2.2: Mixed Batch (Critical + Non-Critical)
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Delete "all" versions where some are critical, some aren't
**Setup:**
```python
# Create multiple versions
insert(label="api_spec", version="1.0", priority="reference")
insert(label="api_spec", version="1.1", priority="always_check")
insert(label="api_spec", version="1.2", priority="important")
```
**Input:**
```python
unlock_context(topic="api_spec", version="all", force=False)
```
**Expected Output:**
- Deletion FAILS (any critical version blocks entire operation)
- Error: "Cannot delete critical (always_check) context..."
- NO versions deleted (atomic operation)

**Why it matters:** One critical version should protect all versions

---

#### Test 2.2.3: Force Delete All Critical Versions
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Delete multiple critical versions with force=True
**Setup:**
```python
insert(label="security_rule", version="1.0", priority="always_check")
insert(label="security_rule", version="1.1", priority="always_check")
insert(label="security_rule", version="1.2", priority="always_check")
```
**Input:**
```python
unlock_context(topic="security_rule", version="all", force=True)
```
**Expected Output:**
- All 3 versions deleted
- Success message includes: "⚠️ Critical context deleted (force=True was used)"
- All 3 versions archived
- Audit trail records critical deletion

**Why it matters:** Verifies force override works correctly

---

#### Test 2.2.4: Critical Check with Invalid Metadata
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** Context has malformed metadata JSON
**Setup:**
```python
# Manually insert context with invalid JSON metadata
conn.execute("""
    INSERT INTO context_locks (label, version, content, metadata, session_id)
    VALUES ('bad_context', '1.0', 'test', 'invalid{json}', 'test_session')
""")
```
**Input:**
```python
unlock_context(topic="bad_context", version="all")
```
**Expected Output:**
- Graceful handling of JSON parse error
- Either: treat as non-critical (safe default)
- Or: error message about corrupted metadata

**Why it matters:** Defensive programming against database corruption

---

### 2.3 Archive Operations (Priority: P0)

#### Test 2.3.1: No-Archive Mode
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Delete with archive=False
**Input:**
```python
unlock_context(topic="api_spec", version="all", archive=False)
```
**Expected Output:**
- Contexts deleted successfully
- NO archive records created
- Success message: "Deleted N version(s)" (no archive mention)
- Audit trail created

**Why it matters:** Tests archive opt-out functionality

---

#### Test 2.3.2: Archive Creation Failure
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Archive INSERT fails (e.g., disk full, constraint violation)
**Mock:**
```python
# Mock conn.execute to raise exception on INSERT INTO context_archives
with patch('conn.execute') as mock_execute:
    mock_execute.side_effect = [
        MagicMock(),  # SELECT succeeds
        Exception("Disk full")  # INSERT fails
    ]
```
**Expected Output:**
- Error: "❌ Failed to archive context: Disk full"
- NO deletion occurs (rollback)
- Original context still exists

**Why it matters:** Archive failure should prevent deletion

---

#### Test 2.3.3: Archive Content Completeness
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Verify all fields archived correctly
**Setup:**
```python
insert(
    label="api_spec",
    version="1.0",
    content="Full API specification...",
    preview="API spec for REST endpoints",
    key_concepts='["API", "REST", "auth"]',
    metadata='{"priority": "important", "tags": ["api", "v1"]}'
)
```
**Input:**
```python
unlock_context(topic="api_spec", version="all")
```
**Verification:**
```python
# Query archive
archive = conn.execute("SELECT * FROM context_archives WHERE label='api_spec'")
assert archive['content'] == original_content
assert archive['preview'] == original_preview
assert archive['key_concepts'] == original_key_concepts
assert archive['metadata'] == original_metadata
assert archive['version'] == "1.0"
assert archive['delete_reason'] == "Deleted all version(s)"
assert archive['deleted_at'] is not None
```
**Why it matters:** Ensures complete archive for recovery

---

#### Test 2.3.4: Archive Multiple Versions
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Delete "all" with 5+ versions, verify all archived
**Setup:**
```python
for i in range(1, 6):
    insert(label="api_spec", version=f"1.{i}", content=f"Version 1.{i}")
```
**Input:**
```python
unlock_context(topic="api_spec", version="all")
```
**Verification:**
```python
archives = conn.execute("""
    SELECT * FROM context_archives
    WHERE label='api_spec'
    ORDER BY version
""")
assert len(archives) == 5
for i, archive in enumerate(archives, 1):
    assert archive['version'] == f"1.{i}"
    assert archive['content'] == f"Version 1.{i}"
```
**Why it matters:** Batch archiving correctness

---

#### Test 2.3.5: Archive Duplicate Deletion
**Status:** ⚠️ NEW
**Priority:** P2
**Scenario:** Delete same context twice (archive should have 2 records)
**Setup:**
```python
insert(label="test", version="1.0", content="Original")
unlock_context(topic="test", version="all")

# Re-create and delete again
insert(label="test", version="1.0", content="Second")
unlock_context(topic="test", version="all")
```
**Verification:**
```python
archives = conn.execute("""
    SELECT * FROM context_archives
    WHERE label='test'
    ORDER BY deleted_at
""")
assert len(archives) == 2
assert archives[0]['content'] == "Original"
assert archives[1]['content'] == "Second"
```
**Why it matters:** Archive history preservation

---

### 2.4 Error Scenarios (Priority: P0)

#### Test 2.4.1: Empty Topic String
**Status:** ⚠️ NEW
**Priority:** P0
**Input:**
```python
unlock_context(topic="", version="all")
```
**Expected Output:**
- Error: "Context '' (version: all) not found"
- OR: "Topic cannot be empty"
- No deletion, no archive

**Why it matters:** Input validation

---

#### Test 2.4.2: None/Null Topic
**Status:** ⚠️ NEW
**Priority:** P0
**Input:**
```python
unlock_context(topic=None, version="all")
```
**Expected Output:**
- TypeError or validation error
- OR: graceful error message

**Why it matters:** Type safety

---

#### Test 2.4.3: SQL Injection in Topic
**Status:** ⚠️ NEW
**Priority:** P0 (SECURITY)
**Input:**
```python
unlock_context(topic="'; DROP TABLE context_locks; --", version="all")
```
**Expected Output:**
- No SQL injection executed
- Safe parameterized query
- Error: "Context '...' not found"

**Verification:**
```python
# Verify context_locks table still exists
assert table_exists("context_locks")
```
**Why it matters:** Security - critical vulnerability prevention

---

#### Test 2.4.4: Delete Transaction Rollback
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** DELETE fails after archive succeeds
**Mock:**
```python
with patch('conn.execute') as mock_execute:
    mock_execute.side_effect = [
        MagicMock(),  # SELECT succeeds
        MagicMock(),  # INSERT archive succeeds
        Exception("Constraint violation")  # DELETE fails
    ]
```
**Expected Output:**
- Error: "❌ Failed to delete context: Constraint violation"
- Archive record rolled back (transaction)
- Original context still exists

**Why it matters:** Transaction atomicity

---

#### Test 2.4.5: Audit Trail Creation Failure
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** Deletion succeeds but audit trail INSERT fails
**Expected Behavior:** Should this rollback deletion?
**Decision needed:** Should audit trail failure block deletion?

---

#### Test 2.4.6: Database Connection Failure
**Status:** ⚠️ NEW
**Priority:** P1
**Input:**
```python
# Close connection before unlock_context
conn.close()
unlock_context(topic="api_spec", version="all")
```
**Expected Output:**
- Error: "❌ Failed to delete context: connection closed"
- Graceful error handling

---

#### Test 2.4.7: Extremely Long Topic Name
**Status:** ⚠️ NEW
**Priority:** P2
**Input:**
```python
unlock_context(topic="a" * 10000, version="all")
```
**Expected Output:**
- Error: "not found"
- No performance degradation
- No buffer overflow

---

#### Test 2.4.8: Unicode Topic Name
**Status:** ⚠️ NEW
**Priority:** P2
**Input:**
```python
unlock_context(topic="プロジェクト", version="all")
unlock_context(topic="🚀api_spec", version="all")
```
**Expected Output:**
- Proper Unicode handling
- Correct comparison in SQL
- Not found (if doesn't exist)

---

### 2.5 Session Isolation (Priority: P0)

#### Test 2.5.1: Different Session Can't Delete
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Context locked by session A, session B tries to delete
**Setup:**
```python
# Session A creates context
SESSION_ID = "session_a"
insert(label="api_spec", version="1.0", session_id="session_a")

# Session B tries to delete
SESSION_ID = "session_b"
unlock_context(topic="api_spec", version="all")
```
**Expected Output:**
- Error: "Context 'api_spec' not found"
- Context still exists for session A
- Session isolation maintained

---

#### Test 2.5.2: Same Session Can Delete
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Verify session_id filter works correctly
**Setup:**
```python
# Create contexts for different sessions
insert(label="api_spec", version="1.0", session_id="session_a")
insert(label="api_spec", version="1.0", session_id="session_b")

# Session A deletes
SESSION_ID = "session_a"
unlock_context(topic="api_spec", version="all")
```
**Expected Output:**
- Session A's context deleted
- Session B's context still exists
- Only 1 context deleted

---

#### Test 2.5.3: Session Isolation in Archive
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Archive should preserve session_id
**Verification:**
```python
SESSION_ID = "session_a"
unlock_context(topic="api_spec", version="all")

archive = conn.execute("""
    SELECT * FROM context_archives WHERE label='api_spec'
""").fetchone()

assert archive['session_id'] == "session_a"
```
**Why it matters:** Archive recovery to correct session

---

### 2.6 PostgreSQL-Specific Tests (Priority: P0)

#### Test 2.6.1: PostgreSQL Schema Isolation
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Delete operates on correct schema
**Setup:**
```python
# Create two project schemas
adapter1 = PostgreSQLAdapter(schema="dementia_project_a")
adapter2 = PostgreSQLAdapter(schema="dementia_project_b")

# Insert same topic in both schemas
adapter1.execute("INSERT INTO context_locks ...")
adapter2.execute("INSERT INTO context_locks ...")

# Delete from project_a
unlock_context(topic="api_spec", project="project_a")
```
**Verification:**
```python
# Verify only project_a deleted
assert count_contexts(schema="dementia_project_a", topic="api_spec") == 0
assert count_contexts(schema="dementia_project_b", topic="api_spec") == 1
```

---

#### Test 2.6.2: PostgreSQL Parameterized Queries
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Verify PostgreSQL uses %s placeholders (not ?)
**Note:** Current implementation uses SQLite (?) syntax

**Current code (SQLite):**
```python
conn.execute("SELECT * FROM context_locks WHERE label = ?", (topic,))
```

**PostgreSQL requires:**
```python
conn.execute("SELECT * FROM context_locks WHERE label = %s", (topic,))
```

**Test:** Verify correct placeholder syntax for PostgreSQL

---

#### Test 2.6.3: PostgreSQL Connection Context Manager
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Verify `_get_db_for_project()` context manager works
**Current code (line 4163):**
```python
with _get_db_for_project(project) as conn:
    # ... operations ...
```

**Test:**
```python
# Verify connection closed after context manager exit
with _get_db_for_project(project) as conn:
    conn_id = id(conn)

# Connection should be closed here
assert connection_is_closed(conn_id)
```

---

#### Test 2.6.4: PostgreSQL Transaction Commit
**Status:** ⚠️ NEW
**Priority:** P0
**Scenario:** Verify `conn.commit()` is called
**Current code (line 4251):**
```python
conn.commit()
```

**Test:** Mock commit() and verify it's called exactly once

---

### 2.7 Edge Cases (Priority: P1)

#### Test 2.7.1: Delete During Active Access
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** Delete context while another operation is reading it
**Setup:** Concurrent operations (requires threading/asyncio)

---

#### Test 2.7.2: Delete with Large Content
**Status:** ⚠️ NEW
**Priority:** P2
**Scenario:** Delete context with 10MB+ content
**Why it matters:** Archive storage limits

---

#### Test 2.7.3: Delete with Special Characters in Content
**Status:** ⚠️ NEW
**Priority:** P2
**Input:**
```python
content = "API with \x00 null bytes and 'quotes' and \"double\" and \n newlines"
```

---

#### Test 2.7.4: Rapid Repeated Deletions
**Status:** ⚠️ NEW
**Priority:** P2
**Scenario:** Delete same topic 1000 times (stress test)

---

#### Test 2.7.5: Delete All Topics in Database
**Status:** ⚠️ NEW
**Priority:** P2
**Scenario:** Delete every context (100+ contexts)

---

#### Test 2.7.6: Version String Edge Cases
**Status:** ⚠️ NEW
**Priority:** P2
**Input:**
```python
unlock_context(topic="api", version="0.0.0.0.0.1")
unlock_context(topic="api", version="v1.0-rc1-alpha")
unlock_context(topic="api", version="latest-2")
```

---

### 2.8 Concurrent Operations (Priority: P1)

#### Test 2.8.1: Simultaneous Deletes (Same Context)
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** Two operations delete same context simultaneously
**Expected:** One succeeds, one gets "not found"

---

#### Test 2.8.2: Delete While Locking
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** `unlock_context` and `lock_context` run concurrently

---

#### Test 2.8.3: Delete While Updating
**Status:** ⚠️ NEW
**Priority:** P1
**Scenario:** `unlock_context` and `update_context` run concurrently

---

## Part 3: Helper Function Tests (Post-Refactoring)

### 3.1 Proposed Helper Functions

Based on refactoring analysis, `unlock_context` (175 lines) should be split into:

#### Helper 3.1.1: `_find_contexts_to_delete(conn, topic, version, session_id)`
**Purpose:** Build and execute SELECT query
**Lines:** ~25 lines
**Returns:** `list[Row]` of contexts to delete

**Test Cases:**
- ✅ Find all versions
- ✅ Find specific version
- ✅ Find latest version
- ✅ Return empty list if not found
- ✅ Session isolation

---

#### Helper 3.1.2: `_check_critical_contexts(contexts)`
**Purpose:** Check if any context has priority=always_check
**Lines:** ~15 lines
**Returns:** `bool` (has_critical)

**Test Cases:**
- ✅ Detect critical context
- ✅ Return False for all non-critical
- ✅ Handle missing metadata
- ✅ Handle invalid JSON metadata
- ✅ Handle missing priority field

---

#### Helper 3.1.3: `_archive_contexts(conn, contexts, delete_reason)`
**Purpose:** Archive contexts before deletion
**Lines:** ~25 lines
**Returns:** `tuple[bool, Optional[str]]` (success, error)

**Test Cases:**
- ✅ Archive single context
- ✅ Archive multiple contexts
- ✅ Preserve all fields
- ✅ Handle INSERT failure
- ✅ Return error message on failure

---

#### Helper 3.1.4: `_delete_contexts(conn, topic, version, session_id, context_ids)`
**Purpose:** Execute DELETE query
**Lines:** ~20 lines
**Returns:** `tuple[bool, Optional[str]]` (success, error)

**Test Cases:**
- ✅ Delete by topic (all versions)
- ✅ Delete by version (specific)
- ✅ Delete by ID (latest)
- ✅ Handle DELETE failure
- ✅ Return error message on failure

---

#### Helper 3.1.5: `_create_delete_audit_trail(conn, topic, version, count, has_critical, archived, session_id)`
**Purpose:** Create audit trail entry
**Lines:** ~20 lines
**Returns:** `None` (or raises exception)

**Test Cases:**
- ✅ Create audit entry
- ✅ Include version count
- ✅ Include critical flag
- ✅ Include archive flag
- ✅ Handle INSERT failure

---

#### Helper 3.1.6: `_format_delete_response(topic, version, count, has_critical, archived)`
**Purpose:** Build success message
**Lines:** ~15 lines
**Returns:** `str` (formatted message)

**Test Cases:**
- ✅ Format "all" versions message
- ✅ Format specific version message
- ✅ Include archive note
- ✅ Include critical warning
- ✅ Include version count

---

### 3.2 Refactored Main Function

```python
async def unlock_context(
    topic: str,
    version: str = "all",
    force: bool = False,
    archive: bool = True,
    project: Optional[str] = None
) -> str:
    """Orchestrator: delegates to helper functions"""

    # 1. Validate project
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    update_session_activity()

    # 2. Get database connection
    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # 3. Find contexts to delete
        contexts = _find_contexts_to_delete(conn, topic, version, session_id)

        if not contexts:
            return f"❌ Context '{topic}' (version: {version}) not found"

        # 4. Check for critical contexts
        has_critical = _check_critical_contexts(contexts)

        if has_critical and not force:
            return f"⚠️  Cannot delete critical (always_check) context '{topic}' without force=True"

        # 5. Archive (if enabled)
        if archive:
            success, error = _archive_contexts(conn, contexts, f"Deleted {version} version(s)")
            if not success:
                return f"❌ Failed to archive context: {error}"

        # 6. Delete contexts
        context_ids = [ctx['id'] for ctx in contexts]
        success, error = _delete_contexts(conn, topic, version, session_id, context_ids)
        if not success:
            return f"❌ Failed to delete context: {error}"

        # 7. Create audit trail
        _create_delete_audit_trail(
            conn, topic, version, len(contexts),
            has_critical, archive, session_id
        )

        conn.commit()

        # 8. Format response
        return _format_delete_response(topic, version, len(contexts), has_critical, archive)
```

**Test for refactored main:**
- ✅ Integration test: end-to-end deletion
- ✅ Mock helpers and verify orchestration
- ✅ Verify helper call order
- ✅ Verify transaction commit

---

## Part 4: Integration Tests

### 4.1 End-to-End Workflows

#### Integration 4.1.1: Complete CRUD Lifecycle
**Covered by:** `test_crud_workflow.py` (already exists)
**Workflow:** Lock → Read → Update → **Unlock** → Verify

---

#### Integration 4.1.2: Delete and Recover
**Status:** ⚠️ NEW
**Workflow:**
1. Lock context
2. Delete with archive
3. Manually recover from context_archives
4. Verify recovered content matches original

---

#### Integration 4.1.3: Multi-Project Deletion
**Status:** ⚠️ NEW
**Workflow:**
1. Create 3 projects
2. Lock same topic in each project
3. Delete from project A
4. Verify projects B and C unaffected

---

#### Integration 4.1.4: Session Handover Deletion
**Status:** ⚠️ NEW
**Workflow:**
1. Session A locks context
2. Session A sleeps (handover)
3. Session B wakes up
4. Session B deletes context
5. Verify deletion success

---

### 4.2 Performance Tests

#### Performance 4.2.1: Delete 100 Versions
**Status:** ⚠️ NEW
**Setup:** Create 100 versions of same context
**Measure:** Time to delete all
**Target:** <1000ms

---

#### Performance 4.2.2: Delete with Large Archive
**Status:** ⚠️ NEW
**Setup:** Context with 10MB content
**Measure:** Archive creation time
**Target:** <2000ms

---

## Part 5: Test Implementation Plan

### 5.1 TDD Order (Red-Green-Refactor)

#### Phase 1: Core Functionality (RED → GREEN)
**Order:** Write tests first, ensure they fail, then make them pass

1. **Week 1: Error Handling Tests**
   - Test 2.4.1: Empty topic string
   - Test 2.4.2: None/null topic
   - Test 2.4.3: SQL injection (CRITICAL)
   - Test 2.4.4: Transaction rollback
   - Run tests → RED (should fail)
   - Fix implementation → GREEN (should pass)

2. **Week 1: Version Mode Edge Cases**
   - Test 2.1.1: Delete all (single version)
   - Test 2.1.2: Delete latest (only version)
   - Test 2.1.3: Non-existent version
   - Run tests → RED
   - Fix implementation → GREEN

3. **Week 2: Archive Tests**
   - Test 2.3.1: No-archive mode
   - Test 2.3.2: Archive failure (rollback)
   - Test 2.3.3: Archive completeness
   - Test 2.3.4: Archive multiple versions
   - Run tests → RED
   - Fix implementation → GREEN

4. **Week 2: Session Isolation**
   - Test 2.5.1: Different session can't delete
   - Test 2.5.2: Same session can delete
   - Test 2.5.3: Session in archive
   - Run tests → RED
   - Fix implementation → GREEN

5. **Week 3: Critical Context Protection**
   - Test 2.2.1: Force on non-critical
   - Test 2.2.2: Mixed batch
   - Test 2.2.3: Force delete all critical
   - Run tests → RED
   - Fix implementation → GREEN

---

#### Phase 2: PostgreSQL Migration (RED → GREEN)
**Order:** Convert tests from SQLite to PostgreSQL

6. **Week 3: PostgreSQL Setup**
   - Create `test_unlock_context_postgres.py`
   - Test 2.6.1: Schema isolation
   - Test 2.6.2: Parameterized queries
   - Test 2.6.3: Connection context manager
   - Test 2.6.4: Transaction commit
   - Run tests → RED (SQLite syntax fails)
   - Fix implementation → GREEN (PostgreSQL syntax)

---

#### Phase 3: Refactoring (GREEN → REFACTOR)
**Order:** All tests passing, now refactor into helpers

7. **Week 4: Extract Helper Functions**
   - Write tests for `_find_contexts_to_delete()`
   - Write tests for `_check_critical_contexts()`
   - Write tests for `_archive_contexts()`
   - Write tests for `_delete_contexts()`
   - Write tests for `_create_delete_audit_trail()`
   - Write tests for `_format_delete_response()`
   - Extract helpers → Run all tests → Should still be GREEN

8. **Week 4: Refactor Main Function**
   - Rewrite `unlock_context()` as orchestrator
   - Run ALL tests (old + new)
   - Verify 100% still passing

---

#### Phase 4: Edge Cases and Integration (Optional)
**Order:** Add nice-to-have tests

9. **Week 5: Edge Cases**
   - Test 2.7.x: Special characters, large content, etc.
   - Test 2.8.x: Concurrency tests

10. **Week 5: Integration Tests**
    - Integration 4.1.x: Multi-project, session handover
    - Performance 4.2.x: Benchmarks

---

### 5.2 Test Fixtures Required

#### Fixture 5.2.1: PostgreSQL Test Database
```python
@pytest.fixture(scope="module")
def postgres_test_db():
    """Create isolated PostgreSQL test schema."""
    schema_name = f"test_unlock_{uuid.uuid4().hex[:8]}"
    adapter = PostgreSQLAdapter(schema=schema_name)
    adapter.ensure_schema_exists()
    adapter.initialize_tables()

    yield adapter

    # Cleanup
    adapter.drop_schema_cascade()
```

---

#### Fixture 5.2.2: Test Session
```python
@pytest.fixture
def test_session(postgres_test_db):
    """Create test session."""
    session_id = str(uuid.uuid4())
    postgres_test_db.execute("""
        INSERT INTO sessions (session_id, active_project, created_at)
        VALUES (%s, 'test_project', %s)
    """, (session_id, time.time()))

    yield session_id

    # Cleanup
    postgres_test_db.execute(
        "DELETE FROM sessions WHERE session_id = %s",
        (session_id,)
    )
```

---

#### Fixture 5.2.3: Sample Context
```python
@pytest.fixture
def sample_context(postgres_test_db, test_session):
    """Create sample context for testing."""
    postgres_test_db.execute("""
        INSERT INTO context_locks
        (session_id, label, version, content, content_hash, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        test_session,
        "api_spec",
        "1.0",
        "Full API specification",
        hashlib.sha256(b"Full API specification").hexdigest(),
        '{"priority": "reference"}'
    ))

    yield {
        "session_id": test_session,
        "topic": "api_spec",
        "version": "1.0"
    }
```

---

#### Fixture 5.2.4: Multiple Versions
```python
@pytest.fixture
def multiple_versions(postgres_test_db, test_session):
    """Create 3 versions of a context."""
    for i in range(1, 4):
        postgres_test_db.execute("""
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            test_session,
            "api_spec",
            f"1.{i}",
            f"API v1.{i}",
            hashlib.sha256(f"API v1.{i}".encode()).hexdigest()
        ))

    yield test_session
```

---

#### Fixture 5.2.5: Critical Context
```python
@pytest.fixture
def critical_context(postgres_test_db, test_session):
    """Create critical (always_check) context."""
    postgres_test_db.execute("""
        INSERT INTO context_locks
        (session_id, label, version, content, content_hash, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        test_session,
        "security_rule",
        "1.0",
        "ALWAYS check authentication",
        hashlib.sha256(b"ALWAYS check authentication").hexdigest(),
        '{"priority": "always_check"}'
    ))

    yield test_session
```

---

### 5.3 Mock Requirements

#### Mock 5.3.1: Archive Failure
```python
@pytest.fixture
def mock_archive_failure(monkeypatch):
    """Mock conn.execute to fail on INSERT INTO context_archives."""
    original_execute = conn.execute

    def mock_execute(sql, params=None):
        if "INSERT INTO context_archives" in sql:
            raise Exception("Archive disk full")
        return original_execute(sql, params)

    monkeypatch.setattr('conn.execute', mock_execute)
```

---

#### Mock 5.3.2: Delete Failure
```python
@pytest.fixture
def mock_delete_failure(monkeypatch):
    """Mock DELETE to fail."""
    # Similar to above
```

---

#### Mock 5.3.3: Timestamp Control
```python
@pytest.fixture
def fixed_time():
    """Return fixed timestamp for deterministic tests."""
    return 1700000000.0  # Fixed Unix timestamp
```

---

### 5.4 Test File Organization

```
tests/
├── unit/
│   ├── test_unlock_context_helpers.py          # Helper function tests
│   │   ├── test_find_contexts_to_delete()
│   │   ├── test_check_critical_contexts()
│   │   ├── test_archive_contexts()
│   │   ├── test_delete_contexts()
│   │   ├── test_create_delete_audit_trail()
│   │   └── test_format_delete_response()
│   │
│   ├── test_unlock_context_validation.py       # Input validation tests
│   │   ├── test_empty_topic()
│   │   ├── test_null_topic()
│   │   ├── test_sql_injection()
│   │   └── test_malformed_version()
│   │
│   └── test_unlock_context_edge_cases.py       # Edge case tests
│       ├── test_unicode_topic()
│       ├── test_large_content()
│       └── test_special_characters()
│
├── integration/
│   ├── test_unlock_context_postgres.py         # PostgreSQL-specific tests
│   │   ├── test_schema_isolation()
│   │   ├── test_parameterized_queries()
│   │   └── test_transaction_rollback()
│   │
│   ├── test_unlock_context_workflows.py        # End-to-end workflows
│   │   ├── test_delete_and_recover()
│   │   ├── test_multi_project_deletion()
│   │   └── test_session_handover_deletion()
│   │
│   └── test_unlock_context_concurrency.py      # Concurrency tests
│       ├── test_simultaneous_deletes()
│       ├── test_delete_while_locking()
│       └── test_delete_while_updating()
│
└── performance/
    └── test_unlock_context_performance.py      # Performance benchmarks
        ├── test_delete_100_versions()
        └── test_delete_large_archive()
```

**Total New Files:** 8 test files
**Total New Tests:** 38+ tests
**Estimated Lines:** ~2,500 lines of test code

---

## Part 6: Expected Test Count by Category

| Category | Test Count | Priority | Status |
|----------|-----------|----------|--------|
| **Existing Tests** | 6 | - | ✅ PASSING |
| Version deletion modes | 5 | P0 | ⚠️ NEW |
| Critical context protection | 4 | P0 | ⚠️ NEW |
| Archive operations | 5 | P0 | ⚠️ NEW |
| Error scenarios | 8 | P0 | ⚠️ NEW |
| Session isolation | 3 | P0 | ⚠️ NEW |
| PostgreSQL operations | 4 | P0 | ⚠️ NEW |
| Edge cases | 6 | P1 | ⚠️ NEW |
| Concurrency | 3 | P1 | ⚠️ NEW |
| Helper functions | 10 | P0 | ⚠️ POST-REFACTOR |
| Integration workflows | 4 | P1 | ⚠️ NEW |
| Performance | 2 | P2 | ⚠️ NEW |
| **TOTAL** | **60** | - | - |

---

## Part 7: Success Criteria

### 7.1 Test Coverage Goals

✅ **Minimum Required (Before Refactoring):**
- All P0 tests passing (35 tests)
- 100% line coverage of main function
- 100% branch coverage (all if/else paths)
- All error paths tested

✅ **Ideal (After Refactoring):**
- All 60 tests passing
- 100% coverage of helper functions
- All integration tests passing
- Performance benchmarks documented

---

### 7.2 Quality Gates

**Before Refactoring:**
- ❌ Cannot refactor until P0 tests written
- ❌ Cannot refactor until all tests GREEN
- ❌ Cannot refactor until PostgreSQL tests pass

**During Refactoring:**
- ❌ All existing tests must stay GREEN
- ❌ No test modifications during refactoring (unless fixing bugs)
- ❌ New helper tests must be written BEFORE extraction

**After Refactoring:**
- ✅ All 60 tests passing
- ✅ No performance regression (benchmarks)
- ✅ Code coverage >95%
- ✅ All edge cases handled

---

### 7.3 Acceptance Criteria

**Test Suite Must:**
1. ✅ Run in <10 seconds (unit tests)
2. ✅ Run in <30 seconds (integration tests)
3. ✅ Be deterministic (no flaky tests)
4. ✅ Clean up resources (no DB pollution)
5. ✅ Use fixtures for test data
6. ✅ Mock external dependencies
7. ✅ Test both SQLite (legacy) and PostgreSQL
8. ✅ Include security tests (SQL injection)
9. ✅ Include transaction rollback tests
10. ✅ Document expected behavior

---

## Part 8: Risk Assessment

### 8.1 Testing Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| Tests take too long | High | Medium | Use in-memory PostgreSQL, mock slow operations |
| Flaky concurrency tests | High | High | Use deterministic delays, proper synchronization |
| PostgreSQL setup complex | Medium | High | Docker compose, clear setup docs |
| Archive tests fill disk | Medium | Low | Use test schema, cleanup after tests |
| Transaction tests unreliable | High | Medium | Proper isolation, explicit commit/rollback |

---

### 8.2 Refactoring Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| Break existing functionality | Critical | Medium | Write tests FIRST (TDD) |
| Performance regression | High | Low | Benchmark before/after |
| Introduce new bugs | High | Medium | 100% test coverage |
| Helper functions too granular | Medium | Medium | Review function boundaries |
| Lost transaction atomicity | Critical | Low | Test rollback scenarios |

---

## Part 9: Timeline Estimate

### 9.1 Development Schedule

| Week | Phase | Tasks | Tests Written | Status |
|------|-------|-------|---------------|--------|
| 1 | Error Handling | Write 12 error tests | 12 | ⚠️ TODO |
| 1 | Version Modes | Write 5 version tests | 5 | ⚠️ TODO |
| 2 | Archive Operations | Write 5 archive tests | 5 | ⚠️ TODO |
| 2 | Session Isolation | Write 3 session tests | 3 | ⚠️ TODO |
| 3 | Critical Protection | Write 4 critical tests | 4 | ⚠️ TODO |
| 3 | PostgreSQL Setup | Write 4 PostgreSQL tests | 4 | ⚠️ TODO |
| 4 | Helper Extraction | Extract + test helpers | 10 | ⚠️ TODO |
| 4 | Refactor Main | Rewrite orchestrator | 0 | ⚠️ TODO |
| 5 | Edge Cases | Write 6 edge case tests | 6 | ⚠️ TODO |
| 5 | Integration | Write 4 integration tests | 4 | ⚠️ TODO |
| 5 | Performance | Write 2 performance tests | 2 | ⚠️ TODO |
| **TOTAL** | **5 weeks** | **60 tests** | **60** | - |

**Estimated Effort:** 80-100 hours (including refactoring)

---

## Part 10: Next Steps

### 10.1 Immediate Actions

1. **Review this strategy** with team
2. **Approve test plan** and priorities
3. **Set up PostgreSQL test environment**
   ```bash
   docker run -d \
     -e POSTGRES_PASSWORD=test \
     -e POSTGRES_DB=dementia_test \
     -p 5433:5432 \
     postgres:15
   ```
4. **Create test file structure** (8 files)
5. **Write first test** (SQL injection - P0 security)

---

### 10.2 Test Writing Order (TDD)

**Start with highest-risk tests:**

1. ✅ **Test 2.4.3:** SQL injection (SECURITY)
2. ✅ **Test 2.4.4:** Transaction rollback (DATA INTEGRITY)
3. ✅ **Test 2.3.2:** Archive failure (DATA LOSS PREVENTION)
4. ✅ **Test 2.5.1:** Session isolation (SECURITY)
5. ✅ **Test 2.2.2:** Mixed critical batch (CORRECTNESS)

**Then fill in remaining P0 tests**

**Finally add P1 and P2 nice-to-haves**

---

### 10.3 Definition of Done

**For unlock_context refactoring:**

- ✅ All 35 P0 tests written
- ✅ All P0 tests passing (GREEN)
- ✅ PostgreSQL tests passing
- ✅ Function refactored into 6 helpers
- ✅ All 60 tests passing
- ✅ Code coverage >95%
- ✅ Performance benchmarks documented
- ✅ Documentation updated
- ✅ PR reviewed and approved

---

## Appendix A: Test Template

```python
#!/usr/bin/env python3
"""
Test: [Test Name]
Category: [Error Handling / Version Modes / Archive / etc.]
Priority: [P0 / P1 / P2]
"""

import pytest
import asyncio
from postgres_adapter import PostgreSQLAdapter
from claude_mcp_hybrid_sessions import unlock_context

@pytest.mark.asyncio
async def test_[test_name](postgres_test_db, test_session):
    """
    Test [scenario description].

    Given: [preconditions]
    When: [action]
    Then: [expected result]
    """
    # Arrange (GIVEN)
    # Set up test data

    # Act (WHEN)
    result = await unlock_context(
        topic="test_topic",
        version="all",
        project="test_project"
    )

    # Assert (THEN)
    assert "✅" in result

    # Verify side effects
    count = postgres_test_db.execute(
        "SELECT COUNT(*) FROM context_locks WHERE label=%s",
        ("test_topic",)
    ).fetchone()[0]

    assert count == 0
```

---

## Appendix B: PostgreSQL Test Setup

```python
# conftest.py (pytest configuration)

import pytest
import os
from postgres_adapter import PostgreSQLAdapter

@pytest.fixture(scope="session")
def postgres_url():
    """Get PostgreSQL connection URL from environment."""
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:test@localhost:5433/dementia_test"
    )

@pytest.fixture(scope="module")
def postgres_test_schema():
    """Create isolated test schema."""
    import uuid
    schema_name = f"test_{uuid.uuid4().hex[:8]}"

    adapter = PostgreSQLAdapter(database_url=postgres_url())
    adapter.execute_update(f"CREATE SCHEMA {schema_name}")
    adapter.set_schema(schema_name)
    adapter.initialize_tables()

    yield adapter

    # Cleanup
    adapter.execute_update(f"DROP SCHEMA {schema_name} CASCADE")
    adapter.close()
```

---

**END OF STRATEGY DOCUMENT**

**Ready to begin? Start with Test 2.4.3 (SQL Injection)**
