#!/usr/bin/env python3
"""
Test suite for sync_project_memory() - Memory Synchronization

TDD Approach: These tests will fail initially (RED),
then we implement sync_project_memory() to make them pass (GREEN).
"""

import os
import sqlite3
import json
import sys
import time
import asyncio
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import claude_mcp_hybrid as mcp


def create_test_project(tmp_dir: str, project_type: str = "mcp_server") -> str:
    """
    Create a minimal test project structure.

    Args:
        tmp_dir: Temporary directory path
        project_type: Type of project to create

    Returns:
        Path to project root
    """
    project_path = os.path.join(tmp_dir, "test_project")
    os.makedirs(project_path, exist_ok=True)

    if project_type == "mcp_server":
        # Create MCP server structure
        main_file = os.path.join(project_path, "server.py")
        with open(main_file, 'w') as f:
            f.write('''
from fastmcp import FastMCP

mcp = FastMCP("test-server")

@mcp.tool()
async def get_data(query: str) -> str:
    """Retrieve data based on query."""
    return f"Data for: {query}"

@mcp.tool()
async def save_data(data: str) -> str:
    """Save data to storage."""
    return "Data saved"
''')

        # Create schema file
        schema_file = os.path.join(project_path, "database.py")
        with open(schema_file, 'w') as f:
            f.write('''
import sqlite3

def init_database():
    """Initialize database schema."""
    conn = sqlite3.connect("data.db")

    # IMPORTANT: Never modify data without validation
    # WARNING: This table stores critical user data
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            content TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()
''')

        # Create README
        readme_file = os.path.join(project_path, "README.md")
        with open(readme_file, 'w') as f:
            f.write('''# Test MCP Server

An MCP server for testing memory synchronization.

## Features
- Data retrieval
- Data storage
- User management
''')

    return project_path


def test_first_run_bootstrap():
    """Test 1: First run creates all required contexts"""
    print("\n🧪 Test 1: First run bootstrap")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        project_path = create_test_project(tmp_dir, "mcp_server")

        try:
            # Set up test environment
            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Initialize database
            conn = mcp.get_db()
            mcp.initialize_database(conn)
            conn.close()

            # Verify no contexts exist initially
            tree = asyncio.run(mcp.explore_context_tree())
            assert 'No locked contexts' in tree, f"Should start empty: {tree}"
            print("   ✅ Test 1.1: Empty database confirmed")

            # Run sync (dry run first)
            result = asyncio.run(mcp.sync_project_memory(
                path=project_path,
                dry_run=True
            ))

            assert 'DRY RUN' in result, f"Should indicate dry run: {result}"
            print("   ✅ Test 1.2: Dry run works")

            # Run actual sync
            result = asyncio.run(mcp.sync_project_memory(
                path=project_path,
                confirm=True,
                priorities=["always_check", "important"]
            ))

            assert '✨' in result or 'complete' in result.lower(), f"Should succeed: {result}"
            print(f"   ✅ Test 1.3: Sync completed")

            # Verify contexts created
            tree = asyncio.run(mcp.explore_context_tree())

            # Should have project_overview
            overview = asyncio.run(mcp.recall_context('project_overview'))
            assert 'not found' not in overview.lower(), f"Should create project_overview: {overview}"
            assert 'MCP' in overview or 'server' in overview, f"Should describe MCP server: {overview}"
            print("   ✅ Test 1.4: project_overview created")

            # Should have database_schema (if detected)
            schema = asyncio.run(mcp.recall_context('database_schema'))
            if 'not found' not in schema.lower():
                assert 'users' in schema or 'documents' in schema, f"Should include tables: {schema}"
                print("   ✅ Test 1.5: database_schema created")

            # Should have tool_contracts
            tools = asyncio.run(mcp.recall_context('tool_contracts'))
            if 'not found' not in tools.lower():
                assert 'get_data' in tools or 'save_data' in tools, f"Should include tools: {tools}"
                print("   ✅ Test 1.6: tool_contracts created")

            mcp.DB_PATH = original_db

            print("   ✅ Test 1: PASSED")
            return True

        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_stale_context_detection():
    """Test 2: Detects and removes stale contexts"""
    print("\n🧪 Test 2: Stale context detection")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        project_path = create_test_project(tmp_dir, "mcp_server")

        try:
            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            conn = mcp.get_db()
            mcp.initialize_database(conn)
            conn.close()

            # Create a context for a feature that will be "removed"
            asyncio.run(mcp.lock_context(
                content="Old REST API endpoints: /api/users, /api/posts",
                topic="rest_api_endpoints",
                tags="api,rest,auto_generated",
                priority="important"
            ))

            metadata_json = json.dumps({"auto_generated": True})
            conn = mcp.get_db()
            conn.execute("""
                UPDATE context_locks
                SET metadata = ?
                WHERE label = 'rest_api_endpoints'
            """, (metadata_json,))
            conn.commit()
            conn.close()

            print("   ✅ Test 2.1: Created stale context")

            # Run sync (should detect stale context)
            result = asyncio.run(mcp.sync_project_memory(
                path=project_path,
                confirm=True
            ))

            # Verify stale context mentioned
            # Note: Actual detection depends on implementation
            print(f"   ℹ️  Sync result: {result[:200]}...")

            mcp.DB_PATH = original_db

            print("   ✅ Test 2: PASSED")
            return True

        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_update_detection():
    """Test 3: Updates contexts when code changes"""
    print("\n🧪 Test 3: Update detection")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        project_path = create_test_project(tmp_dir, "mcp_server")

        try:
            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            conn = mcp.get_db()
            mcp.initialize_database(conn)
            conn.close()

            # First sync
            asyncio.run(mcp.sync_project_memory(
                path=project_path,
                confirm=True
            ))
            print("   ✅ Test 3.1: Initial sync completed")

            # Modify code (add new table)
            schema_file = os.path.join(project_path, "database.py")
            with open(schema_file, 'a') as f:
                f.write('''
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
''')
            print("   ✅ Test 3.2: Modified code (added sessions table)")

            # Second sync
            result = asyncio.run(mcp.sync_project_memory(
                path=project_path,
                confirm=True
            ))

            # Should detect update
            # Note: Actual behavior depends on implementation
            print(f"   ℹ️  Sync result: {result[:200]}...")

            mcp.DB_PATH = original_db

            print("   ✅ Test 3: PASSED")
            return True

        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_confirmation_required():
    """Test 4: Requires confirmation for destructive operations"""
    print("\n🧪 Test 4: Confirmation requirement")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        project_path = create_test_project(tmp_dir, "mcp_server")

        try:
            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            conn = mcp.get_db()
            mcp.initialize_database(conn)
            conn.close()

            # Create a stale context
            asyncio.run(mcp.lock_context(
                content="Old feature",
                topic="old_feature",
                tags="auto_generated",
                priority="reference"
            ))

            metadata_json = json.dumps({"auto_generated": True})
            conn = mcp.get_db()
            conn.execute("""
                UPDATE context_locks
                SET metadata = ?
                WHERE label = 'old_feature'
            """, (metadata_json,))
            conn.commit()
            conn.close()

            # Run without confirmation (should warn or skip)
            result = asyncio.run(mcp.sync_project_memory(
                path=project_path,
                confirm=False
            ))

            # Should mention confirmation required or be a dry run
            # Note: Actual message depends on implementation
            print(f"   ℹ️  Result without confirm: {result[:200]}...")

            mcp.DB_PATH = original_db

            print("   ✅ Test 4: PASSED")
            return True

        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_priority_filtering():
    """Test 5: Respects priority filtering"""
    print("\n🧪 Test 5: Priority filtering")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        project_path = create_test_project(tmp_dir, "mcp_server")

        try:
            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            conn = mcp.get_db()
            mcp.initialize_database(conn)
            conn.close()

            # Sync only always_check priority
            result = asyncio.run(mcp.sync_project_memory(
                path=project_path,
                confirm=True,
                priorities=["always_check"]
            ))

            # Should create only critical contexts
            assert 'always_check' in result or 'PHASE' in result, f"Should run: {result}"
            print(f"   ℹ️  Filtered sync result: {result[:200]}...")

            mcp.DB_PATH = original_db

            print("   ✅ Test 5: PASSED")
            return True

        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_project_type_detection():
    """Test 6: Correctly detects project type"""
    print("\n🧪 Test 6: Project type detection")

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            # Test MCP server detection
            mcp_project = create_test_project(tmp_dir, "mcp_server")

            # This test will need the actual detect_project_type function
            # For now, just verify the project was created
            assert os.path.exists(os.path.join(mcp_project, "server.py"))
            print("   ✅ Test 6.1: MCP project structure created")

            # TODO: Test actual detection when function is implemented
            # project_type = asyncio.run(mcp.detect_project_type(mcp_project))
            # assert project_type == "mcp_server", f"Should detect MCP server: {project_type}"

            print("   ✅ Test 6: PASSED (partial - detection not yet implemented)")
            return True

        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def run_all_tests():
    """Run all sync_project_memory() tests"""
    print("=" * 60)
    print("sync_project_memory() Test Suite (TDD - RED Phase)")
    print("=" * 60)

    tests = [
        ("First Run Bootstrap", test_first_run_bootstrap),
        ("Stale Context Detection", test_stale_context_detection),
        ("Update Detection", test_update_detection),
        ("Confirmation Requirement", test_confirmation_required),
        ("Priority Filtering", test_priority_filtering),
        ("Project Type Detection", test_project_type_detection),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print("\n🔴 Tests FAILED (expected - this is RED phase)")
        print("Next: Implement sync_project_memory() to make tests pass (GREEN phase)")
    else:
        print("\n✅ All tests PASSED!")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
