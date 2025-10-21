#!/usr/bin/env python3
"""
Test suite for update_context() - UPDATE operation

TDD Approach: These tests will fail initially (RED),
then we implement update_context() to make them pass (GREEN).
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


def create_test_database(db_path: str):
    """Create test database with v4.1 schema and sample context"""
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
            access_count INTEGER DEFAULT 0,
            UNIQUE(session_id, label, version)
        )
    ''')

    # Insert initial context v1.0
    conn.execute("""
        INSERT INTO context_locks
        (session_id, label, version, content, content_hash, locked_at, metadata,
         preview, key_concepts, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('test_session', 'api_spec', '1.0',
          'API v1.0: Uses REST with basic auth',
          'hash_v1', time.time(),
          json.dumps({"tags": ["api"], "priority": "important"}),
          'API v1.0: Uses REST with basic auth',
          json.dumps(['API', 'REST', 'auth']),
          time.time()))

    conn.commit()
    conn.close()


def test_update_latest_version():
    """Test 1: Update latest version increments minor (v1.0 → v1.1)"""
    print("\n🧪 Test 1: Update latest version increments minor")

    db_path = "test_update_1.db"
    try:
        create_test_database(db_path)

        # Set up test environment
        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Update the context
        result = asyncio.run(mcp.update_context(
            topic='api_spec',
            content='API v2.0: Uses GraphQL with OAuth',
            version='latest'
        ))

        # Verify update succeeded
        assert '✅' in result, f"Should succeed: {result}"
        assert 'v1.1' in result, f"Should create v1.1: {result}"
        print(f"   ✅ Test 1.1: Update succeeded: {result}")

        # Verify both versions exist
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT version, content FROM context_locks
            WHERE label = 'api_spec' ORDER BY version
        """)
        versions = cursor.fetchall()

        assert len(versions) == 2, f"Should have 2 versions, got {len(versions)}"
        assert versions[0]['version'] == '1.0', "First version should be 1.0"
        assert versions[1]['version'] == '1.1', "Second version should be 1.1"
        assert 'v1.0' in versions[0]['content'], "v1.0 content should be preserved"
        assert 'v2.0' in versions[1]['content'], "v1.1 should have new content"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 1.2: Both versions exist in database")
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


def test_update_with_new_tags_priority():
    """Test 2: Update with new tags/priority works"""
    print("\n🧪 Test 2: Update with new tags and priority")

    db_path = "test_update_2.db"
    try:
        create_test_database(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Update with new tags and priority
        result = asyncio.run(mcp.update_context(
            topic='api_spec',
            content='API v2.0: MUST use OAuth. NEVER use basic auth.',
            tags='api,security,oauth',
            priority='always_check'
        ))

        assert '✅' in result, f"Should succeed: {result}"
        print(f"   ✅ Test 2.1: Update succeeded")

        # Verify metadata updated
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT metadata, content FROM context_locks
            WHERE label = 'api_spec' AND version = '1.1'
        """)
        row = cursor.fetchone()

        assert row is not None, "v1.1 should exist"

        metadata = json.loads(row['metadata'])
        assert 'oauth' in metadata['tags'], f"Should have new tags: {metadata['tags']}"
        assert metadata['priority'] == 'always_check', f"Should have new priority: {metadata['priority']}"
        assert 'MUST' in row['content'], "Should have new content"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 2.2: Metadata updated correctly")
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


def test_update_generates_preview():
    """Test 3: Update generates new preview and key_concepts"""
    print("\n🧪 Test 3: Update generates new preview and key_concepts")

    db_path = "test_update_3.db"
    try:
        create_test_database(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Update with different content
        result = asyncio.run(mcp.update_context(
            topic='api_spec',
            content='GraphQL API with subscription support. Real-time updates via WebSocket.',
            tags='api,graphql,websocket'
        ))

        assert '✅' in result, f"Should succeed: {result}"

        # Verify preview and key_concepts regenerated
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT preview, key_concepts FROM context_locks
            WHERE label = 'api_spec' AND version = '1.1'
        """)
        row = cursor.fetchone()

        assert row['preview'] is not None, "Should have preview"
        assert 'GraphQL' in row['preview'], f"Preview should mention GraphQL: {row['preview']}"

        key_concepts = json.loads(row['key_concepts'])
        assert 'GraphQL' in key_concepts or 'WebSocket' in key_concepts, \
            f"Key concepts should include new terms: {key_concepts}"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 3: Preview and key_concepts regenerated")
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


def test_update_nonexistent_topic():
    """Test 4: Update non-existent topic returns error"""
    print("\n🧪 Test 4: Update non-existent topic returns error")

    db_path = "test_update_4.db"
    try:
        create_test_database(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Try to update non-existent topic
        result = asyncio.run(mcp.update_context(
            topic='nonexistent',
            content='Some content'
        ))

        assert '❌' in result, f"Should return error: {result}"
        assert 'not found' in result.lower() or 'does not exist' in result.lower(), \
            f"Should mention not found: {result}"

        mcp.DB_PATH = original_db

        print("   ✅ Test 4: Error returned for non-existent topic")
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


def test_recall_old_and_new_versions():
    """Test 5: Can recall both old and new versions after update"""
    print("\n🧪 Test 5: Can recall both old and new versions")

    db_path = "test_update_5.db"
    try:
        create_test_database(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Update
        asyncio.run(mcp.update_context(
            topic='api_spec',
            content='Updated content v2.0'
        ))

        # Recall old version
        old_content = asyncio.run(mcp.recall_context('api_spec', version='1.0'))
        assert 'v1.0' in old_content, f"Should recall v1.0 content: {old_content}"

        # Recall new version
        new_content = asyncio.run(mcp.recall_context('api_spec', version='latest'))
        assert 'v2.0' in new_content, f"Should recall v1.1 content: {new_content}"

        mcp.DB_PATH = original_db

        print("   ✅ Test 5: Both versions can be recalled")
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


def test_update_metadata_tracking():
    """Test 6: Metadata tracks update reason and parent version"""
    print("\n🧪 Test 6: Metadata tracks update reason")

    db_path = "test_update_6.db"
    try:
        create_test_database(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Update with reason
        result = asyncio.run(mcp.update_context(
            topic='api_spec',
            content='Fixed typo in API spec',
            reason='Fixed typo'
        ))

        assert '✅' in result, f"Should succeed: {result}"

        # Check metadata
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT metadata FROM context_locks
            WHERE label = 'api_spec' AND version = '1.1'
        """)
        row = cursor.fetchone()

        metadata = json.loads(row['metadata'])
        assert 'updated_from' in metadata, f"Should track parent version: {metadata}"
        assert metadata['updated_from'] == '1.0', f"Should track from v1.0: {metadata}"

        conn.close()
        mcp.DB_PATH = original_db

        print("   ✅ Test 6: Metadata tracks parent version")
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
    """Run all update_context() tests"""
    print("=" * 60)
    print("update_context() Test Suite (TDD - RED Phase)")
    print("=" * 60)

    tests = [
        ("Update Latest Version", test_update_latest_version),
        ("Update Tags & Priority", test_update_with_new_tags_priority),
        ("Generate Preview", test_update_generates_preview),
        ("Non-existent Topic", test_update_nonexistent_topic),
        ("Recall Versions", test_recall_old_and_new_versions),
        ("Metadata Tracking", test_update_metadata_tracking),
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
        print("Next: Implement update_context() to make tests pass (GREEN phase)")
    else:
        print("\n✅ All tests PASSED!")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
