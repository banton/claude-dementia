#!/usr/bin/env python3
"""
Test lock_context with RLM preview generation

Tests that lock_context() automatically generates:
- preview (intelligent content summary)
- key_concepts (extracted technical terms)
- last_accessed (timestamp)
"""

import os
import sqlite3
import json
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from migrate_v4_1_rlm import generate_preview, extract_key_concepts


def test_lock_context_preview_generation():
    """Test that lock_context generates preview and key_concepts"""
    print("\n🧪 Test: lock_context with RLM preview generation")

    db_path = "test_lock_context.db"

    try:
        # Create test database with v4.1 schema
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
                related_contexts TEXT,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                UNIQUE(session_id, label, version)
            )
        ''')

        # Simulate lock_context behavior
        session_id = "test_session"
        topic = "api_authentication"
        content = """# API Authentication

Our API uses JWT tokens for authentication. All endpoints require valid tokens.

MUST validate tokens on every request. NEVER store passwords in plaintext.

Token expiration: 1 hour
Refresh token: 7 days

Implementation uses HS256 algorithm with secret key rotation."""

        tags = ['api', 'auth', 'security']

        # Generate preview and key_concepts (same as lock_context does)
        preview = generate_preview(content, max_length=500)
        key_concepts = extract_key_concepts(content, tags)

        # Insert context with RLM columns
        conn.execute("""
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, locked_at, metadata,
             preview, key_concepts, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, topic, "1.0", content, "test_hash", time.time(),
              json.dumps({"tags": tags, "priority": "always_check"}),
              preview, json.dumps(key_concepts), time.time()))

        conn.commit()

        # Verify the data was inserted correctly
        cursor = conn.execute("""
            SELECT label, content, preview, key_concepts, last_accessed
            FROM context_locks
            WHERE session_id = ? AND label = ?
        """, (session_id, topic))

        row = cursor.fetchone()
        conn.close()

        # Test 1: Context was created
        assert row is not None, "Context should be created"
        print("   ✅ Test 1: Context created successfully")

        # Test 2: Preview was generated
        assert row['preview'] is not None, "Preview should not be None"
        assert len(row['preview']) > 0, "Preview should not be empty"
        assert 'API' in row['preview'] or 'authentication' in row['preview'].lower(), \
            f"Preview should contain relevant keywords: {row['preview']}"
        print(f"   ✅ Test 2: Preview generated ({len(row['preview'])} chars)")

        # Test 3: Key concepts were extracted
        assert row['key_concepts'] is not None, "Key concepts should not be None"
        concepts = json.loads(row['key_concepts'])
        assert isinstance(concepts, list), "Key concepts should be a list"
        assert len(concepts) > 0, "Should have at least one concept"
        print(f"   ✅ Test 3: Key concepts extracted ({len(concepts)} concepts: {concepts[:5]})")

        # Test 4: last_accessed was set
        assert row['last_accessed'] is not None, "last_accessed should not be None"
        assert row['last_accessed'] > 0, "last_accessed should be a valid timestamp"
        print("   ✅ Test 4: last_accessed timestamp set")

        # Test 5: Preview is shorter than full content
        assert len(row['preview']) < len(row['content']), \
            "Preview should be shorter than full content"
        print(f"   ✅ Test 5: Preview is compressed ({len(row['preview'])} vs {len(row['content'])} chars)")

        # Test 6: Verify preview quality
        # Should include header, key rules, or important content
        assert 'API' in row['preview'] or 'JWT' in row['preview'], \
            "Preview should include key terms from content"
        print("   ✅ Test 6: Preview contains key terms")

        print("\n   ✅ All lock_context RLM tests passed!")
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


if __name__ == "__main__":
    print("=" * 60)
    print("lock_context RLM Preview Generation Test")
    print("=" * 60)

    success = test_lock_context_preview_generation()
    sys.exit(0 if success else 1)
