"""
Unit tests for PostgreSQLAdapterAsync.
"""

import pytest
import asyncio
import os
from unittest.mock import MagicMock, patch, AsyncMock
from postgres_adapter_async import PostgreSQLAdapterAsync

# Mock asyncpg to avoid needing a real database connection for unit tests
@pytest.fixture
def mock_asyncpg_pool():
    with patch('asyncpg.create_pool', new_callable=AsyncMock) as mock_create_pool:
        # pool object itself should be a MagicMock because acquire() is synchronous
        # but returns an async context manager
        mock_pool = MagicMock()
        mock_create_pool.return_value = mock_pool
        
        # Mock connection context manager
        mock_conn = AsyncMock()
        
        # Setup acquire() to return an async context manager
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__.return_value = mock_conn
        mock_acquire_ctx.__aexit__.return_value = None
        
        # pool.acquire() returns the context manager
        mock_pool.acquire.return_value = mock_acquire_ctx
        
        # pool.close() is async
        mock_pool.close = AsyncMock()
        
        yield mock_create_pool, mock_pool, mock_conn

@pytest.mark.asyncio
async def test_adapter_initialization():
    """Test adapter initializes correctly."""
    # Ensure DATABASE_URL is set for test
    with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://user:pass@localhost/db'}):
        adapter = PostgreSQLAdapterAsync()
        assert adapter.database_url == 'postgresql://user:pass@localhost/db'
        assert adapter.schema is not None
        await adapter.close()

@pytest.mark.asyncio
async def test_connection(mock_asyncpg_pool):
    """Test database connection."""
    mock_create_pool, mock_pool, mock_conn = mock_asyncpg_pool
    mock_conn.fetchval.return_value = 1
    
    with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://user:pass@localhost/db'}):
        adapter = PostgreSQLAdapterAsync()
        connected = await adapter.test_connection()
        
        assert connected is True
        mock_conn.fetchval.assert_called_with("SELECT 1")
        await adapter.close()

@pytest.mark.asyncio
async def test_execute_query(mock_asyncpg_pool):
    """Test SELECT query execution."""
    mock_create_pool, mock_pool, mock_conn = mock_asyncpg_pool
    
    # Mock fetch return value (list of Record-like objects)
    mock_row = {'test': 1}
    mock_conn.fetch.return_value = [mock_row]
    
    with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://user:pass@localhost/db'}):
        adapter = PostgreSQLAdapterAsync()
        result = await adapter.execute_query("SELECT 1 as test")
        
        assert len(result) == 1
        assert result[0]['test'] == 1
        
        # Verify search_path was set
        mock_conn.execute.assert_any_call(f"SET search_path TO {adapter.schema}")
        mock_conn.fetch.assert_called_with("SELECT 1 as test")
        
        await adapter.close()

@pytest.mark.asyncio
async def test_execute_update(mock_asyncpg_pool):
    """Test INSERT query execution."""
    mock_create_pool, mock_pool, mock_conn = mock_asyncpg_pool
    mock_conn.execute.return_value = "INSERT 0 1"
    
    with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://user:pass@localhost/db'}):
        adapter = PostgreSQLAdapterAsync()
        result = await adapter.execute_update(
            "INSERT INTO test (name) VALUES ($1)",
            ["test_value"]
        )
        
        assert result == "INSERT 0 1"
        mock_conn.execute.assert_called_with("INSERT INTO test (name) VALUES ($1)", "test_value")
        
        await adapter.close()
