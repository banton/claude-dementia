# Essential Fixes - Action Plan
**Date:** 2025-11-09
**Estimated Time:** 1-2 hours
**Impact:** High (security, test reliability, documentation)

## Overview

This document provides step-by-step instructions to implement the 4 ESSENTIAL fixes identified in the pragmatic refactoring evaluation.

---

## Fix 1: Schema Name Validation (5 minutes)

### Problem
Schema names are derived from directory names without validation. Theoretical SQL injection risk.

### Location
`/Users/banton/Sites/claude-dementia/postgres_adapter.py:130-150`

### Current Code
```python
def _get_schema_name(self) -> str:
    """
    Auto-generate schema name from project context.

    Schema names are derived from git repository name or directory basename.
    This provides automatic schema isolation per project without manual configuration.
    """
    # Try environment variable first
    schema = os.getenv('DEMENTIA_SCHEMA')
    if schema:
        return schema.lower().replace('-', '_')

    # Try git repository name
    try:
        result = subprocess.run(
            ['git', 'config', '--get', 'remote.origin.url'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            repo_url = result.stdout.strip()
            # Extract repo name from URL
            repo_name = repo_url.rstrip('.git').split('/')[-1]
            return repo_name.lower().replace('-', '_')
    except:
        pass

    # Fall back to directory basename
    cwd = os.getcwd()
    dir_name = Path(cwd).name
    return dir_name.lower().replace('-', '_')
```

### Fixed Code
```python
def _get_schema_name(self) -> str:
    """
    Auto-generate schema name from project context.

    Schema names are derived from git repository name or directory basename.
    This provides automatic schema isolation per project without manual configuration.

    Returns:
        str: Validated schema name (lowercase alphanumeric + underscores)

    Raises:
        ValueError: If schema name contains invalid characters
    """
    # Try environment variable first
    schema = os.getenv('DEMENTIA_SCHEMA')
    if schema:
        schema = schema.lower().replace('-', '_')
    else:
        # Try git repository name
        try:
            result = subprocess.run(
                ['git', 'config', '--get', 'remote.origin.url'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                repo_url = result.stdout.strip()
                # Extract repo name from URL
                repo_name = repo_url.rstrip('.git').split('/')[-1]
                schema = repo_name.lower().replace('-', '_')
            else:
                # Fall back to directory basename
                cwd = os.getcwd()
                dir_name = Path(cwd).name
                schema = dir_name.lower().replace('-', '_')
        except:
            # Fall back to directory basename
            cwd = os.getcwd()
            dir_name = Path(cwd).name
            schema = dir_name.lower().replace('-', '_')

    # SECURITY: Validate schema name to prevent SQL injection
    # PostgreSQL schema names: 1-63 chars, start with letter, alphanumeric + underscore
    if not re.match(r'^[a-z][a-z0-9_]{0,62}$', schema):
        raise ValueError(
            f"Invalid schema name: '{schema}'. "
            f"Schema names must start with a letter and contain only "
            f"lowercase letters, numbers, and underscores (max 63 chars)."
        )

    return schema
```

### Test
```bash
# Add to tests/unit/test_postgres_adapter.py (create if doesn't exist)
cd /Users/banton/Sites/claude-dementia

# Run this test
python3 << 'EOF'
import re

def validate_schema_name(schema: str) -> bool:
    return bool(re.match(r'^[a-z][a-z0-9_]{0,62}$', schema))

# Valid names
assert validate_schema_name("my_project") == True
assert validate_schema_name("claude_dementia") == True
assert validate_schema_name("test123") == True

# Invalid names
assert validate_schema_name("DROP TABLE;") == False
assert validate_schema_name("1starts_with_number") == False
assert validate_schema_name("has-dashes") == False
assert validate_schema_name("UPPERCASE") == False
assert validate_schema_name("a" * 64) == False  # Too long

print("✅ All schema validation tests passed")
EOF
```

### Implementation Steps
1. Open `postgres_adapter.py`
2. Add `import re` to imports (line 30)
3. Replace `_get_schema_name()` method with fixed version
4. Test with: `python3 claude_mcp_hybrid.py` (should still work)
5. Commit: `git commit -m "fix(security): add schema name validation to prevent SQL injection"`

---

## Fix 2: Fix 6 Failing Tests (30-60 minutes)

### Problem
6 unit tests in `test_mcp_session_store.py` are failing (21% failure rate).

### Location
`/Users/banton/Sites/claude-dementia/tests/unit/test_mcp_session_store.py`

### Investigation
```bash
cd /Users/banton/Sites/claude-dementia

# Run failing tests with verbose output
python3 -m pytest tests/unit/test_mcp_session_store.py -v --tb=long

# Expected output will show:
# - Why tests are failing
# - What assertions are breaking
# - Stack traces for debugging
```

### Common Failure Patterns

#### Pattern 1: Missing Environment Variables
**Error:** `DATABASE_URL environment variable not set`

**Fix:**
```python
# tests/unit/test_mcp_session_store.py
import os
import pytest

@pytest.fixture(autouse=True)
def setup_env():
    """Set up test environment variables."""
    os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/test')
    os.environ.setdefault('DEMENTIA_SCHEMA', 'test_schema')
    yield
    # Cleanup not needed (tests use isolated schema)
```

#### Pattern 2: PostgreSQL vs SQLite Assumptions
**Error:** Tests written for SQLite but running against PostgreSQL

**Fix:**
```python
# If tests use SQLite-specific features (datetime formats, etc)
# Update to use PostgreSQL-compatible code

# Before (SQLite)
cursor.execute("SELECT datetime('now')")

# After (PostgreSQL)
cursor.execute("SELECT NOW()")
```

#### Pattern 3: Session Store API Changed
**Error:** `AttributeError: 'SessionStore' object has no attribute 'create_session'`

**Fix:**
1. Check actual API in `mcp_session_cleanup.py` or similar
2. Update tests to match current implementation
3. Or fix implementation to match test expectations (if tests are correct)

### Implementation Steps
1. Run tests: `pytest tests/unit/test_mcp_session_store.py -v --tb=long`
2. Read error messages carefully
3. Fix one test at a time (commit after each fix)
4. Ensure all tests pass: `pytest tests/unit/test_mcp_session_store.py -v`
5. Commit: `git commit -m "test: fix 6 failing unit tests in test_mcp_session_store.py"`

### Acceptance Criteria
```bash
# All tests should pass
pytest tests/unit/test_mcp_session_store.py -v

# Expected output:
# ============================= test session starts ==============================
# ...
# tests/unit/test_mcp_session_store.py::test_should_create_session_with_unique_id_when_initialized PASSED
# tests/unit/test_mcp_session_store.py::test_should_persist_session_to_database_when_created PASSED
# tests/unit/test_mcp_session_store.py::test_should_mark_session_expired_when_24_hours_passed PASSED
# tests/unit/test_mcp_session_store.py::test_should_update_last_active_when_session_accessed PASSED
# tests/unit/test_mcp_session_store.py::test_should_delete_expired_sessions_when_cleanup_runs PASSED
# tests/unit/test_mcp_session_store.py::test_should_handle_duplicate_session_id_by_regenerating PASSED
# ...
# ============================== 6 passed in 0.5s ================================
```

---

## Fix 3: Session Expiry Assertion (5 minutes)

### Problem
Test expects `400` but implementation returns `401` for expired sessions.

### Location
`/Users/banton/Sites/claude-dementia/tests/integration/test_mcp_session_persistence.py:255`

### Current Code
```python
async def test_middleware_should_reject_expired_session():
    # ... test setup ...
    response = await middleware(request, call_next)
    assert response.status_code == 400  # Expected: Bad Request
```

### Investigation
Run test to see actual behavior:
```bash
pytest tests/integration/test_mcp_session_persistence.py::test_middleware_should_reject_expired_session -v --tb=short
```

### Expected Output
```
AssertionError: assert 401 == 400
+ where 401 = <starlette.responses.JSONResponse object>.status_code
```

### Decision: Which is Correct?
- **400 Bad Request** = Client sent invalid/malformed request
- **401 Unauthorized** = Client's credentials (session) are invalid/expired

**Correct:** `401 Unauthorized` is more accurate for expired sessions.

### Fixed Code
```python
async def test_middleware_should_reject_expired_session():
    """Expired session should be rejected with 401 Unauthorized."""
    # ... test setup ...

    response = await middleware(request, call_next)

    # FIXED: Expired session returns 401 (Unauthorized), not 400 (Bad Request)
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/json"

    # Verify error message mentions expiration
    response_data = json.loads(response.body)
    assert "expired" in response_data.get("error", "").lower() or \
           "inactive" in response_data.get("error", "").lower()
```

### Implementation Steps
1. Open `tests/integration/test_mcp_session_persistence.py`
2. Find line 255 (or search for `test_middleware_should_reject_expired_session`)
3. Change `assert response.status_code == 400` to `401`
4. Add assertion for error message content
5. Run test: `pytest tests/integration/test_mcp_session_persistence.py::test_middleware_should_reject_expired_session -v`
6. Commit: `git commit -m "test: fix session expiry assertion (401 not 400)"`

---

## Fix 4: Document Pool Size Rationale (2 minutes)

### Problem
Pool size was reduced from 10 → 3 without documentation. Future developers might "optimize" back to 10.

### Location
`/Users/banton/Sites/claude-dementia/postgres_adapter.py:85-86`

### Current Code
```python
self.pool = psycopg2.pool.SimpleConnectionPool(
    1, 3,  # Allow 3 concurrent connections (request + lazy checks + finalization)
    self.database_url,
    cursor_factory=RealDictCursor,
    connect_timeout=15
)
```

### Fixed Code
```python
# CRITICAL: Connection pool sizing for Neon + stdio mode
# - Neon free tier: 10 connection limit (shared across all clients)
# - Stdio mode: Single-threaded, max 3 concurrent uses (rare)
#   1. Main request processing
#   2. Background cleanup/validation (rare)
#   3. Schema initialization (startup only)
# - DO NOT increase beyond 3 without testing (causes pool exhaustion)
# - See: DEM-42 "Connection pool exhaustion bug" (2025-11-08)
self.pool = psycopg2.pool.SimpleConnectionPool(
    1,  # min_connections: 1 (always keep one alive)
    3,  # max_connections: 3 (sufficient for stdio, prevents exhaustion)
    self.database_url,
    cursor_factory=RealDictCursor,
    connect_timeout=15
)
```

### Alternative (More Concise)
```python
# CRITICAL: Pool size = 3 (DO NOT INCREASE)
# - Stdio mode is single-threaded, max 3 concurrent uses
# - Neon free tier has 10 connection limit (shared)
# - Higher values cause "connection pool exhausted" errors
# - See commit ce86fc7 for historical context (2025-11-08)
self.pool = psycopg2.pool.SimpleConnectionPool(
    1, 3,  # min=1, max=3 (tuned for stdio + Neon)
    self.database_url,
    cursor_factory=RealDictCursor,
    connect_timeout=15
)
```

### Implementation Steps
1. Open `postgres_adapter.py`
2. Find line 85-86 (pool initialization)
3. Add comment block above pool initialization
4. Commit: `git commit -m "docs: document connection pool size rationale"`

---

## Verification Checklist

After implementing all 4 fixes:

```bash
# 1. Schema validation (should not raise error)
python3 -c "
from postgres_adapter import PostgreSQLAdapter
adapter = PostgreSQLAdapter()
print(f'✅ Schema validation works: {adapter.schema}')
"

# 2. Unit tests (should all pass)
pytest tests/unit/test_mcp_session_store.py -v
# Expected: 6/6 passed (was 0/6)

# 3. Integration tests (should all pass)
pytest tests/integration/test_mcp_session_persistence.py -v
# Expected: 8/8 passed (was 7/8)

# 4. Documentation (visual inspection)
grep -A 5 "CRITICAL.*Pool" postgres_adapter.py
# Should show comment explaining pool size

# 5. Full test suite
pytest tests/ -v
# Expected: 29/29 passed (was 23/29)
```

---

## Git Workflow

```bash
# Create feature branch
git checkout -b fix/essential-refactoring-fixes

# Fix 1: Schema validation
# ... implement fix ...
git add postgres_adapter.py
git commit -m "fix(security): add schema name validation to prevent SQL injection

- Add regex validation for schema names (alphanumeric + underscore)
- Raise ValueError for invalid names (prevents SQL injection)
- Minimal risk but trivial fix (5 min)"

# Fix 2: Failing tests
# ... implement fix ...
git add tests/unit/test_mcp_session_store.py
git commit -m "test: fix 6 failing unit tests in test_mcp_session_store.py

- Update tests to match current PostgreSQL implementation
- Fix environment variable setup in fixtures
- All 6 tests now passing (was 0/6)"

# Fix 3: Session expiry assertion
# ... implement fix ...
git add tests/integration/test_mcp_session_persistence.py
git commit -m "test: fix session expiry assertion (401 not 400)

- Expired sessions correctly return 401 Unauthorized
- Updated test to match actual behavior
- Added assertion for error message content"

# Fix 4: Document pool size
# ... implement fix ...
git add postgres_adapter.py
git commit -m "docs: document connection pool size rationale

- Explain why pool size = 3 (not 10)
- Prevent future 'optimization' regression
- Reference historical bug (ce86fc7)"

# Push and create PR (if using PRs)
git push origin fix/essential-refactoring-fixes

# Or merge directly to main (if solo)
git checkout main
git merge fix/essential-refactoring-fixes
git push origin main
```

---

## Success Metrics

### Before
- ❌ 6 failing unit tests (21% failure rate)
- ❌ 1 failing integration test (12.5% failure rate)
- ⚠️ Theoretical SQL injection risk
- ⚠️ Undocumented connection pool change

### After
- ✅ 0 failing tests (100% pass rate)
- ✅ Schema name validation (defense-in-depth)
- ✅ Documented pool size (prevents regression)
- ✅ Codebase ready for refactoring (tests are safety net)

### Time Investment
- **Estimated:** 1-2 hours
- **Actual:** _____ hours (fill in after completion)
- **ROI:** Prevents hours of debugging, enables safe refactoring

---

## Next Steps

After completing these essential fixes:

1. **Run full test suite:** `pytest tests/ -v` (should be 29/29 passing)
2. **Consider valuable improvements** (see PRAGMATIC_REFACTORING_EVALUATION.md, Category 2)
3. **Resume feature development** with confidence (tests are now trustworthy)

**Remember:** These fixes take 1-2 hours but save weeks of debugging later. Do them now.
