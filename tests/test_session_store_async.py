"""
Unit tests for PostgreSQLSessionStoreAsync.

Validates async session management before migration proceeds.
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from mcp_session_store_async import PostgreSQLSessionStoreAsync
from postgres_adapter_async import PostgreSQLAdapterAsync


@pytest.mark.asyncio
async def test_store_initialization():
    """Test session store initializes correctly."""
    adapter = PostgreSQLAdapterAsync()
    store = PostgreSQLSessionStoreAsync(adapter)

    assert store.adapter is adapter
    assert store.adapter.schema is not None

    await adapter.close()


@pytest.mark.asyncio
async def test_create_session_auto_id():
    """Test creating session with auto-generated ID."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    session = await store.create_session(project_name='test_project')

    assert session['session_id'] is not None
    assert len(session['session_id']) == 12
    assert session['project_name'] == 'test_project'
    assert session['capabilities'] == {}
    assert session['client_info'] == {}

    # Cleanup
    await store.delete_session(session['session_id'])
    await adapter.close()


@pytest.mark.asyncio
async def test_create_session_provided_id():
    """Test creating session with provided ID."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    session_id = 'test_async_12'
    session = await store.create_session(
        session_id=session_id,
        project_name='test_project',
        capabilities={'version': '1.0'},
        client_info={'agent': 'test'}
    )

    assert session['session_id'] == session_id
    assert session['project_name'] == 'test_project'
    assert session['capabilities'] == {'version': '1.0'}
    assert session['client_info'] == {'agent': 'test'}

    # Cleanup
    await store.delete_session(session_id)
    await adapter.close()


@pytest.mark.asyncio
async def test_get_session():
    """Test retrieving session by ID."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create session
    created = await store.create_session(
        session_id='test_get_123',
        project_name='test'
    )

    # Retrieve it
    retrieved = await store.get_session('test_get_123')

    assert retrieved is not None
    assert retrieved['session_id'] == 'test_get_123'
    assert retrieved['project_name'] == 'test'

    # Cleanup
    await store.delete_session('test_get_123')
    await adapter.close()


@pytest.mark.asyncio
async def test_get_session_not_found():
    """Test retrieving non-existent session returns None."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    result = await store.get_session('nonexistent_id')

    assert result is None

    await adapter.close()


@pytest.mark.asyncio
async def test_update_activity():
    """Test updating session activity extends expiration."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create session
    created = await store.create_session(
        session_id='test_activity',
        project_name='test'
    )
    initial_expires = created['expires_at']

    # Wait a moment
    await asyncio.sleep(0.1)

    # Update activity
    await store.update_activity('test_activity')

    # Retrieve updated session
    updated = await store.get_session('test_activity')

    assert updated['expires_at'] > initial_expires

    # Cleanup
    await store.delete_session('test_activity')
    await adapter.close()


@pytest.mark.asyncio
async def test_update_session_project():
    """Test updating session project name."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create session with default project
    await store.create_session(
        session_id='test_project_update',
        project_name='__PENDING__'
    )

    # Update project name
    result = await store.update_session_project('test_project_update', 'real_project')

    assert result is True

    # Verify update
    session = await store.get_session('test_project_update')
    assert session['project_name'] == 'real_project'

    # Cleanup
    await store.delete_session('test_project_update')
    await adapter.close()


@pytest.mark.asyncio
async def test_delete_session():
    """Test deleting a session."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create session
    await store.create_session(
        session_id='test_delete',
        project_name='test'
    )

    # Delete it
    result = await store.delete_session('test_delete')
    assert result is True

    # Verify deleted
    session = await store.get_session('test_delete')
    assert session is None

    await adapter.close()


@pytest.mark.asyncio
async def test_is_expired():
    """Test checking if session is expired."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create session that expires in the past
    past_time = datetime.now(timezone.utc) - timedelta(hours=25)
    await store.create_session(
        session_id='test_expired',
        project_name='test',
        created_at=past_time
    )

    # Check if expired
    is_expired = await store.is_expired('test_expired')
    assert is_expired is True

    # Cleanup
    await store.delete_session('test_expired')
    await adapter.close()


@pytest.mark.asyncio
async def test_cleanup_expired():
    """Test cleaning up expired sessions."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create expired session
    past_time = datetime.now(timezone.utc) - timedelta(hours=25)
    await store.create_session(
        session_id='test_cleanup_1',
        project_name='test',
        created_at=past_time
    )

    # Create active session
    await store.create_session(
        session_id='test_cleanup_2',
        project_name='test'
    )

    # Cleanup expired
    deleted_count = await store.cleanup_expired()
    assert deleted_count >= 1

    # Verify expired session is gone
    expired_session = await store.get_session('test_cleanup_1')
    assert expired_session is None

    # Verify active session still exists
    active_session = await store.get_session('test_cleanup_2')
    assert active_session is not None

    # Cleanup
    await store.delete_session('test_cleanup_2')
    await adapter.close()


@pytest.mark.asyncio
async def test_get_projects_with_stats():
    """Test getting projects list with statistics."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create sessions for different projects
    await store.create_session(
        session_id='test_proj_1',
        project_name='project_a'
    )
    await store.create_session(
        session_id='test_proj_2',
        project_name='project_b'
    )

    # Get projects
    projects = await store.get_projects_with_stats()

    # Should have at least our 2 projects
    project_names = [p['project_name'] for p in projects]
    assert 'project_a' in project_names
    assert 'project_b' in project_names

    # Verify structure
    for project in projects:
        assert 'project_name' in project
        assert 'last_used' in project
        assert 'last_used_timestamp' in project

    # Cleanup
    await store.delete_session('test_proj_1')
    await store.delete_session('test_proj_2')
    await adapter.close()


@pytest.mark.asyncio
async def test_update_session_summary():
    """Test updating session summary with tool execution."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create session with initial summary
    await adapter.execute_update("""
        INSERT INTO mcp_sessions (
            session_id, project_name, session_summary
        ) VALUES ($1, $2, $3::jsonb)
    """, [
        'test_summary',
        'test',
        '{"work_done": [], "tools_used": [], "important_context": {}}'
    ])

    # Update summary
    result = await store.update_session_summary(
        'test_summary',
        'lock_context',
        {'topic': 'api_spec'},
        'API specification locked'
    )

    assert result is True

    # Verify update
    session = await store.get_session('test_summary')
    assert 'lock_context' in session['session_summary']['tools_used']
    assert len(session['session_summary']['work_done']) > 0

    # Cleanup
    await store.delete_session('test_summary')
    await adapter.close()


@pytest.mark.asyncio
async def test_concurrent_sessions():
    """Test creating multiple sessions concurrently."""
    adapter = PostgreSQLAdapterAsync()
    await adapter.ensure_schema_exists()
    store = PostgreSQLSessionStoreAsync(adapter)

    # Create 3 sessions concurrently
    results = await asyncio.gather(
        store.create_session(project_name='test1'),
        store.create_session(project_name='test2'),
        store.create_session(project_name='test3'),
    )

    # Verify all created successfully
    assert len(results) == 3
    session_ids = [s['session_id'] for s in results]
    assert len(set(session_ids)) == 3  # All unique

    # Cleanup
    for session in results:
        await store.delete_session(session['session_id'])

    await adapter.close()


if __name__ == '__main__':
    # Run tests directly
    pytest.main([__file__, '-v'])
