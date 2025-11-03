"""
Unit Test for Project Isolation Database Persistence Fix

This test verifies that _get_project_for_context can read the active_project
from the database when the in-memory cache is empty (simulating MCP server statelessness).

Bug: _get_project_for_context only checked in-memory _active_projects dict,
     which doesn't persist between HTTP requests in Claude Desktop MCP server.

Fix: _get_project_for_context now queries the sessions table for active_project.
"""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

# Set up test environment
os.environ['ENVIRONMENT'] = 'development'
test_db_path = tempfile.mktemp(suffix='.db')
os.environ['DATABASE_URL'] = f'{test_db_path}'  # Direct path for SQLite

# Import the MCP server
import claude_mcp_hybrid
from claude_mcp_hybrid import (
    _get_project_for_context,
    _active_projects,
    get_current_session_id,
    get_db,
)

# Set a test session ID
claude_mcp_hybrid.SESSION_ID = 'test_session_12345'


def test_active_project_database_persistence():
    """
    Test that _get_project_for_context reads active_project from database
    when in-memory cache is empty.
    """
    print("🧪 Testing _get_project_for_context Database Persistence...")
    print()

    # Step 1: Get database connection and ensure sessions table exists
    print("1️⃣  Setting up test database...")
    conn = get_db()
    session_id = get_current_session_id()
    print(f"   Session ID: {session_id}")

    # Ensure session exists
    cursor = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
    if not cursor.fetchone():
        print(f"   Creating session...")
        import time
        conn.execute(
            "INSERT INTO sessions (id, started_at, last_active) VALUES (?, ?, ?)",
            (session_id, time.time(), time.time())
        )
        conn.commit()
    print(f"   ✅ Database setup complete")
    print()

    # Step 2: Manually set active_project in database
    print("2️⃣  Setting active_project='test_project_a' in database...")
    conn.execute(
        "UPDATE sessions SET active_project = ? WHERE id = ?",
        ('test_project_a', session_id)
    )
    conn.commit()

    # Verify it was saved
    cursor = conn.execute(
        "SELECT active_project FROM sessions WHERE id = ?",
        (session_id,)
    )
    saved_project = cursor.fetchone()
    if saved_project:
        print(f"   Saved project: {saved_project[0]}")
        assert saved_project[0] == 'test_project_a', "Database write failed!"
        print(f"   ✅ Successfully saved to database")
    else:
        raise AssertionError("No session found after update!")
    print()

    # Step 3: Clear in-memory cache (simulate MCP server new request)
    print("3️⃣  Clearing in-memory cache (simulating new HTTP request)...")
    print(f"   Before: _active_projects = {_active_projects}")
    _active_projects.clear()
    print(f"   After:  _active_projects = {_active_projects}")
    print()

    # Step 4: Call _get_project_for_context (should read from database)
    print("4️⃣  Calling _get_project_for_context()...")
    detected_project = _get_project_for_context()
    print(f"   Detected project: '{detected_project}'")
    print()

    # Step 5: Verify it read from database
    if detected_project == 'test_project_a':
        print("✅ SUCCESS! _get_project_for_context correctly read from database!")
        print()
        print("   This proves the fix works:")
        print("   - In-memory cache was empty")
        print("   - Database had active_project='test_project_a'")
        print("   - _get_project_for_context() returned 'test_project_a'")
        print("   - Therefore, it read from database successfully!")
    else:
        print(f"❌ FAILED! Expected 'test_project_a', got '{detected_project}'")
        print()
        print("   This means _get_project_for_context is NOT reading from database.")
        raise AssertionError(f"Database read failed! Got '{detected_project}' instead of 'test_project_a'")

    print()
    print("=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    print()
    print("The fix ensures that even when the MCP server starts fresh (empty memory),")
    print("it can retrieve the active project from the database and maintain project")
    print("isolation across HTTP requests in Claude Desktop.")
    print()

    # Cleanup
    conn.close()
    try:
        Path(test_db_path).unlink()
        print(f"🧹 Cleaned up test database: {test_db_path}")
    except:
        pass


if __name__ == '__main__':
    try:
        test_active_project_database_persistence()
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
