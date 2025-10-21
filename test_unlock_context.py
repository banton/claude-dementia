#!/usr/bin/env python3
"""
Test suite for unlock_context() - DELETE operation

TDD Approach: These tests will fail initially (RED),
then we implement unlock_context() to make them pass (GREEN).
"""

import os
import sqlite3
import json
import sys
import time
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import claude_mcp_hybrid as mcp


def create_test_database_with_versions(db_path: str):
    """Create test database with multiple versions of contexts"""
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create v4.1 schema
    conn.execute('''
        CREATE TABLE context_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0',
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lock_source TEXT DEFAULT 'user',
            metadata TEXT,
            preview TEXT,
            key_concepts TEXT,
            last_accessed TIMESTAMP,
            UNIQUE(session_id, label, version)
        )
    ''')

    # Create archives table
    conn.execute('''
        CREATE TABLE context_archives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version TEXT NOT NULL,
            content TEXT NOT NULL,
            preview TEXT,
            key_concepts TEXT,
            metadata TEXT,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delete_reason TEXT
        )
    ''')

    # Insert multiple versions of api_spec
    contexts = [
        ('api_spec', '1.0', 'API v1.0', '{"priority": "reference"}'),
        ('api_spec', '1.1', 'API v1.1', '{"priority": "reference"}'),
        ('api_spec', '1.2', 'API v1.2', '{"priority": "important"}'),
        ('critical_rule', '1.0', 'ALWAYS check auth', '{"priority": "always_check"}'),
        ('test_context', '1.0', 'Test data', '{"priority": "reference"}'),
    ]

    for label, version, content, metadata in contexts:
        conn.execute("""
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, locked_at, metadata, preview, key_concepts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('test_session', label, version, content, 'hash_' + version,
              time.time(), metadata, content, '[]'))

    conn.commit()
    conn.close()


def test_delete_all_versions():
    """Test 1: Delete all versions removes all"""
    print("\n🧪 Test 1: Delete all versions")

    db_path = "test_unlock_1.db"
    try:
        create_test_database_with_versions(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Delete all versions of api_spec
        result = asyncio.run(mcp.unlock_context(topic='api_spec', version='all'))

        assert '✅' in result, f"Should succeed: {result}"
        assert '3' in result, f"Should mention 3 versions deleted: {result}"
        print(f"   ✅ Test 1.1: Delete succeeded: {result}")

        # Verify all versions deleted
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM context_locks
            WHERE label = 'api_spec'
        """)
        count = cursor.fetchone()['count']

        assert count == 0, f"All versions should be deleted, found {count}"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 1.2: All versions removed from database")
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
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_delete_specific_version():
    """Test 2: Delete specific version removes only that one"""
    print("\n🧪 Test 2: Delete specific version")

    db_path = "test_unlock_2.db"
    try:
        create_test_database_with_versions(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Delete only v1.1
        result = asyncio.run(mcp.unlock_context(topic='api_spec', version='1.1'))

        assert '✅' in result, f"Should succeed: {result}"
        print(f"   ✅ Test 2.1: Delete succeeded")

        # Verify only v1.1 deleted
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT version FROM context_locks
            WHERE label = 'api_spec' ORDER BY version
        """)
        versions = [row['version'] for row in cursor.fetchall()]

        assert '1.0' in versions, "v1.0 should still exist"
        assert '1.2' in versions, "v1.2 should still exist"
        assert '1.1' not in versions, "v1.1 should be deleted"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 2.2: Only specified version deleted")
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
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_delete_latest_version():
    """Test 3: Delete latest keeps old versions"""
    print("\n🧪 Test 3: Delete latest version")

    db_path = "test_unlock_3.db"
    try:
        create_test_database_with_versions(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Delete latest (v1.2)
        result = asyncio.run(mcp.unlock_context(topic='api_spec', version='latest'))

        assert '✅' in result, f"Should succeed: {result}"

        # Verify v1.2 deleted but v1.0, v1.1 remain
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT version FROM context_locks
            WHERE label = 'api_spec' ORDER BY version
        """)
        versions = [row['version'] for row in cursor.fetchall()]

        assert '1.0' in versions, "v1.0 should still exist"
        assert '1.1' in versions, "v1.1 should still exist"
        assert '1.2' not in versions, "v1.2 (latest) should be deleted"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 3: Latest deleted, old versions preserved")
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
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_delete_critical_requires_force():
    """Test 4: Delete always_check requires force=True"""
    print("\n🧪 Test 4: Delete critical context requires force")

    db_path = "test_unlock_4.db"
    try:
        create_test_database_with_versions(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Try to delete always_check without force
        result = asyncio.run(mcp.unlock_context(topic='critical_rule', version='all'))

        assert '⚠️' in result or 'force' in result.lower(), \
            f"Should require force for critical context: {result}"
        print(f"   ✅ Test 4.1: Requires force for critical context")

        # Verify not deleted
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM context_locks
            WHERE label = 'critical_rule'
        """)
        count = cursor.fetchone()['count']

        assert count == 1, f"Critical context should not be deleted without force, but count is {count}"

        conn.close()

        # Now delete with force=True
        result = asyncio.run(mcp.unlock_context(topic='critical_rule', version='all', force=True))
        assert '✅' in result, f"Should succeed with force=True: {result}"

        mcp.DB_PATH = original_db

        print("   ✅ Test 4.2: Deletes with force=True")
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
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_archive_created():
    """Test 5: Archive is created before delete"""
    print("\n🧪 Test 5: Archive created before delete")

    db_path = "test_unlock_5.db"
    try:
        create_test_database_with_versions(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Delete with archive (default)
        result = asyncio.run(mcp.unlock_context(topic='test_context', version='all'))

        assert '✅' in result, f"Should succeed: {result}"

        # Verify archive created
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT * FROM context_archives
            WHERE label = 'test_context'
        """)
        archive = cursor.fetchone()

        assert archive is not None, "Archive should be created"
        assert archive['content'] == 'Test data', "Archived content should match original"
        assert archive['version'] == '1.0', "Archived version should match"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 5: Archive created before deletion")
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
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_delete_nonexistent():
    """Test 6: Delete non-existent returns error"""
    print("\n🧪 Test 6: Delete non-existent context")

    db_path = "test_unlock_6.db"
    try:
        create_test_database_with_versions(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Try to delete non-existent
        result = asyncio.run(mcp.unlock_context(topic='nonexistent', version='all'))

        assert '❌' in result, f"Should return error: {result}"
        assert 'not found' in result.lower(), f"Should mention not found: {result}"

        mcp.DB_PATH = original_db

        print("   ✅ Test 6: Error returned for non-existent context")
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
        if os.path.exists(db_path):
            os.remove(db_path)


def run_all_tests():
    """Run all unlock_context() tests"""
    print("=" * 60)
    print("unlock_context() Test Suite (TDD - RED Phase)")
    print("=" * 60)

    tests = [
        ("Delete All Versions", test_delete_all_versions),
        ("Delete Specific Version", test_delete_specific_version),
        ("Delete Latest Version", test_delete_latest_version),
        ("Delete Critical Requires Force", test_delete_critical_requires_force),
        ("Archive Created", test_archive_created),
        ("Delete Non-existent", test_delete_nonexistent),
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
        print("Next: Implement unlock_context() to make tests pass (GREEN phase)")
    else:
        print("\n✅ All tests PASSED!")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
