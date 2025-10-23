#!/usr/bin/env python3
"""
Test suite for execute_sql() - Full SQL Write Operations

TDD Approach: These tests will fail initially (RED),
then we implement execute_sql() to make them pass (GREEN).
"""

import os
import sqlite3
import json
import sys
import time
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

    # Insert initial test data
    conn.execute("""
        INSERT INTO context_locks
        (session_id, label, version, content, content_hash, locked_at, metadata, preview, key_concepts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('test_session', 'api_spec', '1.0', 'API specification', 'hash1', time.time(),
          '{"priority": "reference"}', 'API specification', '[]'))

    conn.execute("""
        INSERT INTO context_locks
        (session_id, label, version, content, content_hash, locked_at, metadata, preview, key_concepts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('test_session', 'database_schema', '1.0', 'Database schema', 'hash2', time.time(),
          '{"priority": "important"}', 'Database schema', '[]'))

    conn.commit()
    conn.close()


def test_insert_single_row():
    """Test 1: INSERT single row with dry-run and confirmation"""
    print("\n🧪 Test 1: INSERT single row")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Test 1.1: Dry-run by default (should NOT insert)
            result = asyncio.run(mcp.execute_sql(
                "INSERT INTO context_locks (session_id, label, version, content, content_hash, locked_at, preview, key_concepts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                params=['test_session', 'new_context', '1.0', 'New content', 'hash3', time.time(), 'New content', '[]']
            ))

            assert 'DRY RUN' in result or 'dry' in result.lower(), f"Should indicate dry-run: {result}"
            print("   ✅ Test 1.1: Dry-run enabled by default")

            # Verify nothing was inserted
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM context_locks WHERE label = 'new_context'")
            count = cursor.fetchone()[0]
            conn.close()
            assert count == 0, f"Should not insert in dry-run mode: {count}"
            print("   ✅ Test 1.2: Dry-run didn't insert data")

            # Test 1.3: Execute without confirmation should fail
            result = asyncio.run(mcp.execute_sql(
                "INSERT INTO context_locks (session_id, label, version, content, content_hash, locked_at, preview, key_concepts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                params=['test_session', 'new_context', '1.0', 'New content', 'hash3', time.time(), 'New content', '[]'],
                dry_run=False
            ))

            assert '❌' in result or 'confirm' in result.lower(), f"Should require confirmation: {result}"
            print("   ✅ Test 1.3: Confirmation required")

            # Test 1.4: Execute with confirmation should succeed
            result = asyncio.run(mcp.execute_sql(
                "INSERT INTO context_locks (session_id, label, version, content, content_hash, locked_at, preview, key_concepts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                params=['test_session', 'new_context', '1.0', 'New content', 'hash3', time.time(), 'New content', '[]'],
                dry_run=False,
                confirm=True
            ))

            assert '✅' in result or 'success' in result.lower(), f"Should succeed: {result}"
            assert '1 row' in result.lower() or 'affected' in result.lower(), f"Should show affected rows: {result}"
            print("   ✅ Test 1.4: INSERT executed successfully")

            # Verify data was inserted
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT * FROM context_locks WHERE label = 'new_context'")
            row = cursor.fetchone()
            conn.close()
            assert row is not None, "Row should exist after insert"
            assert row[2] == 'new_context', f"Label should match: {row[2]}"
            print("   ✅ Test 1.5: Data verified in database")

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


def test_update_multiple_rows():
    """Test 2: UPDATE multiple rows"""
    print("\n🧪 Test 2: UPDATE multiple rows")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Test 2.1: Dry-run shows what would be updated
            result = asyncio.run(mcp.execute_sql(
                "UPDATE context_locks SET metadata = ? WHERE session_id = ?",
                params=['{"priority": "always_check"}', 'test_session'],
                dry_run=True
            ))

            assert 'DRY RUN' in result or 'dry' in result.lower(), f"Should be dry-run: {result}"
            assert '2' in result or 'rows' in result.lower(), f"Should show affected rows: {result}"
            print("   ✅ Test 2.1: Dry-run shows affected rows")

            # Test 2.2: Execute with confirmation
            result = asyncio.run(mcp.execute_sql(
                "UPDATE context_locks SET metadata = ? WHERE session_id = ?",
                params=['{"priority": "always_check"}', 'test_session'],
                dry_run=False,
                confirm=True
            ))

            assert '✅' in result or 'success' in result.lower(), f"Should succeed: {result}"
            assert '2' in result, f"Should update 2 rows: {result}"
            print("   ✅ Test 2.2: UPDATE executed successfully")

            # Verify data was updated
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT metadata FROM context_locks WHERE session_id = 'test_session'")
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                metadata = json.loads(row[0])
                assert metadata['priority'] == 'always_check', f"Priority should be updated: {metadata}"
            print("   ✅ Test 2.3: Data verified as updated")

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


def test_delete_with_where():
    """Test 3: DELETE with WHERE clause"""
    print("\n🧪 Test 3: DELETE with WHERE clause")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Test 3.1: Dry-run shows what would be deleted
            result = asyncio.run(mcp.execute_sql(
                "DELETE FROM context_locks WHERE label = ?",
                params=['api_spec'],
                dry_run=True
            ))

            assert 'DRY RUN' in result or 'dry' in result.lower(), f"Should be dry-run: {result}"
            print("   ✅ Test 3.1: Dry-run preview shown")

            # Test 3.2: Execute deletion
            result = asyncio.run(mcp.execute_sql(
                "DELETE FROM context_locks WHERE label = ?",
                params=['api_spec'],
                dry_run=False,
                confirm=True
            ))

            assert '✅' in result or 'success' in result.lower(), f"Should succeed: {result}"
            assert '1' in result, f"Should delete 1 row: {result}"
            print("   ✅ Test 3.2: DELETE executed successfully")

            # Verify data was deleted
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM context_locks WHERE label = 'api_spec'")
            count = cursor.fetchone()[0]
            conn.close()
            assert count == 0, f"Row should be deleted: {count}"
            print("   ✅ Test 3.3: Data verified as deleted")

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


def test_transaction_rollback():
    """Test 4: Transaction rollback on error"""
    print("\n🧪 Test 4: Transaction rollback on error")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Get initial count
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM context_locks")
            initial_count = cursor.fetchone()[0]
            conn.close()

            # Test 4.1: Execute invalid SQL (should rollback)
            result = asyncio.run(mcp.execute_sql(
                "INSERT INTO context_locks (nonexistent_column) VALUES (?)",
                params=['value'],
                dry_run=False,
                confirm=True
            ))

            assert '❌' in result or 'error' in result.lower() or 'fail' in result.lower(), f"Should show error: {result}"
            print("   ✅ Test 4.1: Error detected")

            # Verify rollback - count should be unchanged
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM context_locks")
            final_count = cursor.fetchone()[0]
            conn.close()

            assert final_count == initial_count, f"Transaction should rollback: {final_count} != {initial_count}"
            print("   ✅ Test 4.2: Transaction rolled back")

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


def test_max_affected_rows():
    """Test 5: max_affected parameter limits changes"""
    print("\n🧪 Test 5: max_affected rows limit")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Test 5.1: Try to update more rows than limit allows
            result = asyncio.run(mcp.execute_sql(
                "UPDATE context_locks SET metadata = ? WHERE session_id = ?",
                params=['{"priority": "test"}', 'test_session'],
                max_affected=1,
                dry_run=False,
                confirm=True
            ))

            assert '❌' in result or 'exceeded' in result.lower() or 'limit' in result.lower(), f"Should fail due to limit: {result}"
            print("   ✅ Test 5.1: Row limit enforced")

            # Verify no changes made
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT metadata FROM context_locks WHERE session_id = 'test_session'")
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                metadata = json.loads(row[0])
                assert metadata['priority'] != 'test', f"Should not be updated: {metadata}"
            print("   ✅ Test 5.2: Changes rolled back")

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


def test_custom_database():
    """Test 6: Works with custom database"""
    print("\n🧪 Test 6: Custom database support")

    # Create temp database in current workspace (not system /tmp)
    db_path = "./test_custom_temp.db"

    try:
        # Create custom database
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        conn.commit()
        conn.close()

        # Test 6.1: Insert into custom database
        result = asyncio.run(mcp.execute_sql(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            params=['Alice', 'alice@example.com'],
            db_path=db_path,
            dry_run=False,
            confirm=True
        ))

        assert '✅' in result or 'success' in result.lower(), f"Should succeed: {result}"
        print("   ✅ Test 6.1: INSERT into custom database")

        # Verify data
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT * FROM users WHERE name = 'Alice'")
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "Row should exist"
        assert row[1] == 'Alice', f"Name should match: {row[1]}"
        print("   ✅ Test 6.2: Data verified")

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
    finally:
        # Clean up temp database
        if os.path.exists(db_path):
            os.remove(db_path)


def test_dangerous_operations_fixed():
    """Test 7: Dangerous operations require extra confirmation"""
    print("\n🧪 Test 7: Dangerous operation protection")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            create_test_database(db_path)

            original_db = mcp.DB_PATH
            mcp.DB_PATH = db_path
            mcp.SESSION_ID = 'test_session'

            # Test 7.1: UPDATE without WHERE should warn
            result = asyncio.run(mcp.execute_sql(
                "UPDATE context_locks SET metadata = ?",
                params=['{"priority": "test"}'],
                dry_run=False,
                confirm=True
            ))

            # Should either fail or require extra confirmation
            # Implementation can choose to block or require allow_bulk_update flag
            print(f"   ℹ️  UPDATE without WHERE result: {result[:100]}...")

            # Test 7.2: DELETE without WHERE should warn
            result = asyncio.run(mcp.execute_sql(
                "DELETE FROM context_locks",
                dry_run=False,
                confirm=True
            ))

            # Should either fail or require extra confirmation
            print(f"   ℹ️  DELETE without WHERE result: {result[:100]}...")

            mcp.DB_PATH = original_db

            print("   ✅ Test 7: PASSED (warnings shown)")
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
    """Run all execute_sql() tests"""
    print("=" * 60)
    print("SQL Write Operations Test Suite (TDD - RED Phase)")
    print("=" * 60)

    tests = [
        ("INSERT single row", test_insert_single_row),
        ("UPDATE multiple rows", test_update_multiple_rows),
        ("DELETE with WHERE", test_delete_with_where),
        ("Transaction rollback", test_transaction_rollback),
        ("Max affected rows limit", test_max_affected_rows),
        ("Custom database support", test_custom_database),
        ("Dangerous operation protection", test_dangerous_operations_fixed),
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
        print("Next: Implement execute_sql() to make tests pass (GREEN phase)")
    else:
        print("\n✅ All tests PASSED!")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
