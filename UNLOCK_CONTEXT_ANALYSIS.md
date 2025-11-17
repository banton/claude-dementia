# unlock_context Function Analysis

**Date:** 2025-11-17
**Branch:** `claude/refactor-functions-01WQfcDL5fD8twQRvp6evAJj`
**Function Location:** `claude_mcp_hybrid_sessions.py` (lines 4089-4265)
**Function Size:** 177 lines
**Priority:** P1 (High) - Functions 100-200 lines

---

## Executive Summary

The `unlock_context` function is a **177-line function** that handles the deletion of locked contexts with archival and safety features. While not in the P0 (>200 lines) critical category, it exhibits similar patterns of responsibility mixing that make it a strong candidate for refactoring using the established `switch_project` pattern.

**Key Findings:**
- ✅ Well-structured with clear sections (1-4 labeled steps)
- ⚠️ Mixes validation, archival, deletion, and audit trail logic
- ⚠️ Contains 3 conditional database query branches (version="all"/"latest"/specific)
- ⚠️ Archival loop could be extracted for testability
- ⚠️ Audit trail creation duplicates patterns seen elsewhere

---

## 1. Function Structure Analysis

### Current Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| **Total Lines** | 177 | ⚠️ Moderate (P1 priority) |
| **Docstring** | 66 lines | ✅ Excellent documentation |
| **Executable Code** | 111 lines | ⚠️ High - refactoring recommended |
| **Database Queries** | 8 queries | ⚠️ High - should be consolidated |
| **Conditional Branches** | 6 branches | ⚠️ Moderate complexity |
| **Error Handling Paths** | 3 explicit paths | ✅ Good coverage |
| **Cyclomatic Complexity** | ~8 | ⚠️ Moderate - similar to switch_project (was 8) |

### Logical Sections Breakdown

The function is well-organized into 4 labeled steps:

```python
# Lines 4155-4158: Project selection validation (4 lines)
project_check = _check_project_selection_required(project)
if project_check:
    return project_check
update_session_activity()

# Lines 4162-4188: Step 1 - Find contexts to delete (27 lines)
with _get_db_for_project(project) as conn:
    session_id = _get_session_id_for_project(conn, project)
    # 3 conditional query branches based on version parameter
    # Each query: 4-8 lines
    contexts = cursor.fetchall()
    if not contexts:
        return f"❌ Context '{topic}' (version: {version}) not found"

# Lines 4190-4200: Step 2 - Check for critical contexts (11 lines)
has_critical = False
for ctx in contexts:
    metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
    if metadata.get('priority') == 'always_check':
        has_critical = True
        break
if has_critical and not force:
    return "⚠️  Cannot delete critical context..."

# Lines 4202-4215: Step 3 - Archive before deletion (14 lines)
if archive:
    for ctx in contexts:
        try:
            conn.execute("""INSERT INTO context_archives...""")
        except Exception as e:
            return f"❌ Failed to archive context: {str(e)}"

# Lines 4217-4264: Step 4 - Delete contexts + audit trail (48 lines)
try:
    # 3 conditional DELETE queries (version branches)
    # Audit trail creation (14 lines)
    # Success message building (8 lines)
    conn.commit()
    return result
except Exception as e:
    return f"❌ Failed to delete context: {str(e)}"
```

### Database Operations

**8 Total Queries:**

1. **SELECT for version="all"** (lines 4168-4171) - Find all versions
2. **SELECT for version="latest"** (lines 4173-4178) - Find latest version
3. **SELECT for specific version** (lines 4180-4183) - Find specific version
4. **INSERT into context_archives** (lines 4206-4213) - Archive each context (in loop)
5. **DELETE for version="all"** (lines 4220-4223) - Delete all versions
6. **DELETE for version="latest"** (lines 4226-4229) - Delete latest only
7. **DELETE for specific version** (lines 4231-4234) - Delete specific version
8. **INSERT into memory_entries** (lines 4246-4249) - Create audit trail

**Issues with Current Query Structure:**
- ❌ Three nearly identical SELECT queries with only WHERE clause differences
- ❌ Three nearly identical DELETE queries with only WHERE clause differences
- ❌ Archive INSERT in loop lacks batch insert optimization
- ⚠️ Could benefit from query builder pattern

---

## 2. Refactoring Opportunities

### 2.1 DRY Utilities Already Available

From `claude_mcp_utils.py`, these utilities can replace existing patterns:

✅ **Already using:**
- `_get_db_for_project(project)` - Connection management (line 4163)
- `_get_session_id_for_project(conn, project)` - Session ID retrieval (line 4164)
- `_check_project_selection_required(project)` - Project validation (line 4156)

⚠️ **Can be applied:**
- `safe_json_response()` - Replace string-based error returns
- `format_error_response()` - Standardize exception handling

### 2.2 Code Duplication Patterns

**Pattern 1: Version-based Query Selection (27 lines, duplicated 2x)**
```python
# Lines 4167-4188: SELECT queries
# Lines 4219-4234: DELETE queries
# Both use identical version="all"/"latest"/specific branching
```

**Pattern 2: String-based Error Returns (vs JSON)**
```python
# Lines 4188, 4199-4200, 4215, 4264
# All return raw strings instead of JSON
# Inconsistent with switch_project's safe_json_response() pattern
```

**Pattern 3: Metadata JSON Parsing**
```python
# Line 4193
metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
# This pattern appears throughout codebase (potential DRY utility)
```

### 2.3 Connection Management

**Current Pattern:**
```python
# Line 4163: Uses context manager ✅
with _get_db_for_project(project) as conn:
    # ... operations ...
    conn.commit()  # Line 4251
```

**Assessment:** ✅ **GOOD** - Already uses context manager pattern (learned from switch_project refactoring)

---

## 3. Helper Function Candidates

### 3.1 `_build_version_query_conditions` Helper

**Lines to Extract:** Logic from lines 4167-4183 + 4219-4234

**Estimated Size:** ~30 lines with documentation

**Purpose:** Build WHERE clause conditions based on version parameter

**Proposed Signature:**
```python
def _build_version_query_conditions(
    version: str,
    topic: str,
    session_id: str,
    context_ids: Optional[list] = None
) -> tuple[str, tuple]:
    """
    Build WHERE clause and parameters for version-specific queries.

    Eliminates duplication between SELECT and DELETE queries by
    providing consistent query conditions.

    Args:
        version: "all", "latest", or specific version string
        topic: Context label to filter
        session_id: Session ID for isolation
        context_ids: Optional list of specific IDs (for DELETE after SELECT)

    Returns:
        Tuple of (where_clause, params) for use in SQL queries

    Examples:
        >>> where, params = _build_version_query_conditions("all", "api", "sess123")
        >>> cursor.execute(f"SELECT * FROM context_locks WHERE {where}", params)

        >>> where, params = _build_version_query_conditions("latest", "api", "sess123")
        >>> # Returns ORDER BY + LIMIT 1 for latest
    """
    if version == "all":
        return "label = ? AND session_id = ?", (topic, session_id)
    elif version == "latest":
        # For DELETE, we need to use ID from previously fetched result
        if context_ids:
            return "id = ?", (context_ids[0],)
        # For SELECT, use ORDER BY + LIMIT
        return "label = ? AND session_id = ? ORDER BY version DESC LIMIT 1", (topic, session_id)
    else:
        return "label = ? AND version = ? AND session_id = ?", (topic, version, session_id)
```

**Impact:**
- ✅ Eliminates 6 query branches → 2 queries + 1 helper
- ✅ Reduces cyclomatic complexity from 8 → 6
- ✅ Makes query logic testable in isolation

---

### 3.2 `_archive_contexts` Helper

**Lines to Extract:** Lines 4202-4215

**Estimated Size:** ~35 lines with documentation and error handling

**Purpose:** Archive contexts before deletion with batch insert optimization

**Proposed Signature:**
```python
def _archive_contexts(
    conn,
    contexts: list,
    version: str,
    delete_reason: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """
    Archive contexts to context_archives table before deletion.

    Stores deleted contexts for potential recovery. Uses batch insert
    for efficiency when archiving multiple contexts.

    Args:
        conn: Active database connection
        contexts: List of context row dicts to archive
        version: Version string ("all", "latest", or specific)
        delete_reason: Optional reason for deletion

    Returns:
        Tuple of (success, error_message)
        - (True, None) if archival succeeded
        - (False, error_msg) if archival failed

    Examples:
        >>> success, error = _archive_contexts(conn, contexts, "all")
        >>> if not success:
        ...     return error_response(error)

    Database:
        Inserts into context_archives table with fields:
        - original_id, session_id, label, version, content
        - preview, key_concepts, metadata
        - deleted_at (timestamp), delete_reason
    """
    import time

    if not contexts:
        return True, None

    try:
        reason = delete_reason or f"Deleted {version} version(s)"
        deleted_at = time.time()

        for ctx in contexts:
            conn.execute("""
                INSERT INTO context_archives
                (original_id, session_id, label, version, content, preview,
                 key_concepts, metadata, deleted_at, delete_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ctx['id'], ctx['session_id'], ctx['label'], ctx['version'],
                ctx['content'], ctx['preview'], ctx['key_concepts'],
                ctx['metadata'], deleted_at, reason
            ))

        return True, None

    except Exception as e:
        return False, f"Failed to archive context: {str(e)}"
```

**Impact:**
- ✅ Separates archival concern from main flow
- ✅ Makes archival logic independently testable
- ✅ Enables future optimization (batch inserts)
- ✅ Consistent error handling pattern

---

### 3.3 `_check_critical_contexts` Helper

**Lines to Extract:** Lines 4190-4200

**Estimated Size:** ~25 lines with documentation

**Purpose:** Check if any contexts are marked as critical (always_check priority)

**Proposed Signature:**
```python
def _check_critical_contexts(contexts: list) -> bool:
    """
    Check if any contexts have 'always_check' priority.

    Scans context metadata to determine if deletion requires force flag.
    Critical contexts contain important rules and should not be deleted
    without explicit confirmation.

    Args:
        contexts: List of context row dicts from database

    Returns:
        True if any context has priority='always_check', False otherwise

    Examples:
        >>> has_critical = _check_critical_contexts(contexts)
        >>> if has_critical and not force:
        ...     return error_msg

    Note:
        Handles both null metadata and malformed JSON gracefully.
    """
    for ctx in contexts:
        try:
            metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
            if metadata.get('priority') == 'always_check':
                return True
        except (json.JSONDecodeError, TypeError):
            # Malformed metadata shouldn't block deletion
            continue

    return False
```

**Impact:**
- ✅ Single responsibility (checking priority)
- ✅ Testable in isolation with mock contexts
- ✅ Graceful handling of malformed metadata
- ⚠️ Small extraction (only 11 lines) - could be debatable

---

### 3.4 `_create_deletion_audit_trail` Helper

**Lines to Extract:** Lines 4236-4249

**Estimated Size:** ~30 lines with documentation

**Purpose:** Create audit trail entry in memory_entries table

**Proposed Signature:**
```python
def _create_deletion_audit_trail(
    conn,
    session_id: str,
    topic: str,
    version: str,
    count: int,
    has_critical: bool,
    archived: bool
) -> None:
    """
    Create audit trail entry for context deletion.

    Records deletion event in memory_entries (category='progress')
    with details about what was deleted.

    Args:
        conn: Active database connection
        session_id: Session ID for audit trail
        topic: Context label that was deleted
        version: Version parameter ("all", "latest", or specific)
        count: Number of contexts deleted
        has_critical: Whether critical contexts were deleted
        archived: Whether contexts were archived before deletion

    Returns:
        None (raises exception on failure)

    Examples:
        >>> _create_deletion_audit_trail(
        ...     conn, session_id, "api_spec", "all", 3, False, True
        ... )
        # Inserts: "Deleted 3 version(s) of context 'api_spec' (archived)"
    """
    import time

    # Build version string for audit message
    version_str = f"{count} version(s)" if version == "all" else f"version {version}"

    # Build audit message with labels
    critical_label = " [CRITICAL]" if has_critical else ""
    audit_message = f"Deleted {version_str} of context '{topic}'{critical_label}"

    if archived:
        audit_message += " (archived for recovery)"

    # Insert audit trail
    conn.execute("""
        INSERT INTO memory_entries (category, content, timestamp, session_id)
        VALUES ('progress', ?, ?, ?)
    """, (audit_message, time.time(), session_id))
```

**Impact:**
- ✅ Separates audit concern from deletion logic
- ✅ Consistent audit message formatting
- ✅ Testable in isolation
- ⚠️ Might be overkill (only 14 lines) - consider inline

---

## 4. Complexity Metrics

### Cyclomatic Complexity Breakdown

**Current: ~8** (similar to switch_project before refactoring)

**Complexity Contributors:**
1. `if project_check:` → +1
2. `if version == "all":` → +1
3. `elif version == "latest":` → +1
4. `else:` (specific version) → +1
5. `if not contexts:` → +1
6. `if has_critical and not force:` → +1
7. `if archive:` → +1
8. `for ctx in contexts:` (archive loop) → +1
9. `if version == "all":` (DELETE) → +1
10. `elif version == "latest":` (DELETE) → +1
11. `else:` (DELETE specific) → +1
12. `try/except` (main delete) → +1

**After Refactoring Estimate: ~5**
- Extracting query builder eliminates 6 branches
- Main function only: project check, archive check, try/except
- Similar to switch_project's post-refactor complexity (5)

### Database Query Count

| Operation | Current | After Refactoring |
|-----------|---------|-------------------|
| SELECT queries | 3 (version branches) | 1 (using query builder) |
| DELETE queries | 3 (version branches) | 1 (using query builder) |
| INSERT queries | 2 (archive + audit) | 2 (via helpers) |
| **Total** | **8 queries** | **4 queries** |

### Error Paths

**3 explicit error paths:**
1. Line 4188: Context not found
2. Line 4199-4200: Critical context without force
3. Line 4215: Archive failure
4. Line 4264: Delete failure

**Assessment:** ✅ Good coverage, but should use `safe_json_response()` for consistency

### Conditional Branches

**6 major branches:**
1. Project validation check
2. Version selection for SELECT (3-way)
3. Critical context check
4. Archive flag check
5. Version selection for DELETE (3-way)

**After refactoring:** Reduced to ~3 branches in main function

---

## 5. Critical Requirements to Preserve

### 5.1 Session Isolation

✅ **CRITICAL - MUST PRESERVE**

```python
# Line 4164: Session ID for isolation
session_id = _get_session_id_for_project(conn, project)

# Lines 4170, 4177, 4182: All queries filter by session_id
WHERE label = ? AND session_id = ?
```

**Why critical:** Prevents cross-session data leaks (Bug #2 fix)

**Refactoring impact:** ⚠️ Must ensure helpers maintain session_id filtering

---

### 5.2 Transaction Boundaries

✅ **CRITICAL - MUST PRESERVE**

```python
# Line 4163: Single transaction for entire operation
with _get_db_for_project(project) as conn:
    # ... all operations ...
    conn.commit()  # Line 4251
```

**Why critical:**
- Atomicity: Archive + Delete + Audit must succeed/fail together
- If archive fails, deletion should not proceed
- If deletion fails, archive should rollback

**Refactoring impact:** ⚠️ Must keep all operations in same transaction context

---

### 5.3 Archive Before Delete Ordering

✅ **CRITICAL - MUST PRESERVE**

```python
# Lines 4203-4215: Archive FIRST
if archive:
    for ctx in contexts:
        conn.execute("INSERT INTO context_archives...")

# Lines 4218-4234: Delete SECOND (only after archive succeeds)
try:
    conn.execute("DELETE FROM context_locks...")
```

**Why critical:** Data loss prevention - must archive before deleting

**Refactoring impact:** ✅ Helper functions maintain this ordering

---

### 5.4 Force Flag for Critical Contexts

✅ **CRITICAL - MUST PRESERVE**

```python
# Lines 4190-4200: Check critical + force flag
has_critical = False
for ctx in contexts:
    if metadata.get('priority') == 'always_check':
        has_critical = True
        break

if has_critical and not force:
    return "⚠️  Cannot delete critical context without force=True"
```

**Why critical:** Prevents accidental deletion of important rules

**Refactoring impact:** ✅ `_check_critical_contexts()` preserves this logic

---

### 5.5 Function Signature

✅ **CRITICAL - MUST PRESERVE**

```python
async def unlock_context(
    topic: str,
    version: str = "all",
    force: bool = False,
    archive: bool = True,
    project: Optional[str] = None
) -> str:
```

**Why critical:** MCP tool contract - callers depend on this signature

**Refactoring impact:** ✅ No changes to signature

---

### 5.6 Return Value Format

⚠️ **INCONSISTENT - NEEDS STANDARDIZATION**

**Current:** Returns raw strings
```python
return f"❌ Context '{topic}' (version: {version}) not found"
return f"✅ Deleted {version_str} of '{topic}'"
```

**switch_project pattern:** Returns JSON via `safe_json_response()`
```python
return safe_json_response({"message": "...", "stats": {...}})
```

**Recommendation:** ⚠️ Consider standardizing to JSON, but check if MCP tools require strings

---

### 5.7 Error Handling Behavior

✅ **MUST PRESERVE**

**Early returns on validation failures:**
- Line 4188: Context not found → return error immediately
- Line 4199: Critical without force → return error immediately
- Line 4215: Archive failure → return error immediately (blocks delete)

**Try/except around deletion:**
- Line 4218-4264: Delete + audit in single try block
- Failure rolls back transaction (implicit with context manager)

**Refactoring impact:** ✅ Helpers use same pattern (early returns for errors)

---

### 5.8 Audit Trail Side Effect

✅ **CRITICAL - MUST PRESERVE**

```python
# Lines 4246-4249: Audit trail creation
conn.execute("""
    INSERT INTO memory_entries (category, content, timestamp, session_id)
    VALUES ('progress', ?, ?, ?)
""", (audit_message, current_time, session_id))
```

**Why critical:** Deletion events must be recorded for compliance/debugging

**Refactoring impact:** ✅ `_create_deletion_audit_trail()` preserves this

---

## 6. Comparison to switch_project

### Similarities (Good candidates for same refactoring pattern)

| Aspect | unlock_context | switch_project |
|--------|----------------|----------------|
| **Size** | 177 lines | 112 lines (before) → 71 lines (after) |
| **Complexity** | ~8 | 8 (before) → 5 (after) |
| **Database Ops** | 8 queries | 6 queries (before) |
| **Helpers Extracted** | 3-4 candidates | 2 extracted |
| **DRY Utilities** | 2 applicable | 4 applied |
| **Connection Pattern** | ✅ Context manager | ✅ Context manager (fixed) |
| **Error Handling** | String returns | JSON (standardized) |
| **Documentation** | 66 lines (✅) | 18 lines (before) → 101 (after) |

### Differences (Considerations for refactoring)

| Aspect | unlock_context | switch_project |
|--------|----------------|----------------|
| **Conditional Queries** | 3-way version branching (2x) | Single query path |
| **Loops** | Archive loop over contexts | No loops |
| **Transaction Scope** | Archive + Delete + Audit | Single update + stats query |
| **Side Effects** | 2 (archive + audit trail) | 1 (cache update) |
| **Return Format** | Strings (inconsistent) | JSON (standardized) |
| **Validation** | Critical context check | Project name sanitization |

### Lessons from switch_project Applied Here

✅ **What we can replicate:**

1. **Helper extraction for database operations** ✅
   - `_fetch_project_stats` → `_archive_contexts`
   - Clear separation of concerns

2. **Response builder pattern** ⚠️ (maybe)
   - `_build_switch_response` → `_build_unlock_response`?
   - unlock_context returns simpler strings - might not need builder

3. **DRY utilities usage** ✅
   - `sanitize_project_name` → Already using project helpers
   - `safe_json_response` → Can apply for consistency
   - `format_error_response` → Can apply

4. **Connection management** ✅
   - unlock_context already uses context manager (learned from switch_project!)

5. **Test-driven approach** ✅
   - Write tests first (RED)
   - Implement helpers (GREEN)
   - Refactor main function (REFACTOR)

⚠️ **What's different (unique challenges):**

1. **Query branching complexity**
   - switch_project: Linear query flow
   - unlock_context: 3-way branching (2x) for version handling
   - **Solution:** Extract query builder helper

2. **Transaction atomicity**
   - switch_project: No critical transaction requirements
   - unlock_context: Must maintain archive → delete → audit ordering
   - **Solution:** Keep all operations in same transaction, test rollback

3. **Loop-based operations**
   - switch_project: No loops
   - unlock_context: Loop over contexts for archival
   - **Solution:** Extract loop into helper with proper error handling

4. **Return format inconsistency**
   - switch_project: Standardized JSON returns
   - unlock_context: String returns (might be intentional for MCP)
   - **Decision needed:** Keep strings or migrate to JSON?

---

## 7. Refactoring Strategy Recommendation

### Approach 1: Conservative (RECOMMENDED for first iteration)

**Extract 2 helpers + apply DRY utilities**

**Helpers:**
1. `_archive_contexts()` - Archive operation (lines 4202-4215)
2. `_build_version_query_conditions()` - Query builder (extracted from 4167-4183, 4219-4234)

**DRY utilities:**
- Keep using existing project helpers ✅
- Consider `safe_json_response()` if return format can be JSON

**Expected Outcome:**
- Lines: 177 → ~90 in main function + ~65 in helpers
- Complexity: 8 → 5
- Queries: 8 → ~4 (consolidated)
- Risk: 🟢 LOW (similar to switch_project)

---

### Approach 2: Aggressive (Optional for second iteration)

**Extract 4 helpers + standardize returns**

**Helpers:**
1. `_build_version_query_conditions()` - Query builder
2. `_archive_contexts()` - Archive operation
3. `_check_critical_contexts()` - Critical check
4. `_create_deletion_audit_trail()` - Audit trail

**Changes:**
- Standardize returns to JSON (breaking change?)
- Consolidate error handling

**Expected Outcome:**
- Lines: 177 → ~60 in main function + ~120 in helpers
- Complexity: 8 → 3
- Risk: 🟡 MEDIUM (return format change might affect callers)

---

### Approach 3: Query Consolidation (Advanced optimization)

**Go beyond switch_project pattern:**

**Add database layer abstraction:**
```python
class ContextQuery:
    """Query builder for context operations."""

    def __init__(self, session_id: str):
        self.session_id = session_id

    def find_by_version(self, label: str, version: str) -> str:
        """Generate SELECT query for version parameter."""
        # Eliminates all 3 SELECT branches

    def delete_by_version(self, label: str, version: str, context_ids: list) -> str:
        """Generate DELETE query for version parameter."""
        # Eliminates all 3 DELETE branches
```

**Expected Outcome:**
- Even more DRY
- Risk: 🔴 HIGH (new abstraction layer)
- Recommendation: ⚠️ **NOT for first refactoring** (too complex)

---

## 8. Recommended Next Steps

### Step 1: Write Tests (RED phase)

**Test file:** `test_unlock_context_refactoring.py`

**Test cases:**
1. `test_archive_contexts_success()` - Archival works
2. `test_archive_contexts_failure()` - Archival error handling
3. `test_build_version_query_all()` - Query builder for "all"
4. `test_build_version_query_latest()` - Query builder for "latest"
5. `test_build_version_query_specific()` - Query builder for specific version
6. `test_check_critical_contexts_true()` - Detects critical
7. `test_check_critical_contexts_false()` - Non-critical contexts
8. `test_unlock_context_preserves_transaction()` - Transaction atomicity

---

### Step 2: Extract Helpers (GREEN phase)

**Order of implementation:**
1. `_build_version_query_conditions()` - Foundation for queries
2. `_archive_contexts()` - Self-contained operation
3. (Optional) `_check_critical_contexts()` - If small helpers are desired

---

### Step 3: Refactor Main Function (REFACTOR phase)

**Apply helpers to main function:**
```python
async def unlock_context(...) -> str:
    # Project validation (unchanged)
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    update_session_activity()

    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # Step 1: Find contexts using query builder
        where, params = _build_version_query_conditions(version, topic, session_id)
        cursor = conn.execute(f"SELECT * FROM context_locks WHERE {where}", params)
        contexts = cursor.fetchall()

        if not contexts:
            return f"❌ Context '{topic}' (version: {version}) not found"

        # Step 2: Check critical (potentially extracted)
        has_critical = _check_critical_contexts(contexts)
        if has_critical and not force:
            return "⚠️  Cannot delete critical..."

        # Step 3: Archive (extracted helper)
        if archive:
            success, error = _archive_contexts(conn, contexts, version)
            if not success:
                return f"❌ {error}"

        # Step 4: Delete using query builder
        try:
            where, params = _build_version_query_conditions(
                version, topic, session_id,
                context_ids=[ctx['id'] for ctx in contexts]
            )
            conn.execute(f"DELETE FROM context_locks WHERE {where}", params)

            # Audit trail (potentially extracted)
            _create_deletion_audit_trail(
                conn, session_id, topic, version,
                len(contexts), has_critical, archive
            )

            conn.commit()

            # Build response
            version_str = f"{len(contexts)} version(s)" if version == "all" else f"version {version}"
            result = f"✅ Deleted {version_str} of '{topic}'"
            if archive:
                result += f"\n   💾 Archived for recovery"
            if has_critical:
                result += f"\n   ⚠️  Critical context deleted (force=True)"

            return result

        except Exception as e:
            return f"❌ Failed to delete context: {str(e)}"
```

**Expected size:** ~60-90 lines (from 177)

---

### Step 4: Update Documentation

**Files to update:**
1. `FUNCTION_REFACTORING_ANALYSIS.md` - Add unlock_context to completed list
2. `REFACTORING_STATUS_SUMMARY.md` - Update status
3. `docs/UNLOCK_CONTEXT_ARCHITECTURE.md` - NEW (like switch_project)

---

## 9. Risk Assessment

### Risk Level: 🟢 **LOW-MEDIUM**

**Low Risk Factors:**
- ✅ Well-structured original code (4 clear steps)
- ✅ Good documentation already exists
- ✅ Connection management pattern already correct
- ✅ Can follow proven switch_project pattern
- ✅ No external API dependencies

**Medium Risk Factors:**
- ⚠️ Transaction atomicity requirements (archive + delete + audit)
- ⚠️ Query branching complexity (6 conditional queries)
- ⚠️ Loop-based operations (archive multiple contexts)
- ⚠️ Critical context safety check (must not break)

**Mitigation:**
- Write comprehensive transaction rollback tests
- Test all version parameter combinations
- Mock database for unit tests
- Integration tests with actual PostgreSQL

---

## 10. Success Metrics

### Target Improvements (Based on switch_project results)

| Metric | Before | Target After | switch_project Achieved |
|--------|--------|--------------|------------------------|
| Lines in Main | 177 | 80-90 | -36% (112→71) |
| Cyclomatic Complexity | 8 | 4-5 | -37% (8→5) |
| Database Queries | 8 | 4-5 | N/A |
| Testable Units | 1 | 3-4 | +200% (1→3) |
| Helper Functions | 0 | 2-3 | 2 extracted |
| Documentation | 66 lines | 120+ | +461% |

---

## Conclusion

The `unlock_context` function is a **strong candidate for refactoring** using the proven `switch_project` pattern. While not as large as P0 functions (200+ lines), it exhibits similar patterns of responsibility mixing and would benefit significantly from helper extraction.

**Recommended approach:**
1. **Start conservative** - Extract 2 helpers (`_archive_contexts`, `_build_version_query_conditions`)
2. **Apply DRY utilities** - Existing project helpers already in use ✅
3. **Follow TDD** - Write tests first, then extract helpers
4. **Maintain critical requirements** - Transaction atomicity, session isolation, archive-before-delete

**Expected outcome:**
- ✅ Improved maintainability (smaller main function)
- ✅ Better testability (isolated helpers)
- ✅ Reduced complexity (8 → 5)
- ✅ Consistent patterns with switch_project
- ✅ Low risk (proven refactoring approach)

**Timeline estimate:** 2-3 hours
- 1 hour: Write tests (RED)
- 1 hour: Extract helpers (GREEN)
- 30 min: Refactor main function (REFACTOR)
- 30 min: Documentation updates

---

**Ready to proceed with refactoring?** ✅

The analysis is complete. Recommend starting with conservative approach (2 helpers) following the switch_project TDD pattern.
