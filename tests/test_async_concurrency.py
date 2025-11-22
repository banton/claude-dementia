"""
Concurrency tests for async tools.

Validates that async tools can run concurrently without blocking.
"""

import pytest
import asyncio
import json


@pytest.mark.asyncio
async def test_concurrent_tool_execution():
    """Test multiple tools can run concurrently without blocking."""
    from claude_mcp_async_sessions import (
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

    # Should complete in parallel (< 5s for 10 operations)
    # If serial, would take 10s+ with blocking
    assert elapsed < 5.0, f"Concurrent ops took {elapsed}s (should be <5s)"


@pytest.mark.asyncio
async def test_concurrent_database_operations():
    """Test that concurrent database operations don't block each other."""
    from claude_mcp_async_sessions import _get_db_for_project
    import time

    async def db_operation(project_name: str, operation_id: int):
        """Perform a database operation."""
        async with await _get_db_for_project(project_name) as conn:
            # Simulate work with pg_sleep (100ms)
            await conn.execute("SELECT pg_sleep(0.1)")
            return operation_id

    # Run 10 concurrent operations
    start = time.time()
    tasks = [db_operation("test_concurrent", i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start

    # All operations should complete
    assert len(results) == 10
    assert results == list(range(10))

    # Should complete in ~100ms (parallel), not 1000ms (serial)
    # Allow up to 500ms for overhead
    assert elapsed < 0.5, f"10 concurrent 100ms ops took {elapsed}s (should be <0.5s)"


@pytest.mark.asyncio
async def test_connection_pool_under_load():
    """Test connection pool handles high concurrent load."""
    from claude_mcp_async_sessions import lock_context

    # Create 20 concurrent lock operations (more than default pool size)
    tasks = [
        lock_context(
            content=f"Load test {i}",
            topic=f"load_test_{i}",
            project="load_test"
        )
        for i in range(20)
    ]

    # Should not deadlock or timeout
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Count successes
    successes = sum(1 for r in results if not isinstance(r, Exception))

    # At least 90% should succeed (allow for some pool contention)
    assert successes >= 18, f"Only {successes}/20 operations succeeded"
