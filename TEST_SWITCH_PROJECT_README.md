# Comprehensive Test Suite for switch_project

## Overview

This document provides instructions for running the comprehensive test suite for the `switch_project` function in the Claude Dementia MCP Server.

**Test File:** `/home/user/claude-dementia/test_switch_project_comprehensive.py`

## Test Coverage

The test suite provides **24 comprehensive tests** covering all critical aspects of the `switch_project` function:

### Category Breakdown

| Category | Tests | Focus |
|----------|-------|-------|
| **Input Validation** | 8 | Empty/null names, SQL injection, Unicode, special chars |
| **Error Handling** | 5 | DB failures, permissions, rollback, missing session |
| **State Verification** | 6 | DB persistence, cache consistency, stats accuracy |
| **Concurrency** | 3 | Concurrent switches, race conditions, conflicts |
| **Performance** | 2 | Latency, load testing |
| **TOTAL** | **24** | **Comprehensive coverage** |

## Prerequisites

### 1. Install Test Dependencies

```bash
# Install pytest and testing tools
pip3 install pytest>=7.4.0
pip3 install pytest-asyncio>=0.21.0
pip3 install pytest-mock>=3.11.0

# Or install all at once
pip3 install pytest pytest-asyncio pytest-mock
```

### 2. Verify Installation

```bash
python3 -m pytest --version
```

Expected output:
```
pytest 7.4.x
```

## Running the Tests

### Run All Tests

```bash
# Verbose output with test names
python3 -m pytest test_switch_project_comprehensive.py -v

# Even more verbose (show print statements)
python3 -m pytest test_switch_project_comprehensive.py -vv -s
```

### Run Specific Test Category

```bash
# Input validation tests only
python3 -m pytest test_switch_project_comprehensive.py -k "validation" -v

# Error handling tests only
python3 -m pytest test_switch_project_comprehensive.py -k "error" -v

# State verification tests only
python3 -m pytest test_switch_project_comprehensive.py -k "database_persistence or cache" -v

# Concurrency tests only
python3 -m pytest test_switch_project_comprehensive.py -k "concurrent" -v

# Performance tests only
python3 -m pytest test_switch_project_comprehensive.py -k "performance or latency or load" -v
```

### Run Individual Test

```bash
# Specific test by name
python3 -m pytest test_switch_project_comprehensive.py::test_sql_injection_attempt -v
python3 -m pytest test_switch_project_comprehensive.py::test_empty_project_name -v
python3 -m pytest test_switch_project_comprehensive.py::test_concurrent_switches -v
```

### Run with Coverage

```bash
# Install coverage tool
pip3 install pytest-cov

# Generate coverage report
python3 -m pytest test_switch_project_comprehensive.py --cov=claude_mcp_hybrid_sessions --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Test Details

### Category 1: Input Validation (8 tests)

These tests verify that `switch_project` correctly sanitizes and validates input:

1. **test_empty_project_name** - Empty string handling
2. **test_null_project_name** - None/null input handling
3. **test_sql_injection_attempt** - SQL injection prevention
4. **test_unicode_characters** - Unicode/international character handling
5. **test_very_long_name** - Name truncation (>255 chars)
6. **test_special_characters** - Special character sanitization
7. **test_whitespace_handling** - Whitespace normalization
8. **test_numeric_only_name** - Numeric-only names

**Key Assertions:**
- Input is sanitized to `[a-z0-9_]` pattern
- SQL injection payloads are neutralized
- Names are truncated to ≤32 characters
- No crashes on invalid input

### Category 2: Error Handling (5 tests)

These tests verify graceful error handling:

1. **test_database_connection_failure** - Network/DB connection errors
2. **test_schema_creation_failure** - Schema query failures
3. **test_permission_error** - Database permission denied
4. **test_transaction_rollback** - Partial failure rollback
5. **test_missing_session_store** - Uninitialized session store

**Key Assertions:**
- All errors return JSON with `"success": false`
- Errors include descriptive `"error"` message
- No uncaught exceptions
- Server remains stable after errors

### Category 3: State Verification (6 tests)

These tests verify correct state management:

1. **test_database_persistence** - Active project persisted to DB
2. **test_cache_update** - In-memory cache updated
3. **test_cache_and_db_consistency** - Cache and DB stay in sync
4. **test_project_stats_accuracy** - Stats reflect DB state
5. **test_schema_creation_on_first_use** - New project workflow
6. **test_existing_project_switch** - Existing project workflow

**Key Assertions:**
- `update_session_project()` called with correct params
- `_active_projects` cache updated
- Database and cache have same value
- Stats counts are accurate

### Category 4: Concurrency (3 tests)

These tests verify thread safety:

1. **test_concurrent_switches** - Multiple concurrent switches
2. **test_race_condition_handling** - Race condition resilience
3. **test_session_conflict_resolution** - Conflict resolution

**Key Assertions:**
- No deadlocks under concurrency
- All concurrent operations complete
- Eventual consistency maintained
- No data corruption

### Category 5: Performance (2 tests)

These tests verify performance requirements:

1. **test_switch_latency** - Single switch latency < 500ms
2. **test_switch_under_load** - 100 switches avg latency < 100ms

**Key Assertions:**
- Reasonable response times
- No performance degradation under load
- No memory leaks

## Expected Results (RED Phase - TDD)

These tests are written **BEFORE** fixing any bugs in `switch_project`. Many tests are **expected to FAIL** initially:

### Expected Failures (RED Phase)

The following tests may fail initially and document issues to fix:

- ❌ **test_empty_project_name** - May fail due to empty schema name
- ❌ **test_null_project_name** - May fail with AttributeError
- ❌ **test_transaction_rollback** - No rollback logic currently
- ❌ **test_race_condition_handling** - Race conditions may exist
- ⚠️ **test_project_stats_accuracy** - Stats may be inaccurate

### Expected Passes (Current Implementation)

The following tests should pass with current implementation:

- ✅ **test_sql_injection_attempt** - Sanitization works
- ✅ **test_unicode_characters** - Regex strips non-ASCII
- ✅ **test_very_long_name** - Truncation works ([:32])
- ✅ **test_special_characters** - Regex sanitization works
- ✅ **test_database_persistence** - update_session_project called
- ✅ **test_cache_update** - Cache updated correctly

## TDD Workflow

### Phase 1: RED (Current)

```bash
# Run all tests - expect some failures
python3 -m pytest test_switch_project_comprehensive.py -v

# Document all failures
python3 -m pytest test_switch_project_comprehensive.py -v > test_results_red.txt 2>&1
```

**Goal:** Identify bugs and edge cases not currently handled.

### Phase 2: GREEN (Next)

Fix bugs one at a time until all tests pass:

```bash
# Fix a specific issue
# Edit claude_mcp_hybrid_sessions.py

# Re-run tests to verify fix
python3 -m pytest test_switch_project_comprehensive.py::test_empty_project_name -v

# Continue until all tests pass
python3 -m pytest test_switch_project_comprehensive.py -v
```

**Goal:** Make all tests pass with minimal code changes.

### Phase 3: REFACTOR (Final)

Refactor code while keeping all tests green:

```bash
# Refactor switch_project implementation
# Edit claude_mcp_hybrid_sessions.py

# Verify tests still pass after refactoring
python3 -m pytest test_switch_project_comprehensive.py -v

# Repeat until code is clean
```

**Goal:** Improve code quality without breaking functionality.

## Continuous Integration

### GitHub Actions Example

```yaml
name: Test switch_project

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-mock pytest-cov
      - name: Run comprehensive tests
        run: |
          python3 -m pytest test_switch_project_comprehensive.py -v --cov=claude_mcp_hybrid_sessions --cov-report=term-missing
```

## Troubleshooting

### Import Errors

```bash
# Error: ModuleNotFoundError: No module named 'pytest'
pip3 install pytest pytest-asyncio pytest-mock

# Error: ModuleNotFoundError: No module named 'claude_mcp_hybrid_sessions'
# Make sure you're running from the project root directory
cd /home/user/claude-dementia
python3 -m pytest test_switch_project_comprehensive.py -v
```

### Database Connection Errors

These tests **mock** database connections, so no real database is required. If you see database connection errors:

```bash
# Check that DATABASE_URL is not set for tests
unset DATABASE_URL

# Or set it to a test value
export DATABASE_URL="postgresql://test:test@localhost/test"
```

### AsyncIO Errors

```bash
# Error: SyntaxError: 'await' outside async function
# Make sure pytest-asyncio is installed
pip3 install pytest-asyncio

# Or mark tests with @pytest.mark.asyncio (already done in test file)
```

## Test Maintenance

### Adding New Tests

To add a new test to the suite:

1. Choose the appropriate category (validation, error, state, concurrency, performance)
2. Follow the existing test pattern:

```python
@pytest.mark.asyncio
async def test_my_new_test(test_session):
    """
    Test description.

    Expected behavior: ...
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        result = await switch_project("test_input")
        result_data = json.loads(result)

        assert result_data.get("success") == True
```

3. Run the new test:

```bash
python3 -m pytest test_switch_project_comprehensive.py::test_my_new_test -v
```

### Updating Existing Tests

When `switch_project` implementation changes:

1. Update test expectations if behavior intentionally changed
2. Keep tests that document edge cases even if currently failing
3. Add comments explaining why a test fails (if documenting known issues)

## References

- **TEST_COVERAGE_ANALYSIS.md** - Detailed coverage analysis
- **CLAUDE.md** - Development guide
- **docs/SWITCH_PROJECT_ARCHITECTURE.md** - Architecture details
- **REFACTORING_REVIEW_GUIDE.md** - Refactoring guidelines

## Contact

For questions about these tests:

1. Check TEST_COVERAGE_ANALYSIS.md for detailed requirements
2. Review existing tests in tests/unit/ for patterns
3. Follow TDD principles: RED → GREEN → REFACTOR

---

**Created:** 2025-11-17
**Test Count:** 24 comprehensive tests
**Coverage:** Input validation, error handling, state verification, concurrency, performance
**Status:** RED phase (tests written, awaiting fixes)
