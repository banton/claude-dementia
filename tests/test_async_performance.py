"""
Performance tests for async tools.

Measures response times and validates performance improvements.
"""

import pytest
import time
import json


@pytest.mark.asyncio
async def test_tool_response_times():
    """Measure response times for common tools."""
    from claude_mcp_async_sessions import (
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
    print("\nPerformance Results:")
    for tool, ms in results.items():
        print(f"  {tool}: {ms:.2f}ms")

    # All should be <1s (1000ms)
    for tool, ms in results.items():
        assert ms < 1000, f"{tool} took {ms:.2f}ms (should be <1000ms)"


@pytest.mark.asyncio
async def test_database_connection_pool_efficiency():
    """Test connection pool handles concurrent requests efficiently."""
    import asyncio
    from postgres_adapter_async import PostgreSQLAdapterAsync

    adapter = PostgreSQLAdapterAsync()
    pool = await adapter.get_pool()

    async def execute_query(query_id: int):
        """Execute a simple query."""
        conn = await pool.acquire()
        try:
            result = await conn.fetch("SELECT $1 as id", query_id)
            return result[0]['id']
        finally:
            await pool.release(conn)

    # Execute 50 concurrent queries
    start = time.time()
    tasks = [execute_query(i) for i in range(50)]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start

    # All should complete
    assert len(results) == 50
    assert results == list(range(50))

    # Should complete quickly with connection pooling
    print(f"\n50 concurrent queries: {elapsed*1000:.2f}ms")
    assert elapsed < 1.0, f"50 queries took {elapsed}s (should be <1s)"

    await adapter.close()


@pytest.mark.asyncio
async def test_large_context_operations():
    """Test performance with large context content."""
    from claude_mcp_async_sessions import lock_context, recall_context

    # Create 100KB context
    large_content = "x" * 100_000

    # Lock large context
    start = time.time()
    await lock_context(
        content=large_content,
        topic="large_test",
        project="perf"
    )
    lock_time = (time.time() - start) * 1000

    # Recall large context
    start = time.time()
    result = await recall_context(topic="large_test", project="perf")
    recall_time = (time.time() - start) * 1000

    print(f"\nLarge context (100KB):")
    print(f"  Lock: {lock_time:.2f}ms")
    print(f"  Recall: {recall_time:.2f}ms")

    # Should handle large content reasonably fast
    assert lock_time < 2000, f"Lock took {lock_time:.2f}ms (should be <2s)"
    assert recall_time < 2000, f"Recall took {recall_time:.2f}ms (should be <2s)"


@pytest.mark.asyncio
async def test_batch_operations_performance():
    """Test performance of batch operations vs individual operations."""
    from claude_mcp_async_sessions import lock_context, batch_lock_contexts
    import asyncio

    project = "perf_batch"

    # Test individual operations
    start = time.time()
    for i in range(10):
        await lock_context(
            content=f"Individual {i}",
            topic=f"individual_{i}",
            project=project
        )
    individual_time = time.time() - start

    # Test batch operation
    contexts = [
        {"topic": f"batch_{i}", "content": f"Batch {i}"}
        for i in range(10)
    ]

    start = time.time()
    await batch_lock_contexts(contexts=contexts, project=project)
    batch_time = time.time() - start

    print(f"\n10 operations:")
    print(f"  Individual: {individual_time*1000:.2f}ms")
    print(f"  Batch: {batch_time*1000:.2f}ms")
    print(f"  Speedup: {individual_time/batch_time:.2f}x")

    # Batch should be significantly faster
    assert batch_time < individual_time, "Batch should be faster than individual"
