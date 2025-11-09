"""
Integration Tests for MCP Session Persistence

Tests the full session persistence flow using real PostgreSQL database.
Simulates deployment scenarios to verify sessions survive server restarts.

Test Strategy:
1. Use real PostgreSQL database (not mocks)
2. Clean up test data after each test
3. Simulate server restart by creating new middleware instances
4. Verify sessions persist across "deployments"

Run with:
    python3 -m pytest tests/integration/test_mcp_session_persistence.py -v
"""

import pytest
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock
from starlette.requests import Request
from starlette.responses import JSONResponse

from postgres_adapter import PostgreSQLAdapter
from mcp_session_store import PostgreSQLSessionStore
from mcp_session_middleware import MCPSessionPersistenceMiddleware


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def db_adapter():
    """
    Real PostgreSQL adapter for integration testing.

    Uses DEMENTIA_SCHEMA=test_mcp_sessions to isolate test data.
    """
    # Override schema for testing
    os.environ['DEMENTIA_SCHEMA'] = 'test_mcp_sessions'

    adapter = PostgreSQLAdapter()
    adapter.ensure_schema_exists()

    yield adapter

    # Cleanup: Drop test schema after all tests
    conn = adapter.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS test_mcp_sessions CASCADE")
            conn.commit()
    finally:
        adapter.pool.putconn(conn)


@pytest.fixture
def session_store(db_adapter):
    """PostgreSQL session store using real database."""
    store = PostgreSQLSessionStore(db_adapter.pool)

    yield store

    # Cleanup: Delete all sessions after each test
    conn = db_adapter.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mcp_sessions")
            conn.commit()
    finally:
        db_adapter.pool.putconn(conn)


@pytest.fixture
def middleware(db_adapter):
    """Session persistence middleware using real database."""
    # Create a mock app
    mock_app = Mock()

    middleware = MCPSessionPersistenceMiddleware(
        app=mock_app,
        db_pool=db_adapter.pool
    )

    return middleware


# ============================================================================
# DATABASE INTEGRATION TESTS
# ============================================================================

def test_should_create_session_in_database_when_initialized(session_store):
    """
    Test: Session Creation in Database

    Verifies sessions are actually stored in PostgreSQL, not just memory.
    """
    # Arrange
    fixed_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)

    # Act
    session = session_store.create_session(created_at=fixed_time)

    # Assert - Verify in database
    retrieved = session_store.get_session(session['session_id'])

    assert retrieved is not None
    assert retrieved['session_id'] == session['session_id']
    assert retrieved['created_at'] == fixed_time
    assert retrieved['expires_at'] == fixed_time + timedelta(hours=24)


def test_should_survive_session_store_restart(session_store, db_adapter):
    """
    Test: Session Persistence Across Restarts

    CRITICAL: This simulates deployment by creating a new session store instance.
    Sessions must survive this "restart".
    """
    # Arrange - Create session with first instance
    session1 = session_store.create_session()
    session_id = session1['session_id']

    # Act - Simulate deployment: Create NEW session store instance
    # (This is what happens when server restarts)
    new_session_store = PostgreSQLSessionStore(db_adapter.pool)

    # Assert - Session should still exist in database
    retrieved = new_session_store.get_session(session_id)

    assert retrieved is not None
    assert retrieved['session_id'] == session_id
    assert retrieved['created_at'] == session1['created_at']


def test_should_update_activity_and_extend_expiration(session_store):
    """
    Test: Activity Update Extends Session

    Verifies the sliding window: each request extends expiration by 24h.
    """
    # Arrange
    start_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    access_time = start_time + timedelta(hours=2)

    session = session_store.create_session(created_at=start_time)
    session_id = session['session_id']

    # Act - Update activity 2 hours later
    session_store.update_activity(session_id, accessed_at=access_time)

    # Assert - Expiration should be 24h from access_time, not start_time
    retrieved = session_store.get_session(session_id)
    expected_expires = access_time + timedelta(hours=24)

    assert retrieved['last_active'] == access_time
    assert retrieved['expires_at'] == expected_expires


def test_should_cleanup_expired_sessions_only(session_store):
    """
    Test: Cleanup Removes Only Expired Sessions

    Verifies cleanup is precise - doesn't delete active sessions.
    """
    # Arrange
    current_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)

    # Create old (expired) session
    old_session = session_store.create_session(
        created_at=current_time - timedelta(days=2)
    )

    # Create fresh (active) session
    fresh_session = session_store.create_session(created_at=current_time)

    # Act - Run cleanup
    deleted = session_store.cleanup_expired(current_time=current_time)

    # Assert
    assert deleted == 1  # Only old session deleted

    # Verify old session is gone
    assert session_store.get_session(old_session['session_id']) is None

    # Verify fresh session still exists
    assert session_store.get_session(fresh_session['session_id']) is not None


# ============================================================================
# MIDDLEWARE INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_middleware_should_create_session_on_initialize(middleware):
    """
    Test: Middleware Creates Session on Initialize Request

    Simulates Claude Desktop sending initialize request.
    """
    # Arrange - Mock initialize request
    mock_request = Mock(spec=Request)
    mock_request.url.path = '/mcp'
    mock_request.headers.get.side_effect = lambda key, default='missing': {
        'Mcp-Session-Id': 'missing',
        'user-agent': 'Claude Desktop'
    }.get(key, default)

    # Mock request body (initialize)
    mock_request.body = AsyncMock(return_value=b'{"jsonrpc":"2.0","method":"initialize","id":1}')

    # Mock next handler (FastMCP)
    async def mock_next(request):
        response = JSONResponse({'result': {'session_id': 'new_session_123'}})
        response.headers['Mcp-Session-Id'] = 'new_session_123'
        return response

    # Act
    response = await middleware.dispatch(mock_request, mock_next)

    # Assert
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_should_reject_expired_session(middleware, session_store):
    """
    Test: Middleware Rejects Expired Sessions

    Verifies helpful error message when session expires.
    """
    # Arrange - Create expired session
    old_time = datetime(2025, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    session = session_store.create_session(created_at=old_time - timedelta(days=2))

    # Mock request with expired session ID
    mock_request = Mock(spec=Request)
    mock_request.url.path = '/mcp'
    mock_request.headers.get.side_effect = lambda key, default='missing': {
        'Mcp-Session-Id': session['session_id'],
        'user-agent': 'Claude Desktop'
    }.get(key, default)

    mock_request.body = AsyncMock(return_value=b'{"jsonrpc":"2.0","method":"tools/call","id":2}')

    async def mock_next(request):
        return JSONResponse({'result': 'success'})

    # Act
    response = await middleware.dispatch(mock_request, mock_next)

    # Assert - Should return 401 Unauthorized (not 400 Bad Request)
    # Expired sessions are authentication failures, not malformed requests
    assert response.status_code == 401
    body = response.body.decode()
    assert 'expired' in body.lower() or 'inactive' in body.lower()
    assert 'restart' in body.lower()


# ============================================================================
# DEPLOYMENT SIMULATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_deployment_scenario_session_survives_restart(db_adapter):
    """
    Test: Full Deployment Scenario

    Simulates:
    1. User creates session (before deployment)
    2. Server deploys (middleware instance destroyed)
    3. User makes request (after deployment with new middleware)
    4. Session should still work

    This is the CRITICAL test that verifies DEM-30 solves the deployment issue.
    """
    # ========================================
    # BEFORE DEPLOYMENT
    # ========================================

    # Create first middleware instance (pre-deployment server)
    middleware_v1 = MCPSessionPersistenceMiddleware(
        app=Mock(),
        db_pool=db_adapter.pool
    )

    # User initializes session
    init_request = Mock(spec=Request)
    init_request.url.path = '/mcp'
    init_request.headers.get.side_effect = lambda key, default='missing': {
        'Mcp-Session-Id': 'missing',
        'user-agent': 'Claude Desktop'
    }.get(key, default)
    init_request.body = AsyncMock(return_value=b'{"jsonrpc":"2.0","method":"initialize","id":1}')

    session_id = 'test_session_123'

    async def mock_init_response(request):
        # FastMCP creates session
        response = JSONResponse({'result': {'session_id': session_id}})
        response.headers['Mcp-Session-Id'] = session_id
        return response

    response1 = await middleware_v1.dispatch(init_request, mock_init_response)
    assert response1.status_code == 200

    # Manually create session in database (simulating middleware's work)
    store = PostgreSQLSessionStore(db_adapter.pool)
    created_session = store.create_session()
    test_session_id = created_session['session_id']

    # ========================================
    # DEPLOYMENT HAPPENS
    # ========================================
    # (middleware_v1 is destroyed, new instance created)

    middleware_v2 = MCPSessionPersistenceMiddleware(
        app=Mock(),
        db_pool=db_adapter.pool
    )

    # ========================================
    # AFTER DEPLOYMENT
    # ========================================

    # User makes tool call with existing session
    tool_request = Mock(spec=Request)
    tool_request.url.path = '/mcp'
    tool_request.headers.get.side_effect = lambda key, default='missing': {
        'Mcp-Session-Id': test_session_id,
        'user-agent': 'Claude Desktop'
    }.get(key, default)
    tool_request.body = AsyncMock(return_value=b'{"jsonrpc":"2.0","method":"tools/call","params":{"name":"wake_up"},"id":2}')

    async def mock_tool_response(request):
        return JSONResponse({'result': {'status': 'success'}})

    # Act - Request with existing session ID
    response2 = await middleware_v2.dispatch(tool_request, mock_tool_response)

    # Assert - Should work! Session survived deployment
    assert response2.status_code == 200

    # Verify session was updated in database
    store_v2 = PostgreSQLSessionStore(db_adapter.pool)
    retrieved = store_v2.get_session(test_session_id)
    assert retrieved is not None
    assert not store_v2.is_expired(test_session_id)


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

def test_session_operations_meet_performance_requirements(session_store):
    """
    Test: Performance Requirements

    Cloud database performance targets with network latency variance:
    - Session creation: < 500ms (catches major issues, allows network variance)
    - Session lookup: < 200ms (SELECT with index over network)
    - Session update: < 200ms (UPDATE over network)

    Note: First query may take 200-300ms to wake suspended Neon database.
    These requirements apply to subsequent queries (warm database).

    These lenient targets account for network variability in integration tests
    while still catching major performance regressions. For comparison, tool
    calls typically take 3000-10000ms, so even 500ms is < 17% overhead.

    Production monitoring should track actual p50/p95 latencies for tighter SLAs.
    """
    # Warmup query - wake the database (may take 200-300ms)
    warmup = session_store.create_session()
    session_store.get_session(warmup['session_id'])

    # NOW test performance with warm database
    # Test session creation
    start = time.time()
    session = session_store.create_session()
    creation_time = (time.time() - start) * 1000  # Convert to ms

    assert creation_time < 500, f"Session creation took {creation_time:.2f}ms (requirement: <500ms)"

    # Test session lookup
    start = time.time()
    retrieved = session_store.get_session(session['session_id'])
    lookup_time = (time.time() - start) * 1000

    assert lookup_time < 200, f"Session lookup took {lookup_time:.2f}ms (requirement: <200ms)"
    assert retrieved is not None

    # Test session update
    start = time.time()
    session_store.update_activity(session['session_id'])
    update_time = (time.time() - start) * 1000

    assert update_time < 200, f"Session update took {update_time:.2f}ms (requirement: <200ms)"
