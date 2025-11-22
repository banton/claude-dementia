"""
Unit tests for PostgreSQLAdapterAsync.

Critical validation before async migration proceeds.
Created per EVALUATION_REPORT.md recommendation.
"""

import pytest
import asyncio
import os
from postgres_adapter_async import PostgreSQLAdapterAsync


@pytest.mark.asyncio
async def test_adapter_initialization():
    """Test adapter initializes correctly with schema detection."""
    adapter = PostgreSQLAdapterAsync()

    assert adapter.database_url is not None, "DATABASE_URL should be set"
    assert adapter.schema is not None, "Schema should be auto-detected"
    assert adapter._pool is None, "Pool should not be created until get_pool()"

    info = adapter.get_info()
    assert info['adapter_type'] == 'async'
    assert info['schema'] == adapter.schema

    await adapter.close()


@pytest.mark.asyncio
async def test_connection_pool_creation():
    """Test connection pool is created lazily and reused."""
    adapter = PostgreSQLAdapterAsync()

    # Pool should not exist yet
    assert adapter._pool is None

    # Get pool (lazy creation)
    pool1 = await adapter.get_pool()
    assert pool1 is not None
    assert adapter._pool is pool1

    # Get pool again (should reuse)
    pool2 = await adapter.get_pool()
    assert pool2 is pool1, "Should reuse existing pool"

    await adapter.close()
    assert adapter._pool is None, "Close should clear pool"


@pytest.mark.asyncio
async def test_connection():
    """Test database connection works."""
    adapter = PostgreSQLAdapterAsync()

    connected = await adapter.test_connection()
    assert connected is True, "Should connect to database"

    await adapter.close()


@pytest.mark.asyncio
async def test_execute_query_simple():
    """Test SELECT query execution with simple query."""
    adapter = PostgreSQLAdapterAsync()

    result = await adapter.execute_query("SELECT 1 as test")

    assert len(result) == 1, "Should return one row"
    assert result[0]['test'] == 1, "Should return correct value"
    assert isinstance(result[0], dict), "Should return dict, not asyncpg.Record"

    await adapter.close()


@pytest.mark.asyncio
async def test_execute_query_with_params():
    """Test SELECT query with $1, $2 placeholders."""
    adapter = PostgreSQLAdapterAsync()

    result = await adapter.execute_query(
        "SELECT $1::int as num, $2::text as txt",
        [42, "hello"]
    )

    assert len(result) == 1
    assert result[0]['num'] == 42
    assert result[0]['txt'] == "hello"

    await adapter.close()


@pytest.mark.asyncio
async def test_schema_creation():
    """Test schema and table creation."""
    adapter = PostgreSQLAdapterAsync()

    # Ensure schema exists
    await adapter.ensure_schema_exists()

    # Verify tables exist by querying information_schema
    result = await adapter.execute_query("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1
        ORDER BY table_name
    """, [adapter.schema])

    table_names = [row['table_name'] for row in result]

    # Check required tables exist
    assert 'sessions' in table_names, "sessions table should exist"
    assert 'context_locks' in table_names, "context_locks table should exist"
    assert 'memory_entries' in table_names, "memory_entries table should exist"
    assert 'file_tags' in table_names, "file_tags table should exist"
    assert 'context_archives' in table_names, "context_archives table should exist"

    await adapter.close()


@pytest.mark.asyncio
async def test_execute_update_insert():
    """Test INSERT query execution."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()

    # Insert test session
    result = await adapter.execute_update("""
        INSERT INTO sessions (id, project_name)
        VALUES ($1, $2)
        ON CONFLICT (id) DO NOTHING
    """, ["test_async_session_123", "test_project"])

    assert "INSERT" in result or "DO NOTHING" in result, "Should return status"

    # Verify inserted
    rows = await adapter.execute_query("""
        SELECT * FROM sessions WHERE id = $1
    """, ["test_async_session_123"])

    assert len(rows) > 0, "Should find inserted row"
    assert rows[0]['project_name'] == 'test_project'

    # Cleanup
    await adapter.execute_update("""
        DELETE FROM sessions WHERE id = $1
    """, ["test_async_session_123"])

    await adapter.close()


@pytest.mark.asyncio
async def test_execute_update_delete():
    """Test DELETE query execution."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()

    # Insert test data
    await adapter.execute_update("""
        INSERT INTO sessions (id, project_name)
        VALUES ($1, $2)
        ON CONFLICT (id) DO NOTHING
    """, ["test_delete_123", "test"])

    # Delete it
    result = await adapter.execute_update("""
        DELETE FROM sessions WHERE id = $1
    """, ["test_delete_123"])

    assert "DELETE" in result, "Should return DELETE status"

    # Verify deleted
    rows = await adapter.execute_query("""
        SELECT * FROM sessions WHERE id = $1
    """, ["test_delete_123"])

    assert len(rows) == 0, "Row should be deleted"

    await adapter.close()


@pytest.mark.asyncio
async def test_concurrent_queries():
    """Test multiple concurrent queries don't block each other."""
    adapter = PostgreSQLAdapterAsync()

    # Run multiple queries concurrently
    results = await asyncio.gather(
        adapter.execute_query("SELECT 1 as num"),
        adapter.execute_query("SELECT 2 as num"),
        adapter.execute_query("SELECT 3 as num"),
    )

    assert len(results) == 3
    assert results[0][0]['num'] == 1
    assert results[1][0]['num'] == 2
    assert results[2][0]['num'] == 3

    await adapter.close()


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling for invalid queries."""
    adapter = PostgreSQLAdapterAsync()

    # Invalid SQL should raise exception
    with pytest.raises(Exception):
        await adapter.execute_query("SELECT * FROM nonexistent_table_xyz")

    # Pool should still be usable after error
    result = await adapter.execute_query("SELECT 1 as test")
    assert result[0]['test'] == 1

    await adapter.close()


@pytest.mark.asyncio
async def test_schema_isolation():
    """Test queries use correct schema (search_path)."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()

    # Insert into sessions table
    await adapter.execute_update("""
        INSERT INTO sessions (id, project_name)
        VALUES ($1, $2)
        ON CONFLICT (id) DO NOTHING
    """, ["test_schema_isolation", "test"])

    # Query should find it (using correct schema)
    rows = await adapter.execute_query("""
        SELECT * FROM sessions WHERE id = $1
    """, ["test_schema_isolation"])

    assert len(rows) > 0, "Should find row in correct schema"

    # Cleanup
    await adapter.execute_update("""
        DELETE FROM sessions WHERE id = $1
    """, ["test_schema_isolation"])

    await adapter.close()


@pytest.mark.asyncio
async def test_placeholder_syntax():
    """Test asyncpg placeholder syntax ($1, $2) works correctly."""
    adapter = PostgreSQLAdapterAsync()

    # Test multiple parameters
    result = await adapter.execute_query("""
        SELECT
            $1::int as p1,
            $2::text as p2,
            $3::boolean as p3,
            $4::int as p4
    """, [100, "test", True, 200])

    assert result[0]['p1'] == 100
    assert result[0]['p2'] == "test"
    assert result[0]['p3'] is True
    assert result[0]['p4'] == 200

    await adapter.close()


if __name__ == '__main__':
    # Run tests directly
    pytest.main([__file__, '-v'])
