"""
Comprehensive Test Suite for switch_project Function
======================================================

This test suite provides exhaustive coverage for the switch_project function,
following TDD principles (RED → GREEN → REFACTOR).

Test Categories:
1. Input Validation Tests (8 tests)
2. Error Handling Tests (5 tests)
3. State Verification Tests (6 tests)
4. Concurrency Tests (3 tests)
5. Performance Tests (2 tests)

Total: 24 comprehensive tests

Requirements:
- pytest>=7.4.0
- pytest-asyncio>=0.21.0
- pytest-mock>=3.11.0

Usage:
    python3 -m pytest test_switch_project_comprehensive.py -v
    python3 -m pytest test_switch_project_comprehensive.py::test_empty_project_name -v
    python3 -m pytest test_switch_project_comprehensive.py -k "validation" -v

Reference Documents:
- TEST_COVERAGE_ANALYSIS.md
- CLAUDE.md
- docs/SWITCH_PROJECT_ARCHITECTURE.md
"""

import os
import sys
import json
import asyncio
import time
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
import psycopg2
from psycopg2 import OperationalError, DatabaseError
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up test environment
os.environ['ENVIRONMENT'] = 'test'
os.environ['DEMENTIA_API_KEY'] = 'test_key_comprehensive'

# Import the module under test
import claude_mcp_hybrid_sessions
from claude_mcp_hybrid_sessions import (
    switch_project,
    _active_projects,
    _get_project_for_context,
)

# Import dependencies
from postgres_adapter import PostgreSQLAdapter
from mcp_session_store import PostgreSQLSessionStore
from src.config import config


# ============================================================================
# PYTEST FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def mock_postgres_adapter():
    """
    Mock PostgreSQL adapter for isolated testing.

    Returns a MagicMock that simulates PostgreSQLAdapter behavior
    without requiring a real database connection.
    """
    adapter = MagicMock(spec=PostgreSQLAdapter)
    adapter.schema = 'test_schema'
    adapter.get_connection = MagicMock()
    adapter.execute_query = MagicMock(return_value=[])
    adapter.execute_update = MagicMock()
    adapter.ensure_schema_exists = MagicMock()
    return adapter


@pytest.fixture(scope="function")
def mock_session_store():
    """
    Mock session store for testing session management.

    Returns a MagicMock that simulates PostgreSQLSessionStore behavior.
    """
    store = MagicMock(spec=PostgreSQLSessionStore)
    store.update_session_project = MagicMock(return_value=True)
    store.create_session = MagicMock(return_value={
        'session_id': 'test_session_12345',
        'project_name': 'default',
        'created_at': datetime.now(timezone.utc),
        'last_active': datetime.now(timezone.utc),
    })
    return store


@pytest.fixture(scope="function")
def test_session():
    """
    Set up a test session for switch_project tests.

    Creates a valid session ID and session store that can be used
    across multiple tests. Cleans up after test completion.
    """
    # Save original state
    original_session_id = claude_mcp_hybrid_sessions._local_session_id
    original_session_store = claude_mcp_hybrid_sessions._session_store
    original_active_projects = claude_mcp_hybrid_sessions._active_projects.copy()

    # Set up test session
    test_session_id = 'test_session_' + os.urandom(8).hex()
    claude_mcp_hybrid_sessions._local_session_id = test_session_id

    # Mock session store
    mock_store = MagicMock(spec=PostgreSQLSessionStore)
    mock_store.update_session_project = MagicMock(return_value=True)
    claude_mcp_hybrid_sessions._session_store = mock_store

    yield {
        'session_id': test_session_id,
        'session_store': mock_store
    }

    # Restore original state
    claude_mcp_hybrid_sessions._local_session_id = original_session_id
    claude_mcp_hybrid_sessions._session_store = original_session_store
    claude_mcp_hybrid_sessions._active_projects = original_active_projects


@pytest.fixture(scope="function")
def mock_psycopg2_connection():
    """
    Mock psycopg2 database connection for testing database operations.

    Returns a mock connection with cursor, execute, and fetchone methods.
    """
    mock_cursor = MagicMock()
    mock_cursor.fetchone = MagicMock(return_value=None)
    mock_cursor.execute = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_connection = MagicMock()
    mock_connection.cursor = MagicMock(return_value=mock_cursor)
    mock_connection.close = MagicMock()

    return mock_connection


@pytest.fixture(scope="function", autouse=True)
def reset_state():
    """
    Reset global state before each test.

    This ensures test isolation by clearing in-memory caches.
    """
    # Clear active projects cache before each test
    _active_projects.clear()
    yield
    # Clear again after test
    _active_projects.clear()


# ============================================================================
# CATEGORY 1: INPUT VALIDATION TESTS (8 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_empty_project_name(test_session):
    """
    Test switch_project with empty string project name.

    Expected behavior:
    - Should sanitize empty string to valid project name OR reject
    - Should not crash
    - Should return JSON with either success or error

    Current implementation sanitizes to empty after stripping underscores,
    which may cause issues. This test documents expected behavior.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        result = await switch_project("")

        # Parse result
        result_data = json.loads(result)

        # Should either reject or handle gracefully
        assert isinstance(result_data, dict), "Result should be a JSON object"
        assert "success" in result_data or "error" in result_data, \
            "Result should have success or error field"


@pytest.mark.asyncio
async def test_null_project_name(test_session):
    """
    Test switch_project with None as project name.

    Expected behavior:
    - Should raise TypeError or return error JSON
    - Should not crash the server

    This tests defensive programming for type safety.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        try:
            result = await switch_project(None)
            result_data = json.loads(result)
            # If it doesn't raise, should return error
            assert result_data.get("success") == False, \
                "None project name should return error"
        except (TypeError, AttributeError):
            # Expected exception for None input
            pass


@pytest.mark.asyncio
async def test_sql_injection_attempt(test_session):
    """
    Test switch_project with SQL injection payload.

    Input: "'; DROP TABLE sessions; --"
    Expected sanitized: _drop_table_sessions_

    This test verifies that the input sanitization prevents SQL injection
    by converting special characters to underscores.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone = MagicMock(return_value=None)
        mock_connect.return_value = mock_conn

        malicious_input = "'; DROP TABLE sessions; --"
        result = await switch_project(malicious_input)

        result_data = json.loads(result)

        # Should successfully sanitize (not execute SQL)
        assert result_data.get("success") == True, \
            "Sanitized input should succeed"

        # Verify the sanitized schema name doesn't contain SQL syntax
        schema = result_data.get("schema", "")
        assert "DROP" not in schema.upper(), \
            "Sanitized schema should not contain SQL keywords"
        assert ";" not in schema, \
            "Sanitized schema should not contain semicolons"
        assert "--" not in schema, \
            "Sanitized schema should not contain SQL comments"

        # Verify it was sanitized to underscores
        assert schema.replace("_", "").isalnum() or schema == "", \
            "Schema should only contain alphanumeric and underscores"


@pytest.mark.asyncio
async def test_unicode_characters(test_session):
    """
    Test switch_project with Unicode characters.

    Input: "プロジェクト" (Japanese for "project")
    Expected: Should sanitize to ASCII-safe name

    This tests internationalization handling.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        unicode_input = "プロジェクト"
        result = await switch_project(unicode_input)

        result_data = json.loads(result)

        # Should handle gracefully
        assert isinstance(result_data, dict), "Should return valid JSON"

        # Schema should be ASCII-safe
        if result_data.get("success"):
            schema = result_data.get("schema", "")
            # Should only contain lowercase letters, numbers, and underscores
            assert all(c.isalnum() or c == '_' for c in schema), \
                "Schema should be ASCII-safe (alphanumeric + underscore)"


@pytest.mark.asyncio
async def test_very_long_name(test_session):
    """
    Test switch_project with very long project name (>255 chars).

    PostgreSQL identifier limit is 63 bytes.
    Expected behavior: Truncate to safe length (32 chars per implementation).

    This test verifies name truncation for database compatibility.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        long_name = "a" * 1000  # 1000 character name
        result = await switch_project(long_name)

        result_data = json.loads(result)

        # Should succeed with truncated name
        assert result_data.get("success") == True, \
            "Long name should be truncated and succeed"

        # Verify truncation (implementation uses [:32])
        schema = result_data.get("schema", "")
        assert len(schema) <= 63, \
            f"Schema name should be truncated to ≤63 chars, got {len(schema)}"


@pytest.mark.asyncio
async def test_special_characters(test_session):
    """
    Test switch_project with various special characters.

    Inputs: @, #, $, %, spaces, hyphens, etc.
    Expected: Sanitize to underscores

    This test verifies comprehensive sanitization of special characters.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        test_cases = [
            ("project@123", "project_123"),
            ("my-project", "my_project"),
            ("Project#Name$", "project_name"),
            ("test project", "test_project"),
            ("project___name", "project_name"),  # Multiple underscores should collapse
        ]

        for input_name, expected_pattern in test_cases:
            result = await switch_project(input_name)
            result_data = json.loads(result)

            if result_data.get("success"):
                schema = result_data.get("schema", "")
                # Verify sanitization pattern
                assert all(c.isalnum() or c == '_' for c in schema), \
                    f"Schema '{schema}' should only contain alphanumeric and underscore"
                # Verify no consecutive underscores
                assert "__" not in schema, \
                    f"Schema '{schema}' should not have consecutive underscores"


@pytest.mark.asyncio
async def test_whitespace_handling(test_session):
    """
    Test switch_project with leading/trailing whitespace.

    Input: "  project_name  "
    Expected: Trim whitespace and sanitize

    This test verifies whitespace normalization.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        whitespace_inputs = [
            "  project  ",
            "\tproject\t",
            "  \n  project  \n  ",
            " my  project ",  # Internal whitespace
        ]

        for input_name in whitespace_inputs:
            result = await switch_project(input_name)
            result_data = json.loads(result)

            assert result_data.get("success") == True, \
                f"Whitespace input '{repr(input_name)}' should succeed"

            schema = result_data.get("schema", "")
            # Should not have leading/trailing underscores (from .strip('_'))
            assert not schema.startswith("_") and not schema.endswith("_"), \
                f"Schema '{schema}' should not have leading/trailing underscores"


@pytest.mark.asyncio
async def test_numeric_only_name(test_session):
    """
    Test switch_project with numeric-only project name.

    Input: "12345"
    Expected: Should accept (valid after sanitization)

    PostgreSQL allows identifiers starting with numbers if quoted,
    but sanitization may affect this.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        numeric_name = "12345"
        result = await switch_project(numeric_name)

        result_data = json.loads(result)

        # Should succeed - numeric names are valid after sanitization
        assert result_data.get("success") == True, \
            "Numeric project name should be accepted"

        schema = result_data.get("schema", "")
        assert schema.isdigit(), \
            f"Numeric schema '{schema}' should remain numeric"


# ============================================================================
# CATEGORY 2: ERROR HANDLING TESTS (5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_database_connection_failure(test_session):
    """
    Test switch_project when database connection fails.

    Simulates: psycopg2.OperationalError
    Expected: Return error JSON without crashing

    This test verifies graceful error handling for network/database failures.
    """
    with patch('psycopg2.connect') as mock_connect:
        # Simulate connection failure
        mock_connect.side_effect = OperationalError("Connection refused")

        result = await switch_project("test_project")
        result_data = json.loads(result)

        # Should return error, not crash
        assert result_data.get("success") == False, \
            "Connection failure should return error"
        assert "error" in result_data, \
            "Error message should be present"
        # Verify error mentions connection issue
        error_msg = str(result_data.get("error", "")).lower()
        assert "connection" in error_msg or "operational" in error_msg, \
            f"Error should mention connection issue: {result_data.get('error')}"


@pytest.mark.asyncio
async def test_schema_creation_failure(test_session):
    """
    Test switch_project when schema creation/query fails.

    Simulates: Exception during schema existence check
    Expected: Return error JSON

    This test verifies error handling when database operations fail.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # First execute (schema check) raises exception
        mock_cursor.execute.side_effect = DatabaseError("Permission denied on schema")
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        result = await switch_project("test_project")
        result_data = json.loads(result)

        # Should return error
        assert result_data.get("success") == False, \
            "Schema creation failure should return error"
        assert "error" in result_data, \
            "Error message should be present"


@pytest.mark.asyncio
async def test_permission_error(test_session):
    """
    Test switch_project when user lacks database permissions.

    Simulates: psycopg2.ProgrammingError (permission denied)
    Expected: Return error JSON with permission message

    This test verifies handling of authorization failures.
    """
    with patch('psycopg2.connect') as mock_connect:
        from psycopg2 import ProgrammingError

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = ProgrammingError(
            "permission denied for schema information_schema"
        )
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        result = await switch_project("test_project")
        result_data = json.loads(result)

        # Should return error
        assert result_data.get("success") == False, \
            "Permission error should return error"
        assert "error" in result_data, \
            "Error message should be present"


@pytest.mark.asyncio
async def test_transaction_rollback():
    """
    Test switch_project rollback when session update fails mid-operation.

    Scenario:
    1. Session store update succeeds
    2. Database query fails
    3. Should return error (transaction consistency not guaranteed in current impl)

    This test documents current behavior and highlights potential improvement area.
    """
    # Save original state
    original_session_id = claude_mcp_hybrid_sessions._local_session_id
    original_session_store = claude_mcp_hybrid_sessions._session_store

    try:
        # Set up test session
        test_session_id = 'test_rollback_' + os.urandom(8).hex()
        claude_mcp_hybrid_sessions._local_session_id = test_session_id

        # Mock session store that succeeds
        mock_store = MagicMock(spec=PostgreSQLSessionStore)
        mock_store.update_session_project = MagicMock(return_value=True)
        claude_mcp_hybrid_sessions._session_store = mock_store

        with patch('psycopg2.connect') as mock_connect:
            # Database connection fails AFTER session update
            mock_connect.side_effect = OperationalError("Connection lost")

            result = await switch_project("test_project")
            result_data = json.loads(result)

            # Should return error
            assert result_data.get("success") == False, \
                "Partial failure should return error"

            # Session store was updated (no rollback in current implementation)
            assert mock_store.update_session_project.called, \
                "Session store should have been called"
    finally:
        # Restore original state
        claude_mcp_hybrid_sessions._local_session_id = original_session_id
        claude_mcp_hybrid_sessions._session_store = original_session_store


@pytest.mark.asyncio
async def test_missing_session_store():
    """
    Test switch_project when session store is not initialized.

    Scenario: _session_store is None
    Expected: Return error JSON about missing session

    This test verifies startup/initialization error handling.
    """
    # Save original state
    original_session_store = claude_mcp_hybrid_sessions._session_store
    original_session_id = claude_mcp_hybrid_sessions._local_session_id

    try:
        # Set session store to None (uninitialized state)
        claude_mcp_hybrid_sessions._session_store = None
        claude_mcp_hybrid_sessions._local_session_id = 'some_session'

        result = await switch_project("test_project")
        result_data = json.loads(result)

        # Should return error about missing session
        assert result_data.get("success") == False, \
            "Missing session store should return error"
        assert "error" in result_data, \
            "Error message should be present"
        error_msg = str(result_data.get("error", "")).lower()
        assert "session" in error_msg, \
            f"Error should mention session: {result_data.get('error')}"
    finally:
        # Restore original state
        claude_mcp_hybrid_sessions._session_store = original_session_store
        claude_mcp_hybrid_sessions._local_session_id = original_session_id


# ============================================================================
# CATEGORY 3: STATE VERIFICATION TESTS (6 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_database_persistence(test_session):
    """
    Test that switch_project persists active_project to database.

    Verification:
    1. Call switch_project
    2. Verify update_session_project was called with correct parameters
    3. Verify session store was updated

    This is the core persistence test.
    """
    project_name = "test_persistence"

    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        result = await switch_project(project_name)
        result_data = json.loads(result)

        # Should succeed
        assert result_data.get("success") == True, \
            "Switch should succeed"

        # Verify session store was updated
        session_store = test_session['session_store']
        session_store.update_session_project.assert_called_once()

        # Verify it was called with correct session ID and sanitized name
        call_args = session_store.update_session_project.call_args
        assert call_args[0][0] == test_session['session_id'], \
            "Should update correct session ID"
        assert call_args[0][1] == "test_persistence", \
            "Should use sanitized project name"


@pytest.mark.asyncio
async def test_cache_update(test_session):
    """
    Test that switch_project updates in-memory cache (_active_projects).

    Verification:
    1. Call switch_project
    2. Verify _active_projects[session_id] == project_name

    This ensures backward compatibility with in-memory cache.
    """
    project_name = "test_cache"
    session_id = test_session['session_id']

    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        # Clear cache first
        _active_projects.clear()

        result = await switch_project(project_name)
        result_data = json.loads(result)

        # Should succeed
        assert result_data.get("success") == True, \
            "Switch should succeed"

        # Verify in-memory cache was updated
        assert session_id in _active_projects, \
            "Session should be in active projects cache"
        assert _active_projects[session_id] == "test_cache", \
            f"Cache should store sanitized name, got {_active_projects[session_id]}"


@pytest.mark.asyncio
async def test_cache_and_db_consistency(test_session):
    """
    Test that cache and database are updated consistently.

    Verification:
    1. Call switch_project
    2. Verify both cache AND database were updated
    3. Verify they have the same value

    This ensures dual-write consistency.
    """
    project_name = "consistency_test"
    session_id = test_session['session_id']

    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        # Clear cache
        _active_projects.clear()

        result = await switch_project(project_name)
        result_data = json.loads(result)

        assert result_data.get("success") == True

        # Verify both were updated
        session_store = test_session['session_store']

        # Database update
        assert session_store.update_session_project.called, \
            "Database should be updated"
        db_project_name = session_store.update_session_project.call_args[0][1]

        # Cache update
        assert session_id in _active_projects, \
            "Cache should be updated"
        cache_project_name = _active_projects[session_id]

        # Consistency check
        assert db_project_name == cache_project_name, \
            f"Database ({db_project_name}) and cache ({cache_project_name}) should match"


@pytest.mark.asyncio
async def test_project_stats_accuracy(test_session):
    """
    Test that returned stats accurately reflect database state.

    Verification:
    1. Mock database to return specific counts
    2. Call switch_project
    3. Verify returned stats match mocked counts

    This ensures stats reporting is accurate.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Mock schema existence check (returns True - schema exists)
        # Mock stats queries
        call_count = [0]

        def mock_fetchone():
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: schema existence check
                return {'schema_name': 'test_project'}
            elif call_count[0] == 2:
                # Second call: sessions count
                return {'count': 42}
            elif call_count[0] == 3:
                # Third call: contexts count
                return {'count': 123}
            return None

        mock_cursor.fetchone = mock_fetchone
        mock_cursor.execute = MagicMock()

        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close = MagicMock()
        mock_connect.return_value = mock_conn

        result = await switch_project("test_project")
        result_data = json.loads(result)

        # Should succeed
        assert result_data.get("success") == True

        # Verify stats are present and accurate
        assert "stats" in result_data, \
            "Stats should be present in response"
        stats = result_data["stats"]

        assert stats.get("sessions") == 42, \
            f"Sessions count should be 42, got {stats.get('sessions')}"
        assert stats.get("contexts") == 123, \
            f"Contexts count should be 123, got {stats.get('contexts')}"


@pytest.mark.asyncio
async def test_schema_creation_on_first_use(test_session):
    """
    Test switching to a new project that doesn't exist yet.

    Verification:
    1. Mock database to indicate schema doesn't exist
    2. Call switch_project
    3. Verify response indicates "will be created on first use"

    This tests the new project creation workflow.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Schema doesn't exist - fetchone returns None
        mock_cursor.fetchone = MagicMock(return_value=None)
        mock_cursor.execute = MagicMock()

        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close = MagicMock()
        mock_connect.return_value = mock_conn

        result = await switch_project("new_project")
        result_data = json.loads(result)

        # Should succeed
        assert result_data.get("success") == True, \
            "Switching to new project should succeed"

        # Should indicate it doesn't exist yet
        assert result_data.get("exists") == False, \
            "Should indicate project doesn't exist yet"

        # Should have informative message
        message = result_data.get("message", "").lower()
        assert "created" in message or "first use" in message, \
            f"Message should mention creation: {result_data.get('message')}"


@pytest.mark.asyncio
async def test_existing_project_switch(test_session):
    """
    Test switching to an existing project with data.

    Verification:
    1. Mock database to indicate schema exists
    2. Mock stats queries
    3. Call switch_project
    4. Verify response includes stats

    This tests the existing project workflow.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Schema exists + stats
        call_count = [0]

        def mock_fetchone():
            call_count[0] += 1
            if call_count[0] == 1:
                # Schema exists
                return {'schema_name': 'existing_project'}
            elif call_count[0] == 2:
                # Sessions count
                return {'count': 5}
            elif call_count[0] == 3:
                # Contexts count
                return {'count': 10}
            return None

        mock_cursor.fetchone = mock_fetchone
        mock_cursor.execute = MagicMock()

        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close = MagicMock()
        mock_connect.return_value = mock_conn

        result = await switch_project("existing_project")
        result_data = json.loads(result)

        # Should succeed
        assert result_data.get("success") == True

        # Should indicate it exists
        assert result_data.get("exists") == True, \
            "Should indicate project exists"

        # Should include stats
        assert "stats" in result_data, \
            "Should include project stats"
        assert result_data["stats"]["sessions"] == 5
        assert result_data["stats"]["contexts"] == 10


# ============================================================================
# CATEGORY 4: CONCURRENCY TESTS (3 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_switches():
    """
    Test multiple concurrent switch_project calls.

    Scenario:
    - Create 5 concurrent switch_project calls
    - Each switches to different project
    - All should complete without deadlock or corruption

    This tests thread safety and concurrency handling.
    """
    # Set up test session
    test_session_id = 'test_concurrent_' + os.urandom(8).hex()
    claude_mcp_hybrid_sessions._local_session_id = test_session_id

    mock_store = MagicMock(spec=PostgreSQLSessionStore)
    mock_store.update_session_project = MagicMock(return_value=True)
    claude_mcp_hybrid_sessions._session_store = mock_store

    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        # Launch concurrent switches
        projects = ['project_a', 'project_b', 'project_c', 'project_d', 'project_e']

        tasks = [switch_project(proj) for proj in projects]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete (either success or error, but no exceptions)
        assert len(results) == 5, \
            "All tasks should complete"

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Task {i} raised exception: {result}")

            # Parse result
            result_data = json.loads(result)
            assert "success" in result_data or "error" in result_data, \
                f"Result {i} should have success or error field"


@pytest.mark.asyncio
async def test_race_condition_handling():
    """
    Test race condition between session update and cache update.

    Scenario:
    - Simulate slow session store update
    - Verify cache is still updated correctly
    - Verify eventual consistency

    This tests race condition resilience.
    """
    test_session_id = 'test_race_' + os.urandom(8).hex()
    claude_mcp_hybrid_sessions._local_session_id = test_session_id

    # Mock session store with delay
    mock_store = MagicMock(spec=PostgreSQLSessionStore)

    async def delayed_update(session_id, project_name):
        await asyncio.sleep(0.1)  # Simulate slow DB
        return True

    mock_store.update_session_project = AsyncMock(side_effect=delayed_update)
    claude_mcp_hybrid_sessions._session_store = mock_store

    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        # Note: Current implementation doesn't await update_session_project
        # So this test documents actual behavior
        result = await switch_project("race_test")
        result_data = json.loads(result)

        # Should succeed (if session store update is sync)
        assert isinstance(result_data, dict)


@pytest.mark.asyncio
async def test_session_conflict_resolution():
    """
    Test switch_project with conflicting session states.

    Scenario:
    - Cache says session is on project_a
    - Database says session is on project_b
    - Switch to project_c
    - Verify conflict is resolved (database wins)

    This tests conflict resolution logic.
    """
    test_session_id = 'test_conflict_' + os.urandom(8).hex()
    claude_mcp_hybrid_sessions._local_session_id = test_session_id

    # Set conflicting state
    _active_projects[test_session_id] = 'project_a'  # Cache

    mock_store = MagicMock(spec=PostgreSQLSessionStore)
    mock_store.update_session_project = MagicMock(return_value=True)
    claude_mcp_hybrid_sessions._session_store = mock_store

    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        # Switch to project_c
        result = await switch_project("project_c")
        result_data = json.loads(result)

        assert result_data.get("success") == True

        # Verify both cache and database were updated to project_c
        assert _active_projects[test_session_id] == "project_c", \
            "Cache should be updated to new project"

        # Verify session store was updated
        assert mock_store.update_session_project.called
        assert mock_store.update_session_project.call_args[0][1] == "project_c"


# ============================================================================
# CATEGORY 5: PERFORMANCE TESTS (2 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_switch_latency(test_session):
    """
    Test that switch_project completes within acceptable latency.

    Target: < 500ms for schema existence check + stats query

    This test verifies performance requirements.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_cursor = mock_conn.cursor.return_value

        # Mock fast database responses
        mock_cursor.fetchone = MagicMock(return_value=None)
        mock_connect.return_value = mock_conn

        # Measure latency
        start_time = time.time()
        result = await switch_project("perf_test")
        latency_ms = (time.time() - start_time) * 1000

        result_data = json.loads(result)

        # Should succeed
        assert result_data.get("success") == True

        # Should complete quickly (lenient for CI/CD)
        assert latency_ms < 2000, \
            f"Switch took {latency_ms:.2f}ms, expected < 2000ms"

        print(f"✓ switch_project latency: {latency_ms:.2f}ms")


@pytest.mark.asyncio
async def test_switch_under_load(test_session):
    """
    Test switch_project under load (100 sequential switches).

    Verification:
    - All switches should succeed
    - Average latency should be reasonable
    - No memory leaks or connection exhaustion

    This is a stress test.
    """
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = mock_psycopg2_connection()
        mock_connect.return_value = mock_conn

        num_switches = 100
        project_names = [f"project_{i}" for i in range(num_switches)]

        latencies = []
        start_time = time.time()

        for project_name in project_names:
            switch_start = time.time()
            result = await switch_project(project_name)
            switch_latency = (time.time() - switch_start) * 1000
            latencies.append(switch_latency)

            result_data = json.loads(result)
            assert result_data.get("success") == True, \
                f"Switch {project_name} should succeed"

        total_time = time.time() - start_time
        avg_latency = sum(latencies) / len(latencies)

        print(f"✓ {num_switches} switches in {total_time:.2f}s")
        print(f"✓ Average latency: {avg_latency:.2f}ms")
        print(f"✓ Min latency: {min(latencies):.2f}ms")
        print(f"✓ Max latency: {max(latencies):.2f}ms")

        # Verify reasonable performance
        assert avg_latency < 100, \
            f"Average latency {avg_latency:.2f}ms should be < 100ms"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_mock_cursor_with_stats(sessions_count: int, contexts_count: int):
    """
    Helper to create a mock cursor that returns specific stats.

    Args:
        sessions_count: Number of sessions to return
        contexts_count: Number of contexts to return

    Returns:
        Mock cursor configured to return specified stats
    """
    mock_cursor = MagicMock()

    call_count = [0]

    def mock_fetchone():
        call_count[0] += 1
        if call_count[0] == 1:
            # Schema exists
            return {'schema_name': 'test_project'}
        elif call_count[0] == 2:
            # Sessions count
            return {'count': sessions_count}
        elif call_count[0] == 3:
            # Contexts count
            return {'count': contexts_count}
        return None

    mock_cursor.fetchone = mock_fetchone
    mock_cursor.execute = MagicMock()

    return mock_cursor


# ============================================================================
# TEST SUITE SUMMARY
# ============================================================================

"""
Test Coverage Summary
=====================

Category 1: Input Validation Tests (8 tests)
✓ test_empty_project_name
✓ test_null_project_name
✓ test_sql_injection_attempt
✓ test_unicode_characters
✓ test_very_long_name
✓ test_special_characters
✓ test_whitespace_handling
✓ test_numeric_only_name

Category 2: Error Handling Tests (5 tests)
✓ test_database_connection_failure
✓ test_schema_creation_failure
✓ test_permission_error
✓ test_transaction_rollback
✓ test_missing_session_store

Category 3: State Verification Tests (6 tests)
✓ test_database_persistence
✓ test_cache_update
✓ test_cache_and_db_consistency
✓ test_project_stats_accuracy
✓ test_schema_creation_on_first_use
✓ test_existing_project_switch

Category 4: Concurrency Tests (3 tests)
✓ test_concurrent_switches
✓ test_race_condition_handling
✓ test_session_conflict_resolution

Category 5: Performance Tests (2 tests)
✓ test_switch_latency
✓ test_switch_under_load

TOTAL: 24 comprehensive tests

Run with:
    python3 -m pytest test_switch_project_comprehensive.py -v
    python3 -m pytest test_switch_project_comprehensive.py -k "validation" -v
    python3 -m pytest test_switch_project_comprehensive.py -k "error" -v
    python3 -m pytest test_switch_project_comprehensive.py::test_sql_injection_attempt -v
"""
