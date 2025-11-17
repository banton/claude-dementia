# Test Coverage Analysis Report
## Claude Dementia MCP Server

**Generated:** 2025-11-17
**Analyzed Codebase:** /home/user/claude-dementia
**Main Server File:** claude_mcp_hybrid_sessions.py (9,925 lines)

---

## Executive Summary

The Claude Dementia MCP server has **extensive but fragmented** test coverage with approximately **6,246 lines of test code** across **78+ test functions**. Testing follows a **mixed TDD approach** with both unit and integration tests, but several critical areas—including the **switch_project** function—have **limited comprehensive test coverage**.

### Key Findings

✅ **Strengths:**
- Strong session management test coverage (unit + integration)
- Good database isolation tests (PostgreSQL schema isolation)
- Comprehensive context locking tests (lock, unlock, update, recall)
- Performance benchmarks included
- Mix of unit and integration tests

⚠️ **Gaps:**
- **switch_project**: Only 2 tests (basic functionality, no comprehensive edge cases)
- Limited project management function coverage (create, delete, list)
- Missing tests for batch operations
- No tests for semantic search functions
- Limited error recovery scenarios
- Missing API endpoint integration tests for some tools

---

## Test Files Inventory

### Root Directory Tests (22 files, ~6,000 lines)

| Test File | Test Count | Focus Area | Type |
|-----------|-----------|------------|------|
| `test_project_isolation_fix.py` | 1 | **switch_project** persistence | Integration |
| `test_project_isolation_fix_unit.py` | 1 | **switch_project** DB reads | Unit |
| `test_active_context_engine.py` | 5 | Active context RLM | Unit |
| `test_active_context.py` | 1 | Context activation | Integration |
| `test_auto_migration.py` | 1 | DB schema migration | Integration |
| `test_cloud_services.py` | 3 | Voyage AI, OpenRouter APIs | Integration |
| `test_crud_workflow.py` | 1 | Lock → Update → Unlock flow | Integration |
| `test_database_tools.py` | 7 | query_database, inspect_database | Unit/Integration |
| `test_file_model_integration.py` | 6 | File semantic model, scan_codebase | Integration |
| `test_hosted_api.py` | 6 | FastAPI server endpoints | Integration |
| `test_lock_context_rlm.py` | 1 | Context locking with RLM | Unit |
| `test_mcp_integration.py` | 1 | MCP server integration | Integration |
| `test_migration_v4_1.py` | 6 | Database migration v4.0→v4.1 | Integration |
| `test_phase2a_tools.py` | 5 | Phase 2a feature tools | Integration |
| `test_phase5_tools.py` | 4 | Phase 5 feature tools | Integration |
| `test_postgres_operations.py` | 2 | PostgreSQL schema isolation | Integration |
| `test_sql_write_operations.py` | 7 | SQL execution, write ops | Unit |
| `test_sync_memory.py` | 6 | Memory synchronization | Integration |
| `test_tool_descriptions.py` | 3 | MCP tool metadata | Unit |
| `test_unlock_context.py` | 6 | Context unlocking | Unit |
| `test_update_context.py` | 6 | Context updates | Unit |
| `test_embedding_models.py` | 0 | (No test functions found) | - |

### tests/ Directory (3 files, ~250 lines)

| Test File | Test Count | Focus Area | Type |
|-----------|-----------|------------|------|
| `tests/unit/test_mcp_session_store.py` | 8 | PostgreSQL session store | Unit |
| `tests/unit/test_session_cleanup_task.py` | ~4 | Session cleanup background task | Unit |
| `tests/integration/test_mcp_session_persistence.py` | 6 | Session persistence across deployments | Integration |
| `tests/test_starlette_mcp_integration.py` | ~3 | Starlette MCP middleware | Integration |

---

## MCP Tools Coverage Map

### 🔍 Main MCP Tools in claude_mcp_hybrid_sessions.py

| Tool Function | Line # | Tests | Coverage Status |
|---------------|--------|-------|-----------------|
| **switch_project** | 1995 | ✅ 2 tests | ⚠️ **LIMITED** - basic only |
| create_project | 2200 | ❌ None found | ⚠️ **MISSING** |
| list_projects | 2276 | ❌ None found | ⚠️ **MISSING** |
| get_project_info | 2357 | ❌ None found | ⚠️ **MISSING** |
| delete_project | 2466 | ❌ None found | ⚠️ **MISSING** |
| select_project_for_session | 2540 | ❌ None found | ⚠️ **MISSING** |
| wake_up | 2717 | ✅ Tested | ✅ **GOOD** |
| sleep | 2990 | ✅ Tested | ✅ **GOOD** |
| get_last_handover | 3298 | ✅ Tested | ✅ **GOOD** |
| lock_context | 3554 | ✅ 8+ tests | ✅ **EXCELLENT** |
| recall_context | 3807 | ✅ 6+ tests | ✅ **GOOD** |
| unlock_context | 3967 | ✅ 6 tests | ✅ **GOOD** |
| update_context | 4183 | ✅ 6 tests | ✅ **GOOD** |
| batch_lock_contexts | 4293 | ❌ None found | ⚠️ **MISSING** |
| batch_recall_contexts | 4394 | ❌ None found | ⚠️ **MISSING** |
| search_contexts | 4529 | ✅ Partial | ⚠️ **PARTIAL** |
| sync_project_memory | 4931 | ✅ 6 tests | ✅ **GOOD** |
| query_database | 5046 | ✅ 7 tests | ✅ **EXCELLENT** |
| execute_sql | 5550 | ✅ 7 tests | ✅ **GOOD** |
| manage_workspace_table | 5837 | ✅ Tested | ✅ **GOOD** |
| check_contexts | 6141 | ❌ None found | ⚠️ **MISSING** |
| explore_context_tree | 6303 | ❌ None found | ⚠️ **MISSING** |
| context_dashboard | 6503 | ❌ None found | ⚠️ **MISSING** |
| generate_embeddings | 7269 | ✅ Tested | ✅ **GOOD** |
| semantic_search_contexts | 7392 | ❌ None found | ⚠️ **MISSING** |

### 📊 Coverage Statistics

- **Total MCP Tools:** ~25
- **Tools with Tests:** 14 (56%)
- **Tools without Tests:** 11 (44%)
- **Tools with Excellent Coverage:** 4 (16%)
- **Tools with Good Coverage:** 10 (40%)
- **Tools with Limited/Missing Coverage:** 11 (44%)

---

## Detailed Analysis: switch_project Coverage

### Existing Tests for switch_project

#### 1. `test_project_isolation_fix.py` (Integration Test)

**File:** `/home/user/claude-dementia/test_project_isolation_fix.py`
**Lines:** 163
**Test Function:** `test_project_isolation_persistence()`

**What It Tests:**
- ✅ Switch to project 'test_project_a'
- ✅ Verify switch success
- ✅ Simulate MCP statelessness (clear in-memory cache)
- ✅ Verify `_get_project_for_context()` reads from database
- ✅ Lock context without explicit project parameter
- ✅ Verify context locked to correct project
- ✅ Switch to 'test_project_b'
- ✅ Verify project isolation (contexts don't leak between projects)

**Coverage Level:** **Basic functional test + isolation verification**

**Gaps:**
- ❌ No invalid project name handling
- ❌ No empty/null project name tests
- ❌ No special character sanitization tests
- ❌ No SQL injection attempt tests
- ❌ No concurrent switch tests
- ❌ No switch rollback on failure
- ❌ No schema creation failure tests
- ❌ No permission/access control tests

#### 2. `test_project_isolation_fix_unit.py` (Unit Test)

**File:** `/home/user/claude-dementia/test_project_isolation_fix_unit.py`
**Lines:** 140
**Test Function:** `test_active_project_database_persistence()`

**What It Tests:**
- ✅ Manually set active_project in sessions table
- ✅ Clear in-memory cache
- ✅ Verify `_get_project_for_context()` reads from database
- ✅ Verify persistence across "HTTP requests"

**Coverage Level:** **Database persistence only**

**Gaps:**
- ❌ Doesn't test the full `switch_project()` function
- ❌ Only tests `_get_project_for_context()` helper
- ❌ No validation logic testing
- ❌ No error handling testing

### switch_project Function Analysis

**Location:** `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py:1995`
**Estimated Size:** ~111 lines (based on next function at line 2106)

**Known Functionality (from REFACTORING_REVIEW_GUIDE.md):**
```python
async def switch_project(name: str) -> str:
    # Line 2022: Sanitize project name
    safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())

    # Line 2026-2048: Update session store
    if not _session_store or not _local_session_id:
        # Initialize session

    # Update active_project in database
    await _session_store.update_project(...)

    # Line 2050-2064: Get/create schema
    schema_name = f"dementia_{hash(project_name)}"
    adapter = _get_cached_adapter(schema_name)
    adapter.ensure_schema_exists()

    # Line 2066-2091: Get database stats
    contexts_count, memories_count = ...

    # Line 2093-2106: Return success JSON
    return json.dumps({
        "success": True,
        "message": f"✅ Switched to project '{name}'",
        "project": name,
        "stats": {...}
    })
```

**Complexity Factors:**
- Session store initialization
- Database session updates
- Schema name hashing
- Schema creation/verification
- Database stats queries
- Error handling for each step
- JSON response formatting

---

## Testing Frameworks and Patterns

### Frameworks Used

1. **pytest** (primary)
   - Used in: `tests/unit/`, `tests/integration/`
   - Fixtures for database setup/teardown
   - `@pytest.mark.asyncio` for async tests
   - `@pytest.fixture` for test dependencies

2. **unittest.mock** (mocking)
   - `Mock`, `MagicMock`, `AsyncMock`, `patch`
   - Used for database connection mocking
   - Used for API call mocking (Voyage AI, OpenRouter)

3. **asyncio.run()** (standalone tests)
   - Used in root-level test files
   - Direct async function execution
   - Manual test orchestration

### Testing Patterns

#### Pattern 1: TDD Red-Green-Refactor
```python
# Example: test_database_tools.py
def test_query_database_basic_select():
    """Test 1: Basic SELECT query works"""
    # RED: Write test first (expected to fail)
    # GREEN: Implement query_database() to pass
    # REFACTOR: Clean up implementation
```

#### Pattern 2: Integration Tests with Real PostgreSQL
```python
# Example: test_mcp_session_persistence.py
@pytest.fixture(scope="module")
def db_adapter():
    """Real PostgreSQL adapter for integration testing."""
    os.environ['DEMENTIA_SCHEMA'] = 'test_mcp_sessions'
    adapter = PostgreSQLAdapter()
    adapter.ensure_schema_exists()
    yield adapter
    # Cleanup: DROP SCHEMA CASCADE
```

#### Pattern 3: Deployment Simulation
```python
# Example: test_mcp_session_persistence.py
async def test_deployment_scenario_session_survives_restart(db_adapter):
    # 1. Create middleware v1 (pre-deployment)
    # 2. User creates session
    # 3. DEPLOYMENT: Destroy middleware v1, create v2
    # 4. User makes request with v2
    # 5. Assert: Session still works
```

#### Pattern 4: Fixed Time Testing (Deterministic)
```python
# Example: test_mcp_session_store.py
def test_should_mark_session_expired_when_24_hours_passed(mock_db_pool):
    fixed_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    session = store.create_session(created_at=fixed_time)
    expired = store.is_expired(
        session['session_id'],
        current_time=fixed_time + timedelta(hours=24, seconds=1)
    )
    assert expired is True
```

#### Pattern 5: Performance Testing
```python
# Example: test_mcp_session_persistence.py
def test_session_operations_meet_performance_requirements(session_store):
    # Warmup query to wake database
    warmup = session_store.create_session()

    # Test with warm database
    start = time.time()
    session = session_store.create_session()
    creation_time = (time.time() - start) * 1000

    assert creation_time < 500, f"Creation took {creation_time:.2f}ms"
```

#### Pattern 6: Schema Isolation Testing
```python
# Example: test_postgres_operations.py
def test_schema_isolation():
    # 1. Create schema for user_abc/project_innkeeper
    # 2. Insert data into schema 1
    # 3. Create schema for user_abc/project_linkedin
    # 4. Insert data into schema 2
    # 5. Verify: Schema 1 can't see Schema 2's data
    # 6. Verify: Schema 2 can't see Schema 1's data
```

---

## Database Operations Coverage

### PostgreSQL-Specific Tests

| Area | Tests | Status |
|------|-------|--------|
| Connection pooling | ✅ Tested | Good |
| Schema creation | ✅ Tested | Good |
| Schema isolation | ✅ Tested | Excellent |
| Parameterized queries | ✅ Tested | Good |
| SQL injection prevention | ✅ Tested | Good |
| Connection cleanup | ✅ Tested | Good |
| Error recovery | ⚠️ Partial | Limited |
| Transaction management | ⚠️ Partial | Limited |

### Session Management Tests

| Feature | Unit Tests | Integration Tests | Status |
|---------|-----------|-------------------|--------|
| Session creation | ✅ 2 tests | ✅ 1 test | Excellent |
| Session persistence | ✅ 2 tests | ✅ 2 tests | Excellent |
| Session expiration | ✅ 2 tests | ✅ 1 test | Good |
| Activity updates | ✅ 1 test | ✅ 1 test | Good |
| Cleanup expired | ✅ 1 test | ✅ 1 test | Good |
| Deployment survival | ❌ None | ✅ 1 test | Good |
| Duplicate ID handling | ✅ 1 test | ❌ None | Partial |

---

## Critical Gaps in Test Coverage

### 🔴 High Priority (Before Refactoring)

1. **switch_project Edge Cases**
   - ❌ Invalid/malicious project names
   - ❌ Empty/null project names
   - ❌ Extremely long project names
   - ❌ Unicode/special characters
   - ❌ Schema creation failures
   - ❌ Database connection failures
   - ❌ Concurrent switches

2. **Project Management Functions**
   - ❌ `create_project()` - No tests found
   - ❌ `delete_project()` - No tests found
   - ❌ `list_projects()` - No tests found
   - ❌ `get_project_info()` - No tests found
   - ❌ `select_project_for_session()` - No tests found

3. **Batch Operations**
   - ❌ `batch_lock_contexts()` - No tests found
   - ❌ `batch_recall_contexts()` - No tests found

4. **Semantic Search**
   - ❌ `semantic_search_contexts()` - No tests found
   - ❌ `generate_embeddings()` - Limited coverage

### 🟡 Medium Priority

5. **Context Discovery Tools**
   - ❌ `check_contexts()` - No tests found
   - ❌ `explore_context_tree()` - No tests found
   - ❌ `context_dashboard()` - No tests found

6. **Error Recovery**
   - ⚠️ Network failure recovery (Voyage AI, OpenRouter)
   - ⚠️ Database deadlock handling
   - ⚠️ Partial transaction rollback
   - ⚠️ Connection pool exhaustion

7. **Concurrency**
   - ⚠️ Concurrent context locks
   - ⚠️ Concurrent project switches
   - ⚠️ Session cleanup race conditions

### 🟢 Low Priority

8. **Performance Benchmarks**
   - ⚠️ More comprehensive performance tests
   - ⚠️ Load testing (many concurrent sessions)
   - ⚠️ Memory leak detection
   - ⚠️ Connection pool efficiency

---

## Specific switch_project Test Gaps

### Critical Missing Tests (Before Refactoring)

```python
# 1. Invalid Input Validation
async def test_switch_project_empty_name():
    """Should reject empty project name"""
    result = await switch_project("")
    assert "error" in result

async def test_switch_project_null_name():
    """Should reject None project name"""
    result = await switch_project(None)
    assert "error" in result

async def test_switch_project_sql_injection():
    """Should sanitize SQL injection attempts"""
    result = await switch_project("'; DROP TABLE sessions; --")
    # Should sanitize to: _drop_table_sessions_
    assert "success" in result
    # Verify sessions table still exists

async def test_switch_project_unicode():
    """Should handle Unicode project names"""
    result = await switch_project("プロジェクト")
    assert "success" in result

async def test_switch_project_very_long_name():
    """Should handle very long names (>255 chars)"""
    result = await switch_project("a" * 1000)
    assert "success" in result or "error" in result

# 2. Database Error Handling
async def test_switch_project_database_connection_failure():
    """Should handle DB connection failures gracefully"""
    with patch('postgres_adapter.PostgreSQLAdapter') as mock:
        mock.side_effect = psycopg2.OperationalError("Connection failed")
        result = await switch_project("test_project")
        assert "error" in result
        assert "Connection" in result

async def test_switch_project_schema_creation_failure():
    """Should handle schema creation failures"""
    # Mock ensure_schema_exists to raise exception
    result = await switch_project("test_project")
    assert "error" in result

async def test_switch_project_permission_denied():
    """Should handle permission errors"""
    # Mock database to raise PermissionError
    result = await switch_project("test_project")
    assert "error" in result
    assert "permission" in result.lower()

# 3. Session Management Edge Cases
async def test_switch_project_no_active_session():
    """Should initialize session if none exists"""
    global _local_session_id
    _local_session_id = None
    result = await switch_project("test_project")
    assert "success" in result
    assert _local_session_id is not None

async def test_switch_project_expired_session():
    """Should handle expired sessions"""
    # Create expired session
    result = await switch_project("test_project")
    # Should create new session automatically

# 4. Concurrency Tests
async def test_switch_project_concurrent_switches():
    """Should handle concurrent switches safely"""
    import asyncio
    results = await asyncio.gather(
        switch_project("project_a"),
        switch_project("project_b"),
        switch_project("project_c"),
    )
    assert all("success" in r or "error" in r for r in results)

# 5. State Verification Tests
async def test_switch_project_persists_to_database():
    """Verify active_project is written to database"""
    await switch_project("test_project")
    # Clear in-memory cache
    _active_projects.clear()
    # Read from database
    project = _get_project_for_context()
    assert project == "test_project"

async def test_switch_project_updates_in_memory_cache():
    """Verify active_project is cached in memory"""
    await switch_project("test_project")
    assert _active_projects.get(_local_session_id) == "test_project"

async def test_switch_project_schema_exists_after_switch():
    """Verify schema is created and accessible"""
    await switch_project("test_project")
    # Try to query the schema
    adapter = _get_cached_adapter("dementia_<hash>")
    # Should not raise exception

# 6. Stats Verification
async def test_switch_project_returns_stats():
    """Should return database stats in response"""
    result = await switch_project("test_project")
    data = json.loads(result)
    assert "stats" in data
    assert "contexts" in data["stats"]
    assert "memories" in data["stats"]

async def test_switch_project_stats_accuracy():
    """Stats should reflect actual database state"""
    # Create some test data
    await lock_context("test", "test_topic", project="test_project")
    result = await switch_project("test_project")
    data = json.loads(result)
    assert data["stats"]["contexts"] >= 1

# 7. Sanitization Tests
async def test_switch_project_name_sanitization():
    """Should sanitize project names correctly"""
    test_cases = [
        ("My-Project", "my_project"),
        ("Test@Project#123", "test_project_123"),
        ("UPPERCASE", "uppercase"),
        ("with spaces", "with_spaces"),
    ]
    for input_name, expected_safe_name in test_cases:
        result = await switch_project(input_name)
        data = json.loads(result)
        # Verify sanitized name is used
```

### Test Coverage Goals for switch_project

| Category | Current | Target | Tests Needed |
|----------|---------|--------|--------------|
| Happy path | 2 | 3 | +1 |
| Input validation | 0 | 8 | +8 |
| Error handling | 0 | 5 | +5 |
| Concurrency | 0 | 3 | +3 |
| State verification | 2 | 6 | +4 |
| Performance | 0 | 2 | +2 |
| **TOTAL** | **4** | **27** | **+23** |

---

## Recommendations

### Before Refactoring switch_project

1. **Write Missing Edge Case Tests** (RED Phase)
   - Create `test_switch_project_comprehensive.py`
   - Implement all 23+ missing tests listed above
   - Ensure tests fail (RED) to validate they catch issues

2. **Fix Bugs Revealed by Tests** (GREEN Phase)
   - Run new tests and document failures
   - Fix bugs one at a time
   - Ensure all tests pass before refactoring

3. **Add Test Fixtures**
   ```python
   @pytest.fixture
   def mock_postgres_adapter():
       """Mock PostgreSQL adapter for error testing"""

   @pytest.fixture
   def test_session_with_project():
       """Pre-configured session with active project"""

   @pytest.fixture
   def empty_database():
       """Clean database state for isolation tests"""
   ```

4. **Create Test Data Helpers**
   ```python
   def create_test_project(name: str, with_data: bool = False):
       """Helper to create test projects consistently"""

   def assert_project_isolated(project_a: str, project_b: str):
       """Helper to verify project isolation"""
   ```

### General Testing Improvements

1. **Add pytest Configuration**
   ```ini
   # pytest.ini
   [pytest]
   testpaths = tests
   python_files = test_*.py
   python_classes = Test*
   python_functions = test_*
   asyncio_mode = auto
   markers =
       unit: Unit tests
       integration: Integration tests
       slow: Slow tests (>1s)
   ```

2. **Separate Test Requirements**
   ```txt
   # requirements-test.txt
   pytest>=7.4.0
   pytest-asyncio>=0.21.0
   pytest-cov>=4.1.0
   pytest-mock>=3.11.0
   ```

3. **Add Coverage Reporting**
   ```bash
   pytest --cov=. --cov-report=html --cov-report=term-missing
   ```

4. **Create Test Documentation**
   - Document test patterns in TESTING_GUIDE.md
   - Add examples for common test scenarios
   - Document fixture usage

---

## Test Execution Commands

### Run All Tests
```bash
# All tests
python3 -m pytest tests/ -v

# Root directory tests
python3 -m pytest test_*.py -v

# Specific test file
python3 -m pytest test_project_isolation_fix.py -v
```

### Run by Category
```bash
# Unit tests only
python3 -m pytest tests/unit/ -v

# Integration tests only
python3 -m pytest tests/integration/ -v

# Session management tests
python3 -m pytest -k "session" -v

# switch_project tests
python3 -m pytest -k "switch_project" -v
```

### Run with Coverage
```bash
# Generate HTML coverage report
python3 -m pytest --cov=. --cov-report=html tests/

# Show missing lines
python3 -m pytest --cov=. --cov-report=term-missing tests/
```

### Run Standalone Tests
```bash
# Individual test scripts
python3 test_project_isolation_fix.py
python3 test_postgres_operations.py
python3 test_hosted_api.py
```

---

## Summary: Ready for Refactoring?

### switch_project Readiness: ⚠️ **NOT READY**

**Current State:**
- ✅ Basic functionality tested (2 tests)
- ✅ Database persistence verified
- ✅ Project isolation verified
- ❌ Edge cases not covered (0 tests)
- ❌ Error handling not tested (0 tests)
- ❌ Concurrency not tested (0 tests)
- ❌ Input validation not comprehensive

**Required Before Refactoring:**
1. Add 23+ comprehensive tests for switch_project
2. Verify all tests pass (GREEN phase)
3. Document expected behavior for edge cases
4. Add error recovery tests
5. Add concurrency tests

### Recommendation: **WRITE TESTS FIRST**

Following TDD principles:
1. **RED:** Write comprehensive tests (expect failures)
2. **GREEN:** Fix bugs revealed by tests
3. **REFACTOR:** Only after all tests pass

**Estimated Effort:**
- Write comprehensive tests: 4-6 hours
- Fix bugs revealed: 2-4 hours
- Verify coverage: 1 hour
- **Total:** 7-11 hours before refactoring

---

## Appendix: Test File Details

### Session Management Tests (Excellent Coverage)

**Unit Tests:** `/home/user/claude-dementia/tests/unit/test_mcp_session_store.py`
- test_should_create_session_with_unique_id_when_initialized
- test_should_persist_session_to_database_when_created
- test_should_mark_session_expired_when_24_hours_passed
- test_should_update_last_active_when_session_accessed
- test_should_delete_expired_sessions_when_cleanup_runs
- test_should_handle_duplicate_session_id_by_regenerating
- test_should_return_none_for_invalid_session_id

**Integration Tests:** `/home/user/claude-dementia/tests/integration/test_mcp_session_persistence.py`
- test_should_create_session_in_database_when_initialized
- test_should_survive_session_store_restart
- test_should_update_activity_and_extend_expiration
- test_should_cleanup_expired_sessions_only
- test_middleware_should_create_session_on_initialize
- test_middleware_should_reject_expired_session
- test_deployment_scenario_session_survives_restart
- test_session_operations_meet_performance_requirements

### Context Locking Tests (Excellent Coverage)

**Files:**
- `test_lock_context_rlm.py` - RLM preview generation
- `test_unlock_context.py` - Unlock operations
- `test_update_context.py` - Update operations
- `test_crud_workflow.py` - Full lock→update→unlock flow

### Database Tools Tests (Excellent Coverage)

**File:** `test_database_tools.py`
- test_query_database_basic_select
- test_query_database_with_params
- test_query_database_blocks_unsafe
- test_query_database_formats
- test_inspect_database_overview
- test_inspect_database_schema
- test_inspect_database_contexts

---

**Report End**

**Next Steps:**
1. Review this analysis with the team
2. Prioritize missing tests for switch_project
3. Create `test_switch_project_comprehensive.py`
4. Follow TDD: RED → GREEN → REFACTOR
5. Do not refactor until test coverage is comprehensive

**Document Version:** 1.0
**Last Updated:** 2025-11-17
