"""
Unit tests for MCP Session Store (PostgreSQL-backed persistent sessions).

TDD Phase: RED - These tests are written FIRST and should FAIL initially.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch
import psycopg2
from psycopg2.extras import RealDictCursor


# Test fixtures for database connection
@pytest.fixture
def mock_db_pool():
    """Mock PostgreSQL connection pool."""
    pool = Mock()
    conn = MagicMock()
    cursor = MagicMock()

    # Setup mock chain
    pool.getconn.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = None

    return pool, conn, cursor


# Unit Tests - Following TDD ticket specification


def test_should_create_session_with_unique_id_when_initialized(mock_db_pool):
    """Test: Session Creation"""
    # Arrange
    from mcp_session_store import PostgreSQLSessionStore

    fixed_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    pool, conn, cursor = mock_db_pool
    store = PostgreSQLSessionStore(pool)

    # Mock cursor to return session data
    cursor.fetchone.return_value = {
        'session_id': 'abc123def456',
        'created_at': fixed_time,
        'last_active': fixed_time,
        'expires_at': fixed_time + timedelta(hours=24),
        'capabilities': {},
        'client_info': {},
        'project_name': 'default'
    }

    # Act
    session = store.create_session(created_at=fixed_time)

    # Assert
    assert session['session_id'] is not None
    assert len(session['session_id']) == 12  # UUID fragment
    assert session['created_at'] == fixed_time
    assert session['last_active'] == fixed_time
    assert session['expires_at'] == fixed_time + timedelta(hours=24)

    # Verify SQL was executed
    cursor.execute.assert_called()


def test_should_persist_session_to_database_when_created(mock_db_pool):
    """Test: Session Persistence"""
    # Arrange
    from mcp_session_store import PostgreSQLSessionStore

    pool, conn, cursor = mock_db_pool
    store = PostgreSQLSessionStore(pool)

    session_id = 'test_session_123'
    cursor.fetchone.side_effect = [
        # First call - create_session
        {
            'session_id': session_id,
            'created_at': datetime.now(timezone.utc),
            'last_active': datetime.now(timezone.utc),
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=24),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default'
        },
        # Second call - get_session
        {
            'session_id': session_id,
            'created_at': datetime.now(timezone.utc),
            'last_active': datetime.now(timezone.utc),
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=24),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default',
            'session_summary': {}
        }
    ]

    # Act
    session = store.create_session()
    retrieved = store.get_session(session['session_id'])

    # Assert
    assert retrieved['session_id'] == session['session_id']
    assert retrieved['capabilities'] == session['capabilities']


def test_should_mark_session_expired_when_24_hours_passed(mock_db_pool):
    """Test: Session Expiration"""
    # Arrange
    from mcp_session_store import PostgreSQLSessionStore

    fixed_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    pool, conn, cursor = mock_db_pool
    store = PostgreSQLSessionStore(pool)

    session_id = 'expiring_session'
    cursor.fetchone.side_effect = [
        # create_session
        {
            'session_id': session_id,
            'created_at': fixed_time,
            'last_active': fixed_time,
            'expires_at': fixed_time + timedelta(hours=24),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default'
        },
        # is_expired check - return the session
        {
            'session_id': session_id,
            'expires_at': fixed_time + timedelta(hours=24)
        }
    ]

    # Act
    session = store.create_session(created_at=fixed_time)
    expired = store.is_expired(
        session['session_id'],
        current_time=fixed_time + timedelta(hours=24, seconds=1)
    )

    # Assert
    assert expired is True


def test_should_update_last_active_when_session_accessed(mock_db_pool):
    """Test: Session Activity Update"""
    # Arrange
    from mcp_session_store import PostgreSQLSessionStore

    fixed_start = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    fixed_access = fixed_start + timedelta(hours=2)
    pool, conn, cursor = mock_db_pool
    store = PostgreSQLSessionStore(pool)

    session_id = 'active_session'
    cursor.fetchone.side_effect = [
        # create_session
        {
            'session_id': session_id,
            'created_at': fixed_start,
            'last_active': fixed_start,
            'expires_at': fixed_start + timedelta(hours=24),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default'
        },
        # get_session after update
        {
            'session_id': session_id,
            'created_at': fixed_start,
            'last_active': fixed_access,
            'expires_at': fixed_access + timedelta(hours=24),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default',
            'session_summary': {}
        }
    ]

    # Act
    session = store.create_session(created_at=fixed_start)
    store.update_activity(session['session_id'], accessed_at=fixed_access)
    retrieved = store.get_session(session['session_id'])

    # Assert
    assert retrieved['last_active'] == fixed_access
    assert retrieved['expires_at'] == fixed_access + timedelta(hours=24)


def test_should_delete_expired_sessions_when_cleanup_runs(mock_db_pool):
    """Test: Cleanup Expired Sessions"""
    # Arrange
    from mcp_session_store import PostgreSQLSessionStore

    fixed_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    pool, conn, cursor = mock_db_pool
    store = PostgreSQLSessionStore(pool)

    # Mock rowcount for DELETE operation
    cursor.rowcount = 1  # One session deleted

    cursor.fetchone.side_effect = [
        # create old session
        {
            'session_id': 'old_session',
            'created_at': fixed_time - timedelta(days=2),
            'last_active': fixed_time - timedelta(days=2),
            'expires_at': fixed_time - timedelta(days=1),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default'
        },
        # create new session
        {
            'session_id': 'new_session',
            'created_at': fixed_time,
            'last_active': fixed_time,
            'expires_at': fixed_time + timedelta(hours=24),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default'
        },
        # get old session after cleanup (should be None)
        None,
        # get new session after cleanup (should exist)
        {
            'session_id': 'new_session',
            'created_at': fixed_time,
            'last_active': fixed_time,
            'expires_at': fixed_time + timedelta(hours=24),
            'capabilities': {},
            'client_info': {},
            'project_name': 'default',
            'session_summary': {}
        }
    ]

    # Act
    old_session = store.create_session(created_at=fixed_time - timedelta(days=2))
    new_session = store.create_session(created_at=fixed_time)

    deleted = store.cleanup_expired(current_time=fixed_time)

    retrieved_old = store.get_session(old_session['session_id'])
    retrieved_new = store.get_session(new_session['session_id'])

    # Assert
    assert deleted == 1
    assert retrieved_old is None  # Old session deleted
    assert retrieved_new is not None  # New session still exists


# Edge Cases & Error Handling Tests


def test_should_handle_duplicate_session_id_by_regenerating(mock_db_pool):
    """Test: Handle duplicate session IDs (regenerate)"""
    # Arrange
    from mcp_session_store import PostgreSQLSessionStore
    import psycopg2.errors

    pool, conn, cursor = mock_db_pool
    store = PostgreSQLSessionStore(pool)

    # First attempt raises IntegrityError (duplicate key)
    # Second attempt succeeds
    cursor.execute.side_effect = [
        psycopg2.errors.UniqueViolation("duplicate key value"),
        None  # Success on retry
    ]

    cursor.fetchone.return_value = {
        'session_id': 'new_unique_id',
        'created_at': datetime.now(timezone.utc),
        'last_active': datetime.now(timezone.utc),
        'expires_at': datetime.now(timezone.utc) + timedelta(hours=24),
        'capabilities': {},
        'client_info': {},
        'project_name': 'default'
    }

    # Act
    session = store.create_session()

    # Assert
    assert session['session_id'] is not None
    # Should have tried twice (first failed, second succeeded)
    assert cursor.execute.call_count >= 2


def test_should_return_none_for_invalid_session_id(mock_db_pool):
    """Test: Handle invalid session IDs (return None)"""
    # Arrange
    from mcp_session_store import PostgreSQLSessionStore

    pool, conn, cursor = mock_db_pool
    store = PostgreSQLSessionStore(pool)

    cursor.fetchone.return_value = None  # Session not found

    # Act
    retrieved = store.get_session('nonexistent_session')

    # Assert
    assert retrieved is None
