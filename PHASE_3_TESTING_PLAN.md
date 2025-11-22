# Phase 3 Testing Plan: Async Tool Migration Validation

**Objective:** Validate that async-converted MCP tools work correctly, perform better than sync versions, and maintain backward compatibility.

---

## 1. Pre-Migration Baseline

### 1.1 Establish Performance Baseline (Current State)
**Purpose:** Document current performance to validate improvements post-migration.

**Actions:**
```bash
# Record baseline metrics before any changes
python3 -m pytest tests/test_systematic_tool_check.py -v --durations=10 > baseline_performance.txt

# Capture current response times
curl -X POST https://dementia-mcp-7f4vf.ondigitalocean.app/execute \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "context_dashboard", "arguments": {}}' \
  --write-out "\nTime: %{time_total}s\n" \
  > baseline_context_dashboard.txt
```

**Expected Baseline (with session middleware disabled):**
- Simple tools: 280-640ms
- Complex tools: 1-2s
- Database queries: 50-200ms each

**Success Criteria:**
- Async versions should be ≤ baseline times
- Database-heavy tools should show 30-50% improvement (no blocking)

---

## 2. Unit Testing Strategy

### 2.1 Test Infrastructure Components

**File:** `tests/test_async_infrastructure.py`

```python
import pytest
from claude_mcp_hybrid_sessions import AsyncAutoClosingConnection
from postgres_adapter_async import PostgreSQLAdapterAsync

@pytest.mark.asyncio
async def test_async_connection_wrapper():
    """Test AsyncAutoClosingConnection context manager."""
    adapter = PostgreSQLAdapterAsync()
    pool = await adapter.get_pool()

    async with AsyncAutoClosingConnection(pool, adapter.schema) as conn:
        result = await conn.execute("SELECT 1 as test")
        assert result[0]['test'] == 1

    await adapter.close()

@pytest.mark.asyncio
async def test_async_db_for_project():
    """Test _get_db_for_project async helper."""
    from claude_mcp_hybrid_sessions import _get_db_for_project

    async with await _get_db_for_project('test_project') as conn:
        result = await conn.execute("SELECT current_schema() as schema")
        assert 'dementia_' in result[0]['schema']

@pytest.mark.asyncio
async def test_placeholder_conversion():
    """Test SQL placeholder conversion if using automated conversion."""
    from claude_mcp_hybrid_sessions import convert_sql_placeholders

    # Test single placeholder
    assert convert_sql_placeholders("SELECT * FROM t WHERE id = %s") == \
           "SELECT * FROM t WHERE id = $1"

    # Test multiple placeholders
    assert convert_sql_placeholders("INSERT INTO t (a, b) VALUES (%s, %s)") == \
           "INSERT INTO t (a, b) VALUES ($1, $2)"
```

### 2.2 Test Individual Tool Conversion

**Pattern for each converted tool:**

```python
@pytest.mark.asyncio
async def test_lock_context_async():
    """Test lock_context tool works with async adapter."""
    from claude_mcp_hybrid_sessions import lock_context

    # Test basic locking
    result = await lock_context(
        content="Test API spec",
        topic="test_async_lock",
        project="test"
    )

    result_data = json.loads(result[0].text)
    assert result_data['status'] == 'success'
    assert result_data['topic'] == 'test_async_lock'
    assert 'version' in result_data

@pytest.mark.asyncio
async def test_recall_context_async():
    """Test recall_context retrieves locked contexts."""
    from claude_mcp_hybrid_sessions import lock_context, recall_context

    # Lock a context
    await lock_context(
        content="Recall test content",
        topic="test_recall_async",
        project="test"
    )

    # Recall it
    result = await recall_context(
        topic="test_recall_async",
        project="test"
    )

    result_data = json.loads(result[0].text)
    assert 'Recall test content' in result_data['content']
```

---

## 3. Integration Testing

### 3.1 End-to-End Tool Workflow Tests

**File:** `tests/test_async_tool_workflows.py`

```python
@pytest.mark.asyncio
async def test_context_lifecycle_async():
    """Test complete context lifecycle: lock -> recall -> search -> unlock."""
    from claude_mcp_hybrid_sessions import (
        lock_context, recall_context, search_contexts, unlock_context
    )

    project = "test_workflow"
    topic = "api_spec_async"

    # 1. Lock context
    lock_result = await lock_context(
        content="API specification for async endpoints",
        topic=topic,
        tags="api,async,test",
        project=project
    )
    assert json.loads(lock_result[0].text)['status'] == 'success'

    # 2. Recall context
    recall_result = await recall_context(topic=topic, project=project)
    recalled = json.loads(recall_result[0].text)
    assert recalled['topic'] == topic
    assert 'async endpoints' in recalled['content']

    # 3. Search for context
    search_result = await search_contexts(
        query="async endpoints",
        project=project
    )
    search_data = json.loads(search_result[0].text)
    assert len(search_data['results']) > 0

    # 4. Unlock context
    unlock_result = await unlock_context(topic=topic, project=project)
    assert json.loads(unlock_result[0].text)['deleted_count'] >= 1

@pytest.mark.asyncio
async def test_session_management_workflow():
    """Test session creation, project selection, and context access."""
    from claude_mcp_hybrid_sessions import (
        list_projects, select_project_for_session, get_last_handover
    )

    # 1. List projects
    projects_result = await list_projects()
    projects = json.loads(projects_result[0].text)
    assert len(projects) > 0

    # 2. Select project
    select_result = await select_project_for_session(name="test_session")
    assert json.loads(select_result[0].text)['success'] == True

    # 3. Get handover (if exists)
    handover_result = await get_last_handover(project="test_session")
    # Should not error even if no handover exists
    assert handover_result is not None
```

### 3.2 Concurrent Operations Test

**File:** `tests/test_async_concurrency.py`

```python
@pytest.mark.asyncio
async def test_concurrent_tool_execution():
    """Test multiple tools can run concurrently without blocking."""
    import asyncio
    from claude_mcp_hybrid_sessions import (
        lock_context, search_contexts, context_dashboard
    )

    # Run 10 operations concurrently
    tasks = [
        lock_context(
            content=f"Concurrent test {i}",
            topic=f"concurrent_test_{i}",
            project="concurrency_test"
        )
        for i in range(5)
    ] + [
        search_contexts(query="concurrent", project="concurrency_test")
        for _ in range(3)
    ] + [
        context_dashboard(project="concurrency_test")
        for _ in range(2)
    ]

    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(*tasks)
    elapsed = asyncio.get_event_loop().time() - start_time

    # All should succeed
    assert len(results) == 10

    # Should complete in parallel (< 3s for 10 operations)
    # If serial, would take 5-10s+ with blocking
    assert elapsed < 3.0, f"Concurrent ops took {elapsed}s (should be <3s)"
```

---

## 4. Performance Testing

### 4.1 Response Time Benchmarks

**File:** `tests/test_async_performance.py`

```python
@pytest.mark.asyncio
async def test_tool_response_times():
    """Measure response times for common tools."""
    import time
    from claude_mcp_hybrid_sessions import (
        lock_context, recall_context, search_contexts,
        context_dashboard, check_contexts
    )

    results = {}

    # Test lock_context
    start = time.time()
    await lock_context(
        content="Performance test content",
        topic="perf_test",
        project="perf"
    )
    results['lock_context'] = (time.time() - start) * 1000

    # Test recall_context
    start = time.time()
    await recall_context(topic="perf_test", project="perf")
    results['recall_context'] = (time.time() - start) * 1000

    # Test search_contexts
    start = time.time()
    await search_contexts(query="performance", project="perf")
    results['search_contexts'] = (time.time() - start) * 1000

    # Test context_dashboard
    start = time.time()
    await context_dashboard(project="perf")
    results['context_dashboard'] = (time.time() - start) * 1000

    # Test check_contexts
    start = time.time()
    await check_contexts(text="implementing API", project="perf")
    results['check_contexts'] = (time.time() - start) * 1000

    # Print results
    for tool, ms in results.items():
        print(f"{tool}: {ms:.2f}ms")

    # All should be <1s
    for tool, ms in results.items():
        assert ms < 1000, f"{tool} took {ms:.2f}ms (should be <1000ms)"

@pytest.mark.asyncio
async def test_database_connection_pool_efficiency():
    """Test connection pool handles concurrent requests efficiently."""
    import asyncio
    from postgres_adapter_async import PostgreSQLAdapterAsync

    adapter = PostgreSQLAdapterAsync()

    async def query_task():
        return await adapter.execute_query("SELECT COUNT(*) FROM context_locks")

    # Run 20 concurrent queries
    start = asyncio.get_event_loop().time()
    results = await asyncio.gather(*[query_task() for _ in range(20)])
    elapsed = asyncio.get_event_loop().time() - start

    # Should complete in <500ms with connection pooling
    # Without pooling, would take 2-3s+ serially
    assert elapsed < 0.5, f"20 concurrent queries took {elapsed}s (should be <0.5s)"
    assert len(results) == 20

    await adapter.close()
```

### 4.2 Load Testing

**File:** `tests/test_async_load.py`

```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_sustained_load():
    """Test system handles sustained load without degradation."""
    import asyncio
    from claude_mcp_hybrid_sessions import lock_context, search_contexts

    durations = []

    for batch in range(10):  # 10 batches of 10 operations
        start = asyncio.get_event_loop().time()

        tasks = [
            lock_context(
                content=f"Load test batch {batch} item {i}",
                topic=f"load_test_{batch}_{i}",
                project="load_test"
            )
            for i in range(5)
        ] + [
            search_contexts(query=f"batch {batch}", project="load_test")
            for _ in range(5)
        ]

        await asyncio.gather(*tasks)
        duration = asyncio.get_event_loop().time() - start
        durations.append(duration)

        await asyncio.sleep(0.1)  # Small pause between batches

    # Check for degradation (last batch shouldn't be >2x slower than first)
    avg_early = sum(durations[:3]) / 3
    avg_late = sum(durations[-3:]) / 3

    assert avg_late < avg_early * 2, \
        f"Performance degraded: early={avg_early:.2f}s, late={avg_late:.2f}s"
```

---

## 5. Regression Testing

### 5.1 Existing Test Suite

**Action:** Ensure all existing tests still pass after async conversion.

```bash
# Run full test suite
python3 -m pytest tests/ -v --tb=short

# Expected results:
# - tests/test_postgres_adapter_async.py: 12/12 PASS
# - tests/test_session_store_async.py: 13/13 PASS
# - tests/test_async_infrastructure.py: NEW, all PASS
# - tests/test_async_tool_workflows.py: NEW, all PASS
# - tests/test_async_performance.py: NEW, all PASS
```

### 5.2 Systematic Tool Check (Updated for Async)

**File:** `tests/test_systematic_tool_check_async.py`

```python
"""
Systematic tool validation for async MCP tools.
Updated version of test_systematic_tool_check.py for async migration.
"""

@pytest.mark.asyncio
async def test_all_tools_systematic():
    """Test all 30+ tools systematically."""

    tools_to_test = [
        # Context management
        ('lock_context', {'content': 'test', 'topic': 'test'}),
        ('recall_context', {'topic': 'test'}),
        ('search_contexts', {'query': 'test'}),
        ('check_contexts', {'text': 'test'}),
        ('unlock_context', {'topic': 'test'}),

        # Session management
        ('list_projects', {}),
        ('create_project', {'name': 'test_systematic'}),
        ('switch_project', {'name': 'test_systematic'}),
        ('select_project_for_session', {'name': 'test_systematic'}),

        # Health & inspection
        ('context_dashboard', {}),
        ('health_check_and_repair', {}),
        ('inspect_schema', {}),

        # ... add all 30+ tools
    ]

    results = {}

    for tool_name, args in tools_to_test:
        try:
            tool_func = getattr(
                __import__('claude_mcp_hybrid_sessions'),
                tool_name
            )

            result = await tool_func(**args)
            results[tool_name] = 'PASS'

        except Exception as e:
            results[tool_name] = f'FAIL: {str(e)}'

    # Print summary
    passed = sum(1 for v in results.values() if v == 'PASS')
    total = len(results)

    print(f"\n{'='*60}")
    print(f"Systematic Tool Check: {passed}/{total} PASS")
    print(f"{'='*60}")

    for tool, status in results.items():
        status_emoji = '✅' if status == 'PASS' else '❌'
        print(f"{status_emoji} {tool}: {status}")

    # All should pass
    assert passed == total, f"Only {passed}/{total} tools passed"
```

---

## 6. Production Readiness Checks

### 6.1 Pre-Deployment Checklist

```markdown
## Phase 3 Deployment Checklist

### Code Quality
- [ ] All tools converted to async (30+ tools)
- [ ] All SQL placeholders converted (%s → $1)
- [ ] All `conn.commit()` calls removed
- [ ] All tools use `async def` and `await`
- [ ] AsyncAutoClosingConnection implemented
- [ ] _get_db_for_project converted to async

### Testing
- [ ] Unit tests: 100% pass rate
- [ ] Integration tests: All workflows pass
- [ ] Performance tests: All tools <1s response time
- [ ] Concurrency tests: 20+ concurrent ops <500ms
- [ ] Load tests: No degradation over 100+ ops
- [ ] Regression tests: All existing tests pass

### Performance Validation
- [ ] Baseline captured before migration
- [ ] Post-migration metrics collected
- [ ] Response times ≤ baseline
- [ ] No event loop blocking detected
- [ ] Connection pool efficiency validated

### Documentation
- [ ] PHASE_3_MIGRATION_GUIDE.md complete
- [ ] PHASE_3_TESTING_PLAN.md followed
- [ ] Code comments updated for async patterns
- [ ] README.md updated with async notes

### Deployment
- [ ] Feature branch: feature/async-migration-phase3
- [ ] All commits follow conventional format
- [ ] CI/CD pipeline passes
- [ ] Staged deployment to test environment
- [ ] Production deployment plan approved
```

### 6.2 Monitoring Post-Deployment

**Metrics to track:**

```python
# Add to server_hosted.py or monitoring dashboard

import time
import prometheus_client

# Track tool execution times
tool_latency = prometheus_client.Histogram(
    'mcp_tool_latency_seconds',
    'MCP tool execution latency',
    ['tool_name', 'async_version']
)

# Track concurrent operations
concurrent_ops = prometheus_client.Gauge(
    'mcp_concurrent_operations',
    'Number of concurrent MCP operations'
)

# Track database pool usage
db_pool_usage = prometheus_client.Gauge(
    'mcp_db_pool_usage',
    'Database connection pool usage',
    ['state']  # 'active', 'idle'
)
```

**Alert thresholds:**
- Tool latency >2s: WARNING
- Tool latency >5s: CRITICAL
- DB pool exhaustion: CRITICAL
- Error rate >1%: WARNING

---

## 7. Testing Execution Plan

### Week 1: Infrastructure & Unit Tests
**Day 1-2:** Implement AsyncAutoClosingConnection + async helpers
**Day 3-4:** Write infrastructure unit tests
**Day 5:** Convert first batch of 5 tools + unit tests

### Week 2: Tool Conversion & Integration Tests
**Day 1-3:** Convert remaining 25+ tools
**Day 4:** Write integration workflow tests
**Day 5:** Performance testing + baseline comparison

### Week 3: Load Testing & Production Prep
**Day 1-2:** Load testing + concurrency validation
**Day 3:** Regression testing + systematic tool check
**Day 4:** Documentation + deployment checklist
**Day 5:** Staged deployment to test environment

---

## 8. Success Criteria

### Must Pass:
✅ All unit tests pass (100% coverage for converted tools)
✅ All integration tests pass
✅ All performance tests show ≤ baseline latency
✅ Systematic tool check: 30/30 PASS
✅ No event loop blocking detected
✅ Connection pool efficiency >90%

### Nice to Have:
🎯 30-50% latency reduction on database-heavy tools
🎯 100+ concurrent operations without degradation
🎯 Zero production incidents in first week

---

## 9. Rollback Plan

**If critical issues detected:**

1. **Immediate:** Revert to `main` branch (session middleware disabled)
2. **Short-term:** Fix issues in `feature/async-migration-phase3`
3. **Long-term:** Re-deploy after validation

**Rollback command:**
```bash
# Emergency rollback
git checkout main
git push origin main --force-with-lease

# Or use git revert if already merged
git revert <merge-commit-sha>
git push origin main
```

**Data safety:** All async changes are backward-compatible with existing PostgreSQL schema.

---

## Summary

This testing plan ensures Phase 3 migration is:
- **Correct:** All tools work as expected
- **Performant:** Response times meet targets
- **Reliable:** No regressions or blocking issues
- **Production-ready:** Comprehensive validation before deployment

**Estimated effort:** 2-3 weeks with systematic approach.
