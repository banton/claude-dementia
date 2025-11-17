# DRY (Don't Repeat Yourself) Analysis Report
## File: claude_mcp_hybrid_sessions.py

**Date:** 2025-11-17
**File Size:** 9,925 lines (371.4KB)
**MCP Tools:** 47 tools defined with @mcp.tool()
**Helper Functions:** 26 private functions (prefixed with `_`)

---

## Executive Summary

This analysis identified **10 major categories of code duplication** across 47 MCP tool functions. The most critical duplication involves:
- **Project name sanitization** (5+ exact duplicates)
- **JSON error/success response building** (145+ json.dumps calls with similar structures)
- **Database connection patterns** (3 different patterns in use)
- **Error handling boilerplate** (~99 try-except blocks with similar structure)
- **Import statement duplication** (9 `import json`, 13 `import re`, 4 `import psycopg2`)

**Estimated Impact:** Extracting these patterns to utilities could reduce code by ~1,500-2,000 lines (~15-20%).

---

## Top 10 Most Duplicated Code Patterns

### 1. ⭐ **Project Name Sanitization** (HIGHEST PRIORITY)
**Occurrences:** 5+ exact duplicates
**Lines:** 2022-2023, 2219-2220, 2376-2377, 2488-2489, 2577-2578
**Impact:** 5 tools directly affected

**Current Code (duplicated 5+ times):**
```python
import re
safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]
```

**Affected Tools:**
- `switch_project()`
- `create_project()`
- `get_project_info()`
- `delete_project()`
- `select_project_for_session()`

**Suggested Utility:**
```python
def sanitize_project_name(name: str) -> str:
    """
    Sanitize project name for PostgreSQL schema naming.

    Rules:
    - Lowercase only
    - Replace non-alphanumeric with underscore
    - Collapse multiple underscores
    - Strip leading/trailing underscores
    - Max 32 characters

    Args:
        name: Raw project name

    Returns:
        Sanitized schema-safe name
    """
    safe = re.sub(r'[^a-z0-9]', '_', name.lower())
    safe = re.sub(r'_+', '_', safe).strip('_')[:32]
    return safe
```

**Priority:** 🔴 **HIGH**
**Refactoring Effort:** Low (simple extraction)
**Risk:** Very Low (pure function, easily testable)

---

### 2. ⭐ **JSON Error Response Building** (HIGHEST PRIORITY)
**Occurrences:** 17+ error responses, 10+ success responses
**Pattern Variations:** Multiple structures (`"error"`, `"success": False`, `"message"`)
**Impact:** ALL 47 tools affected

**Current Patterns:**
```python
# Pattern 1: Simple error
return json.dumps({
    "success": False,
    "error": str(e)
})

# Pattern 2: Error with context
return json.dumps({
    "error": "INVALID_PROJECT",
    "message": f"⚠️  Project '{project}' does not exist",
    "available_projects": [p for p in project_names if p != '__PENDING__'],
    "instruction": "📌 Use an existing project name"
})

# Pattern 3: Success with data
return json.dumps({
    "success": True,
    "message": f"✅ Project '{name}' created successfully!",
    "project": name,
    "schema": safe_name,
    "usage": f"Use project='{name}' parameter"
})
```

**Suggested Utilities:**
```python
class ResponseBuilder:
    """Standardized JSON response builder for MCP tools."""

    @staticmethod
    def success(message: str, **data) -> str:
        """Build success response with optional data."""
        response = {
            "success": True,
            "message": message,
            **data
        }
        return json.dumps(response, indent=2)

    @staticmethod
    def error(message: str, error_code: Optional[str] = None, **context) -> str:
        """Build error response with optional context."""
        response = {
            "success": False,
            "error": message,
            **context
        }
        if error_code:
            response["error_code"] = error_code
        return json.dumps(response, indent=2)

    @staticmethod
    def project_selection_required(available_projects: List[str]) -> str:
        """Build project selection error (used by 13 tools)."""
        return ResponseBuilder.error(
            message="⚠️  Please select a project before using this tool",
            error_code="PROJECT_SELECTION_REQUIRED",
            available_projects=available_projects,
            instruction="📌 Call select_project_for_session('project_name')"
        )
```

**Priority:** 🔴 **HIGH**
**Refactoring Effort:** Medium (affects all tools, requires consistency)
**Risk:** Medium (need to ensure backward compatibility with MCP protocol)

---

### 3. ⭐ **Database Connection Management** (HIGH PRIORITY)
**Occurrences:** 3 different patterns in use
**Impact:** ALL database-touching tools (~40+ tools)

**Current Patterns:**

**Pattern A: Direct psycopg2.connect (4 occurrences)**
```python
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(config.database_url)
cur = conn.cursor(cursor_factory=RealDictCursor)
# ... do work ...
conn.close()  # Often missing or in wrong place!
```
*Lines: 2057, 2131 (commented), 2292, 2501*

**Pattern B: adapter.get_connection() (5 occurrences)**
```python
adapter = _get_cached_adapter(schema_name)
conn = adapter.get_connection()
try:
    cur = conn.cursor()
    # ... do work ...
finally:
    adapter.release_connection(conn)
    adapter.close()
```

**Pattern C: Context manager - _get_db_for_project() (15 occurrences - PREFERRED)**
```python
with _get_db_for_project(project) as conn:
    session_id = _get_session_id_for_project(conn, project)
    # ... do work ...
    # Connection automatically closed
```

**Problem:** Mixing patterns leads to:
- Connection leaks (Pattern A often missing `.close()`)
- Inconsistent error handling
- Difficult to track connection pool usage

**Suggested Utility (already exists but underused):**
```python
# ALREADY EXISTS at line 599! Just needs wider adoption
def _get_db_for_project(project: str = None):
    """
    Get database connection for a specific project.

    ALWAYS use as context manager:
        with _get_db_for_project(project) as conn:
            # work here
    """
    # ... implementation ...
    return AutoClosingPostgreSQLConnection(conn, adapter)
```

**Action Required:**
- Migrate all Pattern A and B usages to Pattern C (context manager)
- Remove direct `psycopg2.connect()` calls
- Standardize on `_get_db_for_project()` everywhere

**Priority:** 🔴 **HIGH** (prevents connection leaks)
**Refactoring Effort:** Medium (need to migrate 9 tools from Pattern A/B to C)
**Risk:** Medium (connection handling is critical)

---

### 4. **Error Handling Boilerplate** (MEDIUM PRIORITY)
**Occurrences:** ~99 try-except blocks
**Impact:** ALL 47 tools

**Current Pattern:**
```python
@mcp.tool()
async def some_tool(param: str) -> str:
    import json  # ← Repeated in every tool!

    try:
        # Tool logic here
        return json.dumps({
            "success": True,
            "result": result
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })
```

**Problems:**
- `import json` repeated in 9+ tool functions
- Same try-except-return pattern in every tool
- No structured error logging
- Lost stack traces

**Suggested Utility:**
```python
def tool_error_handler(func):
    """
    Decorator to standardize error handling in MCP tools.

    Automatically wraps tool in try-except and returns JSON error.
    """
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            # If function already returns JSON string, pass through
            if isinstance(result, str) and result.startswith('{'):
                return result
            # Otherwise wrap in success response
            return ResponseBuilder.success("Operation completed", result=result)
        except Exception as e:
            # Log full stack trace for debugging
            logger.exception(f"Error in {func.__name__}")
            # Return user-friendly error
            return ResponseBuilder.error(
                message=str(e),
                error_code=type(e).__name__,
                tool=func.__name__
            )

    return wrapper

# Usage:
@mcp.tool()
@tool_error_handler
async def some_tool(param: str) -> str:
    # No try-except needed!
    # No import json needed!
    # Just write the business logic
    result = do_something(param)
    return {"data": result}  # Decorator handles JSON conversion
```

**Priority:** 🟡 **MEDIUM**
**Refactoring Effort:** High (touches all 47 tools)
**Risk:** Medium (changes error reporting structure)

---

### 5. **Project Selection Check** (HIGH PRIORITY)
**Occurrences:** 13 tool calls to `_check_project_selection_required()`
**Impact:** 13 tools (all memory/context tools)

**Current Pattern (repeated 13 times):**
```python
@mcp.tool()
async def some_tool(project: Optional[str] = None, ...) -> str:
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check  # Returns JSON error string

    # ... rest of tool logic ...
```

**Affected Tools:**
- `lock_context()`
- `recall_context()`
- `search_contexts()`
- Plus 10+ other memory tools

**Suggested Utility:**
```python
def require_project_selection(func):
    """
    Decorator to enforce project selection before tool execution.

    Checks if project is selected and returns error if not.
    Automatically injects validated project into kwargs.
    """
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        project = kwargs.get('project', None)

        # Check selection
        error = _check_project_selection_required(project)
        if error:
            return error

        # Inject resolved project name
        kwargs['_resolved_project'] = _get_project_for_context(project)

        return await func(*args, **kwargs)

    return wrapper

# Usage:
@mcp.tool()
@require_project_selection
async def lock_context(content: str, topic: str, project: Optional[str] = None, **kwargs) -> str:
    # No manual check needed!
    # Use kwargs['_resolved_project'] instead of _get_project_for_context(project)
    resolved_project = kwargs['_resolved_project']
    # ... rest of logic ...
```

**Priority:** 🟡 **MEDIUM-HIGH**
**Refactoring Effort:** Medium (13 tools affected)
**Risk:** Low (pure validation logic)

---

### 6. **Import Statement Duplication** (LOW PRIORITY)
**Occurrences:**
- `import json`: 9 times (within tool functions)
- `import re`: 13 times (within tool functions)
- `import psycopg2`: 4 times
- `from psycopg2.extras import RealDictCursor`: 4 times

**Current Anti-Pattern:**
```python
@mcp.tool()
async def tool_a(...) -> str:
    import json  # ← Inside function
    import re    # ← Inside function
    # ... use them ...

@mcp.tool()
async def tool_b(...) -> str:
    import json  # ← Duplicated!
    import re    # ← Duplicated!
    # ... use them ...
```

**Why This Happens:**
Python allows function-local imports, which some developers use to make dependencies explicit. However, this is an anti-pattern when the same imports appear in many functions.

**Solution:**
Move to top-level imports (already exists at lines 15-28, but tools re-import):
```python
# At top of file (already exists but not used consistently):
import json
import re
import psycopg2
from psycopg2.extras import RealDictCursor
```

**Action Required:**
- Remove all function-local `import json` statements (9 occurrences)
- Remove all function-local `import re` statements (13 occurrences)
- Remove redundant `import psycopg2` (4 occurrences)

**Priority:** 🟢 **LOW** (cosmetic, no functional impact)
**Refactoring Effort:** Very Low (simple find-replace)
**Risk:** Zero (imports already at top level)

---

### 7. **Database Cursor Creation** (MEDIUM PRIORITY)
**Occurrences:**
- `cursor = conn.execute(...)`: 91 times
- `cur.execute(...)`: 61 times
- `with conn.cursor() as cur:`: 12 times
- `cur = conn.cursor()`: 4 times

**Current Patterns:**

**Pattern A: Direct execute (91 uses - PREFERRED)**
```python
cursor = conn.execute("""
    SELECT * FROM table WHERE id = ?
""", (id,))
result = cursor.fetchone()
```

**Pattern B: Explicit cursor (61 uses)**
```python
cur = conn.cursor()
cur.execute("""
    SELECT * FROM table WHERE id = %s
""", (id,))
result = cur.fetchone()
```

**Pattern C: Context manager (12 uses - BEST)**
```python
with conn.cursor() as cur:
    cur.execute("""
        SELECT * FROM table WHERE id = %s
    """, (id,))
    result = cur.fetchone()
# Cursor automatically closed
```

**Issue:** Placeholder inconsistency
- SQLite uses `?` placeholders
- PostgreSQL uses `%s` placeholders
- Code has workaround via `AutoClosingPostgreSQLConnection._convert_sql_placeholders()`

**Suggested Utility:**
```python
class QueryHelper:
    """Helper for consistent database queries."""

    @staticmethod
    def execute_one(conn, sql: str, params: tuple = None) -> Optional[dict]:
        """Execute query and return first row as dict."""
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()

    @staticmethod
    def execute_all(conn, sql: str, params: tuple = None) -> List[dict]:
        """Execute query and return all rows as dicts."""
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()

    @staticmethod
    def execute_update(conn, sql: str, params: tuple = None) -> int:
        """Execute update/insert and return affected row count."""
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount
```

**Priority:** 🟡 **MEDIUM**
**Refactoring Effort:** Medium (many call sites)
**Risk:** Low (wrappers around existing code)

---

### 8. **Logging/Debug Print Statements** (LOW PRIORITY)
**Occurrences:**
- `print(..., file=sys.stderr)`: 27 times
- `print(f"✅...": 4 times
- `print(f"⚠️...": 12 times
- `print(f"❌...": 4 times

**Current Pattern:**
```python
print(f"✅ Switched to project: {safe_name}", file=sys.stderr)
print(f"⚠️  Warning: Could not check project selection: {e}", file=sys.stderr)
print(f"❌ Session creation failed: {e}", file=sys.stderr)
```

**Issues:**
- Inconsistent formatting
- No log levels
- No structured logging
- All goes to stderr (can't filter)

**Suggested Utility (already exists but underused):**
```python
# Logger already imported at line 75!
import logging
logger = logging.getLogger(__name__)

# Should use instead of print():
logger.info(f"✅ Switched to project: {safe_name}")
logger.warning(f"⚠️  Could not check project selection: {e}")
logger.error(f"❌ Session creation failed: {e}")
```

**Action Required:**
- Replace all 27 `print(..., file=sys.stderr)` with `logger.*()` calls
- Add log level configuration
- Consider structured logging (JSON format for cloud)

**Priority:** 🟢 **LOW** (quality-of-life improvement)
**Refactoring Effort:** Low (find-replace with care)
**Risk:** Very Low (logging changes)

---

### 9. **Session ID Retrieval** (MEDIUM PRIORITY)
**Occurrences:**
- `_get_local_session_id()`: Multiple calls
- `get_current_session_id()`: Multiple calls (old API)
- `getattr(config, '_current_session_id', None)`: Multiple patterns
- `_get_session_id_for_project(conn, project)`: 15+ calls

**Current Patterns:**
```python
# Pattern A: Local session (session-aware fork)
session_id = _get_local_session_id()

# Pattern B: From config (hosted mode)
session_id = getattr(config, '_current_session_id', None)

# Pattern C: From database
session_id = _get_session_id_for_project(conn, project)

# Pattern D: Old API
session_id = get_current_session_id()
```

**Problem:** 4 different ways to get session ID creates confusion

**Suggested Utility:**
```python
def get_current_session() -> Optional[str]:
    """
    Get current session ID using unified fallback logic.

    Priority:
    1. Local session ID (stdio mode)
    2. Config session ID (HTTP mode)
    3. None (no session)

    Returns:
        Session ID or None
    """
    # Try local session first
    if _local_session_id:
        return _local_session_id

    # Try config
    session_id = getattr(config, '_current_session_id', None)
    if session_id:
        return session_id

    return None
```

**Priority:** 🟡 **MEDIUM**
**Refactoring Effort:** Medium (need to audit all session ID calls)
**Risk:** Medium (session management is critical)

---

### 10. **Transaction Management** (MEDIUM PRIORITY)
**Occurrences:**
- `conn.commit()`: 26 times
- `conn.rollback()`: 4 times
- `try-except-rollback`: Inconsistent usage

**Current Pattern:**
```python
try:
    conn.execute("INSERT ...", params)
    conn.execute("UPDATE ...", params)
    conn.commit()
except Exception as e:
    # Sometimes has rollback, sometimes doesn't
    conn.rollback()  # Only 4 explicit rollbacks!
    raise
```

**Issue:**
- 26 commits but only 4 rollbacks
- Many try-except blocks missing rollback
- Potential for partial commits on error

**Suggested Utility:**
```python
@contextmanager
def transaction(conn):
    """
    Context manager for database transactions.

    Auto-commits on success, auto-rolls back on exception.

    Usage:
        with transaction(conn):
            conn.execute("INSERT ...")
            conn.execute("UPDATE ...")
        # Auto-committed here
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    # No finally needed - context manager handles cleanup
```

**Usage:**
```python
with _get_db_for_project(project) as conn:
    with transaction(conn):
        conn.execute("INSERT ...")
        conn.execute("UPDATE ...")
        # Auto-committed or rolled back
```

**Priority:** 🟡 **MEDIUM**
**Refactoring Effort:** Medium (26 commit sites)
**Risk:** Medium (transaction handling is critical)

---

## Suggested Utility Functions to Extract

### High Priority (Extract First)

#### 1. `sanitize_project_name(name: str) -> str`
**Location:** New file: `src/utils/project_utils.py`
**Impact:** 5 tools immediately
**LOC Savings:** ~10 lines

#### 2. `ResponseBuilder` class
**Location:** New file: `src/utils/response_builder.py`
**Impact:** ALL 47 tools
**LOC Savings:** ~500-800 lines (major impact)

#### 3. Standardize on `_get_db_for_project()` context manager
**Location:** Already exists (line 599), need to enforce usage
**Impact:** 40+ tools
**LOC Savings:** ~200 lines + prevents connection leaks

### Medium Priority (Extract After High Priority)

#### 4. `@require_project_selection` decorator
**Location:** New file: `src/utils/decorators.py`
**Impact:** 13 tools
**LOC Savings:** ~50 lines

#### 5. `@tool_error_handler` decorator
**Location:** `src/utils/decorators.py`
**Impact:** ALL 47 tools
**LOC Savings:** ~300 lines

#### 6. `QueryHelper` class
**Location:** `src/utils/db_helpers.py`
**Impact:** 30+ tools
**LOC Savings:** ~100 lines

#### 7. `transaction()` context manager
**Location:** `src/utils/db_helpers.py`
**Impact:** 26 commit sites
**LOC Savings:** ~50 lines + correctness improvement

### Low Priority (Nice to Have)

#### 8. Replace print() with logger.*()
**Location:** Throughout file
**Impact:** 27 print statements
**LOC Savings:** Minimal (same LOC, better structure)

#### 9. Remove duplicate imports
**Location:** Throughout file
**Impact:** 9 + 13 + 4 = 26 duplicate imports
**LOC Savings:** ~26 lines

---

## Impact Assessment

### By Number of Functions Affected

| Pattern | Functions Affected | LOC Savings | Risk Level |
|---------|-------------------|-------------|------------|
| JSON Response Building | 47 (100%) | 500-800 | Medium |
| Error Handling Boilerplate | 47 (100%) | 300 | Medium |
| Connection Management | 40 (85%) | 200 | Medium |
| Project Selection Check | 13 (28%) | 50 | Low |
| Project Name Sanitization | 5 (11%) | 10 | Very Low |
| Cursor Creation | 30 (64%) | 100 | Low |
| Transaction Management | 26 commits | 50 | Medium |
| Import Duplication | 26 imports | 26 | Zero |
| Logging Statements | 27 prints | 0 | Very Low |
| Session ID Retrieval | 15+ calls | 30 | Medium |

**Total Estimated LOC Savings:** ~1,266 - 1,566 lines

### By Priority Level

#### 🔴 HIGH Priority (Do First)
1. **Project Name Sanitization** - Simple, high-confidence win
2. **JSON Response Building** - Massive impact, standardizes API
3. **Connection Management** - Prevents bugs (connection leaks)

**Estimated Time:** 2-3 days
**Risk:** Low-Medium
**Impact:** Immediate code quality improvement + bug prevention

#### 🟡 MEDIUM Priority (Do Second)
4. **Project Selection Check** - Reduces boilerplate
5. **Error Handling Decorator** - Large impact but needs careful testing
6. **Cursor/Query Helpers** - Consistency improvement
7. **Transaction Management** - Correctness improvement

**Estimated Time:** 3-4 days
**Risk:** Medium
**Impact:** Significant maintainability improvement

#### 🟢 LOW Priority (Nice to Have)
8. **Logging Standardization** - Quality of life
9. **Import Cleanup** - Cosmetic

**Estimated Time:** 1 day
**Risk:** Very Low
**Impact:** Minimal but clean

---

## Recommended Refactoring Sequence

### Phase 1: Foundation (Week 1)
**Goal:** Extract pure utility functions with no behavior changes

1. **Day 1-2:** Create `src/utils/project_utils.py`
   - Extract `sanitize_project_name()`
   - Add comprehensive tests
   - Replace 5 call sites

2. **Day 3-4:** Create `src/utils/response_builder.py`
   - Implement `ResponseBuilder` class
   - Add tests for all response types
   - Replace 10 simple cases as proof of concept

3. **Day 5:** Create `src/utils/db_helpers.py`
   - Extract `transaction()` context manager
   - Add tests
   - Document `_get_db_for_project()` usage

**Deliverable:** 3 new utility modules with tests, 15+ tools refactored

### Phase 2: Standardization (Week 2)
**Goal:** Standardize patterns across all tools

4. **Day 6-7:** Database Connection Standardization
   - Audit all 47 tools for connection patterns
   - Migrate Pattern A and B to Pattern C (context manager)
   - Remove direct `psycopg2.connect()` calls

5. **Day 8-9:** Response Builder Rollout
   - Replace all `json.dumps()` with `ResponseBuilder.*()`
   - Ensure consistent error format across all tools
   - Update documentation

6. **Day 10:** Testing & Validation
   - Run full test suite
   - Test all 47 tools manually
   - Fix any regressions

**Deliverable:** All 47 tools using standardized patterns

### Phase 3: Advanced Patterns (Week 3)
**Goal:** Add decorators to reduce boilerplate

7. **Day 11-12:** Create `src/utils/decorators.py`
   - Implement `@require_project_selection`
   - Implement `@tool_error_handler`
   - Add comprehensive tests

8. **Day 13-14:** Decorator Rollout
   - Apply `@require_project_selection` to 13 tools
   - Apply `@tool_error_handler` to all 47 tools
   - Remove redundant try-except blocks

9. **Day 15:** Cleanup
   - Remove duplicate imports
   - Replace print() with logger.*()
   - Update documentation

**Deliverable:** Fully refactored codebase with decorators

---

## Testing Strategy

### For Each Refactoring:

1. **Write Tests First**
   ```python
   # test_project_utils.py
   def test_sanitize_project_name():
       assert sanitize_project_name("My-Project!") == "my_project"
       assert sanitize_project_name("test___name") == "test_name"
       assert len(sanitize_project_name("x" * 100)) <= 32
   ```

2. **Verify No Behavior Change**
   - Run existing test suite before and after
   - Compare outputs for same inputs
   - Check connection pool stats

3. **Integration Testing**
   - Test all affected tools end-to-end
   - Verify MCP protocol compliance
   - Check database state consistency

### Regression Prevention:

- Create snapshot tests for complex tools
- Add property-based tests for utilities
- Monitor connection pool usage
- Check for memory leaks

---

## Risk Mitigation

### High-Risk Changes:
1. **Connection Management** - Could cause leaks or deadlocks
   - **Mitigation:** Thorough testing, gradual rollout, monitor connection pool

2. **Error Handling Decorator** - Could change error response format
   - **Mitigation:** Ensure backward compatibility, version responses

3. **Transaction Management** - Could cause data corruption
   - **Mitigation:** Test rollback behavior, use database snapshots

### Medium-Risk Changes:
4. **Response Builder** - Could break MCP clients
   - **Mitigation:** Maintain response schema, add validation

5. **Project Selection Decorator** - Could block valid tool calls
   - **Mitigation:** Comprehensive validation testing

### Low-Risk Changes:
6. **Project Name Sanitization** - Pure function
7. **Import Cleanup** - No runtime changes
8. **Logging** - No functional impact

---

## Code Quality Metrics

### Current State:
- **Total Lines:** 9,925
- **Duplication:** ~15-20% (estimated)
- **Cyclomatic Complexity:** High (many nested try-except)
- **Import Redundancy:** 26 duplicate imports
- **Connection Patterns:** 3 different patterns in use

### Target State (After Refactoring):
- **Total Lines:** ~7,900 (-20%)
- **Duplication:** <5%
- **Cyclomatic Complexity:** Medium (decorators reduce nesting)
- **Import Redundancy:** 0
- **Connection Patterns:** 1 standard pattern

### Maintainability Improvements:
- ✅ Easier to add new tools (copy decorator pattern)
- ✅ Consistent error messages (better UX)
- ✅ Fewer connection leaks (more reliable)
- ✅ Better testability (smaller functions)
- ✅ Clearer code intent (decorators are self-documenting)

---

## Next Steps

### Immediate Actions:
1. **Review this report** with team
2. **Prioritize phases** based on current sprint goals
3. **Create tickets** for Phase 1 tasks
4. **Set up testing infrastructure** for regression prevention

### Before Starting Refactoring:
- [ ] Create feature branch: `refactor/dry-improvements`
- [ ] Set up test coverage monitoring
- [ ] Document current behavior (snapshot tests)
- [ ] Get stakeholder approval for changes

### Success Criteria:
- [ ] All tests pass after refactoring
- [ ] Code coverage maintained or improved
- [ ] No connection pool leaks
- [ ] MCP protocol compliance verified
- [ ] Documentation updated
- [ ] Code review approved

---

## Appendix: Pattern Frequency Table

| Pattern | Occurrences | Location Examples |
|---------|-------------|-------------------|
| `json.dumps()` | 145 | Throughout all tools |
| `try-except` | 99+ | All tool functions |
| `cursor = conn.execute()` | 91 | Database operations |
| `cur.execute()` | 61 | Database operations |
| `conn.commit()` | 26 | Transaction commits |
| `print(..., file=sys.stderr)` | 27 | Logging/debugging |
| `with conn.cursor() as cur:` | 12 | Best practice usage |
| `_check_project_selection_required()` | 13 | Memory tools |
| `_get_project_for_context()` | 12 | Project resolution |
| `@mcp.tool()` | 47 | All tool definitions |
| `import json` (in function) | 9 | Tool functions |
| `import re` (in function) | 13 | Tool functions |
| Project name sanitization | 5 | Project management tools |
| `psycopg2.connect()` | 4 | Direct connections |
| `adapter.close()` | 5 | Manual connection cleanup |
| `conn.close()` | 9 | Manual connection cleanup |

---

**Report Generated:** 2025-11-17
**Analyzer:** Claude Code (Sonnet 4.5)
**Methodology:** Static code analysis via Grep + Read tools
**Confidence:** High (based on direct code inspection)
