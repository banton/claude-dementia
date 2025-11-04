# Testing Deployment Changes Without Deploying

## Problem Statement

Deployment-related changes (session persistence, state management, connection pooling) are critical to test but traditionally require actual deployments to verify. This creates slow feedback loops and risks production issues.

**Example**: DEM-30 (Persistent MCP Sessions) needed to verify sessions survive server restarts. Without this strategy, we'd need to:
1. Deploy to production
2. Wait for deployment to complete
3. Test manually
4. If broken, fix and repeat

This approach is too slow and risky.

## Solution: Local Integration Testing with Real Database

### Core Principle

**Simulate deployment scenarios locally using real infrastructure (PostgreSQL), but with isolated test data.**

### Strategy Components

#### 1. Test Database Isolation

Use schema-based multi-tenancy to isolate test data:

```python
# Use dedicated test schema
os.environ['DEMENTIA_SCHEMA'] = 'test_mcp_sessions'

# Initialize with real database
adapter = PostgreSQLAdapter()
adapter.ensure_schema_exists()

# Run tests against real PostgreSQL
# ... tests run ...

# Cleanup: Drop test schema after all tests
DROP SCHEMA IF EXISTS test_mcp_sessions CASCADE
```

**Benefits**:
- Real database behavior (indexes, transactions, concurrency)
- Isolated from production/development data
- Easy cleanup after testing
- No mocks - catches real database issues

#### 2. Deployment Simulation

Simulate server restart by creating new object instances:

```python
# BEFORE DEPLOYMENT
middleware_v1 = MCPSessionPersistenceMiddleware(app, db_pool)
response1 = await middleware_v1.dispatch(init_request, mock_next)

# DEPLOYMENT HAPPENS (middleware_v1 destroyed)
# Simulate by creating NEW instance
middleware_v2 = MCPSessionPersistenceMiddleware(app, db_pool)

# AFTER DEPLOYMENT
response2 = await middleware_v2.dispatch(tool_request, mock_next)

# Assert: Session should still work
assert response2.status_code == 200
```

**Key Insight**: In-memory state is lost, but PostgreSQL state persists. Creating new instances simulates this exactly.

#### 3. Fixture Lifecycle Management

Use pytest fixtures with proper scopes:

```python
@pytest.fixture(scope="module")
def db_adapter():
    """Module-scoped adapter - shared across all tests"""
    adapter = PostgreSQLAdapter()
    yield adapter
    # Cleanup after ALL tests
    drop_test_schema()

@pytest.fixture
def session_store(db_adapter):
    """Function-scoped store - new instance per test"""
    store = PostgreSQLSessionStore(db_adapter.pool)
    yield store
    # Cleanup after EACH test
    delete_all_sessions()
```

**Scope Strategy**:
- `module`: Database adapter, connection pool (expensive to create)
- `function`: Store/middleware instances (cheap, simulates restart)

#### 4. Performance Testing with Cloud Database

Account for cloud database characteristics:

```python
def test_session_operations_meet_performance_requirements(session_store):
    # Warmup query - wake suspended Neon database (200-300ms)
    warmup = session_store.create_session()
    session_store.get_session(warmup['session_id'])

    # NOW test performance with warm database
    start = time.time()
    session = session_store.create_session()
    creation_time = (time.time() - start) * 1000

    # Lenient targets account for network variance
    assert creation_time < 500, f"Session creation took {creation_time:.2f}ms"
```

**Performance Philosophy**:
- Integration tests: Lenient targets (< 500ms), catch major regressions
- Production monitoring: Tight SLAs (p50/p95 latencies)
- Goal: Verify "reasonable" performance, not enforce SLAs

#### 5. Test Organization

```
tests/
├── unit/                           # Fast, mocked tests
│   └── test_mcp_session_store.py  # Business logic only
├── integration/                    # Real database tests
│   └── test_mcp_session_persistence.py  # Full flow with PostgreSQL
└── e2e/                           # End-to-end tests (future)
    └── test_mcp_client_flow.py    # Real MCP client tests
```

**Test Pyramid**:
- Unit tests: Fast (ms), mocked, business logic
- Integration tests: Medium (seconds), real database, deployment scenarios
- E2E tests: Slow (minutes), real clients, production-like

## Example: DEM-30 Integration Test Strategy

### Test Coverage

1. **Database Integration Tests**
   - ✅ Session creation in database
   - ✅ Session persistence across store restarts
   - ✅ Activity update extends expiration
   - ✅ Cleanup deletes only expired sessions

2. **Middleware Integration Tests**
   - ✅ Middleware creates session on initialize
   - ✅ Middleware rejects expired sessions

3. **Deployment Simulation Tests** (CRITICAL)
   - ✅ Full deployment scenario:
     1. User creates session (pre-deployment)
     2. Server deploys (middleware destroyed)
     3. User makes tool call (post-deployment)
     4. Session should still work ✅

4. **Performance Tests**
   - ✅ Session operations meet cloud database targets

### Test Results

```bash
$ python3 -m pytest tests/integration/test_mcp_session_persistence.py -v

test_should_create_session_in_database_when_initialized PASSED
test_should_survive_session_store_restart PASSED ← Simulates restart
test_should_update_activity_and_extend_expiration PASSED
test_should_cleanup_expired_sessions_only PASSED
test_middleware_should_create_session_on_initialize PASSED
test_middleware_should_reject_expired_session PASSED
test_deployment_scenario_session_survives_restart PASSED ← CRITICAL
test_session_operations_meet_performance_requirements PASSED

8 passed in 6.59s ✅
```

## When to Use This Strategy

### ✅ Use Integration Testing For:

- **State Persistence**: Sessions, cache, database state
- **Connection Pooling**: Database connections, HTTP clients
- **Middleware Behavior**: Request/response interception
- **Background Tasks**: Async jobs, scheduled tasks
- **Database Migrations**: Schema changes, data migrations
- **API Contract Changes**: Request/response validation

### ❌ Don't Use Integration Testing For:

- **Infrastructure Changes**: Load balancer, DNS, CDN
- **Environment Variables**: Configuration in production
- **Network Issues**: Firewall, VPC, routing
- **Third-party Services**: OAuth providers, payment gateways

*For these, use staging/canary deployments.*

## Best Practices

### 1. Clean Up Test Data

```python
@pytest.fixture
def session_store(db_adapter):
    store = PostgreSQLSessionStore(db_adapter.pool)
    yield store

    # Cleanup after EACH test
    conn = db_adapter.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mcp_sessions")
            conn.commit()
    finally:
        db_adapter.pool.putconn(conn)
```

### 2. Use Fixed Test Data

```python
# ✅ GOOD - Deterministic
fixed_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
session = session_store.create_session(created_at=fixed_time)

# ❌ BAD - Non-deterministic
session = session_store.create_session()  # Uses datetime.now()
```

### 3. Test Edge Cases

```python
def test_should_handle_duplicate_session_id_by_regenerating():
    """Test retry logic for UUID collisions"""
    ...

def test_should_cleanup_expired_sessions_only():
    """Test precision of cleanup (don't delete active sessions)"""
    ...
```

### 4. Document Assumptions

```python
def test_session_operations_meet_performance_requirements(session_store):
    """
    Cloud database performance targets with network latency variance:
    - Session creation: < 500ms (catches major issues)
    - Session lookup: < 200ms
    - Session update: < 200ms

    Note: First query may wake suspended database (200-300ms).
    These targets apply to subsequent queries (warm database).
    """
```

## Running Tests

### Local Development

```bash
# Run all integration tests
python3 -m pytest tests/integration/ -v

# Run specific test file
python3 -m pytest tests/integration/test_mcp_session_persistence.py -v

# Run specific test
python3 -m pytest tests/integration/test_mcp_session_persistence.py::test_deployment_scenario_session_survives_restart -v

# Run with coverage
python3 -m pytest tests/integration/ --cov=mcp_session_store --cov=mcp_session_middleware
```

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio

      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://postgres:test@localhost/test
          DEMENTIA_SCHEMA: test_mcp_sessions
        run: |
          python3 -m pytest tests/integration/ -v
```

## Troubleshooting

### Tests Fail Due to Database Connection

**Error**: `psycopg2.OperationalError: could not connect to server`

**Solution**:
```bash
# Check DATABASE_URL environment variable
echo $DATABASE_URL

# Verify database is running
psql $DATABASE_URL -c "SELECT 1"

# Check schema exists
psql $DATABASE_URL -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'test_mcp_sessions'"
```

### Tests Fail Due to Dirty Data

**Error**: `AssertionError: Expected 1 session, found 3`

**Solution**: Ensure cleanup fixtures are running
```python
# Add autouse=True to cleanup fixture
@pytest.fixture(autouse=True)
def cleanup_sessions(db_adapter):
    yield
    # Cleanup runs after EVERY test
    conn = db_adapter.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mcp_sessions")
            conn.commit()
    finally:
        db_adapter.pool.putconn(conn)
```

### Performance Tests Fail Intermittently

**Error**: `AssertionError: Session creation took 523.21ms (requirement: <500ms)`

**Solution**: Increase performance targets or skip in CI
```python
@pytest.mark.skip(reason="Performance varies in CI environment")
def test_session_operations_meet_performance_requirements():
    ...

# OR: Mark as flaky and allow retries
@pytest.mark.flaky(reruns=3)
def test_session_operations_meet_performance_requirements():
    ...
```

## Benefits of This Approach

✅ **Fast Feedback**: Tests run in seconds, not minutes (deployment time)
✅ **Safe**: Isolated test data, no production impact
✅ **Realistic**: Real database behavior, catches real issues
✅ **Repeatable**: Deterministic tests, same results every time
✅ **Comprehensive**: Can test edge cases difficult to reproduce in production
✅ **Developer Friendly**: Run tests locally during development
✅ **CI/CD Ready**: Easy to integrate into automated pipelines

## Conclusion

**Local integration testing with real infrastructure eliminates the need for deployment testing in most cases.**

This strategy enabled us to verify DEM-30 (session persistence across deployments) locally with 100% confidence before deploying to production.

**Key Takeaway**: Simulate deployment by creating new object instances. If state persists (PostgreSQL), it will survive real deployments. If state is lost (in-memory), tests will catch it.

---

**Related Documents**:
- DEM-30: Persistent MCP Session Storage
- tests/integration/test_mcp_session_persistence.py
- mcp_session_store.py
- mcp_session_middleware.py
