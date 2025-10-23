#!/usr/bin/env python3
"""
Test suite for database query tools - query_database() and inspect_database()

TDD Approach: These tests will fail initially (RED),
then we implement the tools to make them pass (GREEN).
"""

import os
import sqlite3
import json
import sys
import asyncio
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import claude_mcp_hybrid as mcp


def create_test_database(db_path: str):
    """Create test database with sample data"""
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Initialize schema
    mcp.initialize_database(conn)

    # Insert test data
    import time

    # Add some contexts
    contexts = [
        ('api_spec', '1.0', 'API v1.0 specification', '{"tags": ["api"], "priority": "important"}'),
        ('api_spec', '1.1', 'API v1.1 specification', '{"tags": ["api"], "priority": "important"}'),
        ('database_schema', '1.0', 'CREATE TABLE users (id, name)', '{"tags": ["schema"], "priority": "always_check"}'),
        ('test_context', '1.0', 'Test content', '{"tags": ["test"], "priority": "reference"}'),
    ]

    for label, version, content, metadata in contexts:
        conn.execute("""
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, locked_at, metadata, preview, key_concepts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('test_session', label, version, content, 'hash', time.time(), metadata, content[:50], '[]'))

    # Add some memories
    conn.execute("""
        INSERT INTO memory_entries (session_id, category, content, timestamp)
        VALUES (?, ?, ?, ?)
    """, ('test_session', 'progress', 'Test memory', time.time()))

    # Add an archive
    conn.execute("""
        INSERT INTO context_archives
        (original_id, session_id, label, version, content, deleted_at, delete_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (1, 'test_session', 'old_context', '1.0', 'Old content', time.time(), 'No longer needed'))

    conn.commit()
    conn.close()


def test_query_database_basic_select():
    """Test 1: Basic SELECT query works"""
    print("\n🧪 Test 1: Basic SELECT query")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Query all contexts
            result = asyncio.run(mcp.query_database(
                "SELECT label, version FROM context_locks"
            ))

            assert '✅' in result or 'api_spec' in result, f"Should return results: {result}"
            assert 'api_spec' in result, f"Should include api_spec: {result}"
            assert 'database_schema' in result, f"Should include database_schema: {result}"
            print("   ✅ Test 1.1: Query executed successfully")

            # Check row count in output
            assert '4 rows' in result or 'rows' in result.lower(), f"Should show row count: {result}"
            print("   ✅ Test 1.2: Row count displayed")

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


def test_query_database_with_params():
    """Test 2: Parameterized queries work"""
    print("\n🧪 Test 2: Parameterized queries")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Query with parameter
            result = asyncio.run(mcp.query_database(
                "SELECT label, version FROM context_locks WHERE label = ?",
                params=['api_spec']
            ))

            assert 'api_spec' in result, f"Should find api_spec: {result}"
            assert 'database_schema' not in result, f"Should NOT include database_schema: {result}"
            assert '2 rows' in result, f"Should show 2 rows: {result}"
            print("   ✅ Test 2.1: Parameterized query works")

            # Query with LIKE
            result = asyncio.run(mcp.query_database(
                "SELECT label FROM context_locks WHERE label LIKE ?",
                params=['%api%']
            ))

            assert 'api_spec' in result, f"Should match LIKE pattern: {result}"
            print("   ✅ Test 2.2: LIKE queries work")

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


def test_query_database_blocks_unsafe():
    """Test 3: Blocks unsafe queries (INSERT/UPDATE/DELETE)"""
    print("\n🧪 Test 3: Block unsafe queries")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Try INSERT
            result = asyncio.run(mcp.query_database(
                "INSERT INTO context_locks (label) VALUES ('bad')"
            ))
            assert '❌' in result and 'SELECT' in result, f"Should block INSERT: {result}"
            print("   ✅ Test 3.1: Blocks INSERT")

            # Try UPDATE
            result = asyncio.run(mcp.query_database(
                "UPDATE context_locks SET label = 'bad'"
            ))
            assert '❌' in result, f"Should block UPDATE: {result}"
            print("   ✅ Test 3.2: Blocks UPDATE")

            # Try DELETE
            result = asyncio.run(mcp.query_database(
                "DELETE FROM context_locks"
            ))
            assert '❌' in result, f"Should block DELETE: {result}"
            print("   ✅ Test 3.3: Blocks DELETE")

            # Try DROP
            result = asyncio.run(mcp.query_database(
                "DROP TABLE context_locks"
            ))
            assert '❌' in result, f"Should block DROP: {result}"
            print("   ✅ Test 3.4: Blocks DROP")

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


def test_query_database_formats():
    """Test 4: Different output formats work"""
    print("\n🧪 Test 4: Output formats")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # JSON format
            result = asyncio.run(mcp.query_database(
                "SELECT label, version FROM context_locks LIMIT 1",
                format="json"
            ))
            # Should be valid JSON
            parsed = json.loads(result)
            assert isinstance(parsed, list), f"JSON should be a list: {result}"
            assert 'label' in parsed[0], f"JSON should have label field: {result}"
            print("   ✅ Test 4.1: JSON format works")

            # Table format (default)
            result = asyncio.run(mcp.query_database(
                "SELECT label FROM context_locks LIMIT 1",
                format="table"
            ))
            assert 'label' in result, f"Table should have header: {result}"
            assert '-' in result, f"Table should have separator: {result}"
            print("   ✅ Test 4.2: Table format works")

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


def test_inspect_database_overview():
    """Test 5: inspect_database() overview works"""
    print("\n🧪 Test 5: inspect_database() overview")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Get overview
            result = asyncio.run(mcp.inspect_database("overview"))

            assert 'contexts' in result.lower() or 'locked' in result.lower(), f"Should show contexts: {result}"
            assert '4' in result, f"Should show 4 contexts: {result}"
            print("   ✅ Test 5.1: Overview shows context count")

            assert 'memories' in result.lower(), f"Should show memories: {result}"
            print("   ✅ Test 5.2: Overview shows memory count")

            assert 'archives' in result.lower() or 'archived' in result.lower(), f"Should show archives: {result}"
            print("   ✅ Test 5.3: Overview shows archive count")

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


def test_inspect_database_schema():
    """Test 6: inspect_database() shows schema"""
    print("\n🧪 Test 6: inspect_database() schema")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Get schema
            result = asyncio.run(mcp.inspect_database("schema"))

            assert 'context_locks' in result, f"Should show context_locks table: {result}"
            assert 'memory_entries' in result or 'memory' in result, f"Should show memory table: {result}"
            assert 'context_archives' in result, f"Should show archives table: {result}"
            print("   ✅ Test 6.1: Shows all tables")

            # Should show columns
            assert 'label' in result, f"Should show column names: {result}"
            assert 'version' in result, f"Should show version column: {result}"
            print("   ✅ Test 6.2: Shows column names")

            mcp.DB_PATH = original_db

            print("   ✅ Test 6: PASSED")
            return True

        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_inspect_database_contexts():
    """Test 7: inspect_database() lists contexts"""
    print("\n🧪 Test 7: inspect_database() contexts")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # List all contexts
            result = asyncio.run(mcp.inspect_database("contexts"))

            assert 'api_spec' in result, f"Should list api_spec: {result}"
            assert 'database_schema' in result, f"Should list database_schema: {result}"
            print("   ✅ Test 7.1: Lists contexts")

            # With filter
            result = asyncio.run(mcp.inspect_database("contexts", filter_text="api"))

            assert 'api_spec' in result, f"Should find api_spec: {result}"
            print("   ✅ Test 7.2: Filter works")

            mcp.DB_PATH = original_db

            print("   ✅ Test 7: PASSED")
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
    """Run all database tool tests"""
    print("=" * 60)
    print("Database Query Tools Test Suite (TDD - RED Phase)")
    print("=" * 60)

    tests = [
        ("Basic SELECT Query", test_query_database_basic_select),
        ("Parameterized Queries", test_query_database_with_params),
        ("Block Unsafe Queries", test_query_database_blocks_unsafe),
        ("Output Formats", test_query_database_formats),
        ("Inspect Overview", test_inspect_database_overview),
        ("Inspect Schema", test_inspect_database_schema),
        ("Inspect Contexts", test_inspect_database_contexts),
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
        print("Next: Implement query_database() and inspect_database() (GREEN phase)")
    else:
        print("\n✅ All tests PASSED!")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
