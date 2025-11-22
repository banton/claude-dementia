"""
Unit tests for PostgreSQLSessionStoreAsync.
"""

import pytest
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from mcp_session_store_async import PostgreSQLSessionStoreAsync

@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    # Mock execute_query to return a list
    adapter.execute_query.return_value = []
    # Mock execute_update to return a status string
    adapter.execute_update.return_value = "INSERT 0 1"
    return adapter

@pytest.fixture
def session_store(mock_adapter):
    return PostgreSQLSessionStoreAsync(mock_adapter)

@pytest.mark.asyncio
async def test_create_session(session_store, mock_adapter):
    """Test creating a session."""
    session_id = "test_session"
    now = datetime.now(timezone.utc)
    
    # Mock return row
    mock_row = {
        'session_id': session_id,
        'created_at': now,
        'last_active': now,
        'expires_at': now + timedelta(hours=24),
        'capabilities': '{}',
        'client_info': '{}',
        'project_name': 'default'
    }
    mock_adapter.execute_query.return_value = [mock_row]
    
    result = await session_store.create_session(session_id=session_id)
    
    assert result['session_id'] == session_id
    assert result['project_name'] == 'default'
    
    # Verify query arguments (checking for $1, $2 placeholders implicitly by call args)
    args = mock_adapter.execute_query.call_args[0]
    assert "INSERT INTO mcp_sessions" in args[0]
    assert args[1][0] == session_id

@pytest.mark.asyncio
async def test_get_session(session_store, mock_adapter):
    """Test retrieving a session."""
    session_id = "test_session"
    
    mock_row = {
        'session_id': session_id,
        'created_at': datetime.now(timezone.utc),
        'last_active': datetime.now(timezone.utc),
        'expires_at': datetime.now(timezone.utc),
        'capabilities': '{}',
        'client_info': '{}',
        'project_name': 'default',
        'session_summary': None
    }
    mock_adapter.execute_query.return_value = [mock_row]
    
    result = await session_store.get_session(session_id)
    
    assert result['session_id'] == session_id
    assert "SELECT session_id" in mock_adapter.execute_query.call_args[0][0]

@pytest.mark.asyncio
async def test_update_activity(session_store, mock_adapter):
    """Test updating activity."""
    session_id = "test_session"
    await session_store.update_activity(session_id)
    
    assert "UPDATE mcp_sessions" in mock_adapter.execute_update.call_args[0][0]
    assert mock_adapter.execute_update.call_args[0][1][2] == session_id

@pytest.mark.asyncio
async def test_cleanup_expired(session_store, mock_adapter):
    """Test cleanup of expired sessions."""
    mock_adapter.execute_update.return_value = "DELETE 5"
    
    count = await session_store.cleanup_expired()
    
    assert count == 5
    assert "DELETE FROM mcp_sessions" in mock_adapter.execute_update.call_args[0][0]
