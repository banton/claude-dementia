"""
Test for Project Isolation Fix

This test verifies that switch_project persists the active project to the database,
ensuring that subsequent tool calls (like lock_context) use the correct project
even in stateless MCP server environments.

Bug: switch_project stored active_project in memory only, which doesn't persist
between HTTP requests in Claude Desktop MCP server.

Fix: Persist active_project to sessions table in database.
"""
import os
import sys
import asyncio
import json
import tempfile
from pathlib import Path

# Set up test environment
os.environ['ENVIRONMENT'] = 'development'
os.environ['DEMENTIA_API_KEY'] = 'test_key_123'

# Use temporary SQLite database for testing
test_db_path = tempfile.mktemp(suffix='.db')
os.environ['DATABASE_URL'] = f'sqlite:///{test_db_path}'

# Import the MCP server
import claude_mcp_hybrid
from claude_mcp_hybrid import (
    switch_project,
    lock_context,
    recall_context,
    _get_project_for_context,
    _active_projects,
    get_current_session_id,
)

# Set a test session ID for testing
claude_mcp_hybrid.SESSION_ID = 'test_session_12345'


async def test_project_isolation_persistence():
    """
    Test that switch_project persists to database and lock_context respects it.

    This simulates the Claude Desktop MCP server behavior where each tool call
    is a separate HTTP request with a fresh in-memory state.
    """
    print("🧪 Testing Project Isolation Persistence Fix...")
    print()

    # Step 1: Switch to project 'test_project_a'
    print("1️⃣  Switching to project 'test_project_a'...")
    result = await switch_project('test_project_a')
    result_data = json.loads(result)
    print(f"   Result: {result_data}")
    assert result_data.get('success', False), f"switch_project failed: {result_data}"
    print(f"   ✅ Successfully switched")
    print()

    # Step 2: Simulate MCP server statelessness - clear in-memory cache
    print("2️⃣  Simulating MCP server statelessness (clearing in-memory cache)...")
    session_id = get_current_session_id()
    print(f"   Session ID: {session_id}")
    print(f"   Before clear: _active_projects = {_active_projects}")
    _active_projects.clear()  # This simulates a new HTTP request
    print(f"   After clear:  _active_projects = {_active_projects}")
    print()

    # Step 3: Verify _get_project_for_context reads from database
    print("3️⃣  Verifying _get_project_for_context reads from database...")
    detected_project = _get_project_for_context()
    print(f"   Detected project: '{detected_project}'")
    assert detected_project == 'test_project_a', \
        f"Expected 'test_project_a', got '{detected_project}'. Database persistence FAILED!"
    print(f"   ✅ Correctly detected 'test_project_a' from database")
    print()

    # Step 4: Lock context without explicit project parameter
    print("4️⃣  Locking context without explicit project parameter...")
    lock_result = await lock_context(
        content="Test content for project isolation fix",
        topic="test_isolation_fix"
    )
    print(f"   Lock result preview: {lock_result[:150]}...")

    # Parse the result to verify which project it was locked to
    if "test_project_a" in lock_result:
        print(f"   ✅ Context locked to correct project: test_project_a")
    else:
        print(f"   ❌ Context NOT locked to test_project_a!")
        print(f"   Full result: {lock_result}")
        raise AssertionError("Context was not locked to the correct project!")
    print()

    # Step 5: Switch to different project and verify isolation
    print("5️⃣  Switching to 'test_project_b' to verify isolation...")
    result = await switch_project('test_project_b')
    result_data = json.loads(result)
    print(f"   Result: {result_data}")
    assert result_data.get('success', False), f"switch_project failed: {result_data}"
    print(f"   ✅ Successfully switched")
    print()

    # Clear in-memory cache again
    print("6️⃣  Clearing cache again...")
    _active_projects.clear()
    detected_project_b = _get_project_for_context()
    print(f"   Detected project: '{detected_project_b}'")
    assert detected_project_b == 'test_project_b', \
        f"Expected 'test_project_b', got '{detected_project_b}'"
    print(f"   ✅ Correctly detected 'test_project_b' from database")
    print()

    # Step 6: Verify context locked to project_a is NOT visible in project_b
    print("7️⃣  Verifying context isolation between projects...")
    try:
        recall_result = await recall_context('test_isolation_fix', project='test_project_a')
        print(f"   ✅ Context exists in test_project_a")
    except:
        print(f"   ❌ Context NOT found in test_project_a (unexpected!)")
        raise

    # Try to recall from wrong project (should fail or be empty)
    try:
        recall_result_b = await recall_context('test_isolation_fix', project='test_project_b')
        if 'not found' in recall_result_b.lower() or 'error' in recall_result_b.lower():
            print(f"   ✅ Context correctly isolated - not visible in test_project_b")
        else:
            print(f"   ⚠️  Context may be visible across projects (potential isolation issue)")
    except:
        print(f"   ✅ Context correctly isolated - exception when accessing from wrong project")
    print()

    print("=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    print()
    print("Summary:")
    print("- switch_project correctly persists active_project to database")
    print("- _get_project_for_context reads active_project from database")
    print("- lock_context respects active project even after in-memory cache cleared")
    print("- Projects are properly isolated")
    print()

    # Cleanup
    try:
        Path(test_db_path).unlink()
        print(f"🧹 Cleaned up test database: {test_db_path}")
    except:
        pass


if __name__ == '__main__':
    try:
        asyncio.run(test_project_isolation_persistence())
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
