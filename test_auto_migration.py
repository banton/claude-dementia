#!/usr/bin/env python3
"""
Test automatic v4.1 migration when using Phase 5 tools
"""

import os
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_auto_migration():
    """Test that v4.0 databases auto-migrate to v4.1 on first tool use"""
    print("\n🧪 Test: Auto-migration from v4.0 to v4.1")

    db_path = "test_auto_migrate.db"

    try:
        # 1. Create a v4.0 database (without RLM columns)
        if os.path.exists(db_path):
            os.remove(db_path)

        conn = sqlite3.connect(db_path)

        # Create v4.0 schema (no preview, key_concepts, etc.)
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
                UNIQUE(session_id, label, version)
            )
        ''')

        # Insert a v4.0 context (no preview)
        conn.execute("""
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, locked_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('test_session', 'test_context', '1.0',
              'Test content for migration', 'hash123', 1234567890,
              '{"tags": ["test"], "priority": "reference"}'))

        conn.commit()
        conn.close()

        print("   ✅ Step 1: Created v4.0 database with 1 context (no RLM columns)")

        # 2. Import claude_mcp_hybrid which should auto-migrate
        import claude_mcp_hybrid as mcp

        # Override DB_PATH to use test database
        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path

        # Call get_db() which triggers initialize_database()
        conn = mcp.get_db()

        # 3. Check if migration added columns
        cursor = conn.execute("PRAGMA table_info(context_locks)")
        columns = [row[1] for row in cursor.fetchall()]

        assert 'preview' in columns, "Should have 'preview' column after migration"
        assert 'key_concepts' in columns, "Should have 'key_concepts' column"
        assert 'last_accessed' in columns, "Should have 'last_accessed' column"

        print("   ✅ Step 2: Auto-migration added RLM columns")

        # 4. Check if existing context got preview generated
        cursor = conn.execute("""
            SELECT preview, key_concepts FROM context_locks WHERE label = 'test_context'
        """)
        row = cursor.fetchone()

        assert row['preview'] is not None, "Should have generated preview for existing context"
        assert row['preview'] != '', "Preview should not be empty"
        assert row['key_concepts'] is not None, "Should have generated key_concepts"

        print(f"   ✅ Step 3: Generated preview for existing context: '{row['preview'][:50]}...'")

        conn.close()
        mcp.DB_PATH = original_db

        print("\n   ✅ Auto-migration test PASSED!")
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
    print("Auto-Migration Test")
    print("=" * 60)

    success = test_auto_migration()
    sys.exit(0 if success else 1)
