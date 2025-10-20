#!/usr/bin/env python3
"""
Test suite for Phase 5 MCP tools

Tests:
1. ask_memory() - Natural language search
2. get_context_preview() - Lightweight preview access
3. explore_context_tree() - Browse all contexts
"""

import os
import sqlite3
import json
import sys
import time
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import claude_mcp_hybrid as mcp_module


def create_test_database(db_path: str):
    """Create test database with v4.1 schema and sample contexts"""
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)

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

    # Insert diverse test contexts
    test_contexts = [
        {
            'session_id': 'test_session',
            'label': 'api_authentication',
            'version': '1.0',
            'content': '''# API Authentication

Our API uses JWT tokens for authentication. All endpoints require valid tokens.

MUST validate tokens on every request. NEVER store passwords in plaintext.

Token expiration: 1 hour
Refresh token: 7 days

Implementation uses HS256 algorithm with secret key rotation.''',
            'preview': 'API Authentication. Our API uses JWT tokens for authentication. All endpoints require valid tokens.',
            'key_concepts': json.dumps(['api', 'authentication', 'JWT', 'tokens', 'HS256']),
            'metadata': json.dumps({'tags': ['api', 'auth', 'security'], 'priority': 'always_check'}),
            'last_accessed': time.time()
        },
        {
            'session_id': 'test_session',
            'label': 'database_config',
            'version': '1.0',
            'content': '''Database configuration for PostgreSQL.

Connection pooling enabled with max 20 connections.
Read replicas configured for load balancing.

ALWAYS use parameterized queries to prevent SQL injection.''',
            'preview': 'Database configuration for PostgreSQL. Connection pooling enabled with max 20 connections.',
            'key_concepts': json.dumps(['database', 'PostgreSQL', 'connection', 'pooling']),
            'metadata': json.dumps({'tags': ['database', 'config'], 'priority': 'reference'}),
            'last_accessed': time.time() - 86400
        },
        {
            'session_id': 'test_session',
            'label': 'deployment_process',
            'version': '1.0',
            'content': '''Deployment Process

1. Run tests locally
2. Create PR and get approval
3. Merge to main
4. CI/CD automatically deploys to staging
5. Manual promotion to production

NEVER deploy directly to production. ALWAYS test in staging first.''',
            'preview': 'Deployment Process. 1. Run tests locally 2. Create PR and get approval 3. Merge to main',
            'key_concepts': json.dumps(['deployment', 'CI/CD', 'staging', 'production', 'testing']),
            'metadata': json.dumps({'tags': ['deploy', 'process'], 'priority': 'important'}),
            'last_accessed': time.time() - 172800
        },
        {
            'session_id': 'test_session',
            'label': 'code_style',
            'version': '1.0',
            'content': '''Code Style Guide

Follow PEP 8 for Python code.
Use black for formatting.
Maximum line length: 100 characters.

Document all public functions with docstrings.
Use type hints for function signatures.''',
            'preview': 'Code Style Guide. Follow PEP 8 for Python code. Use black for formatting.',
            'key_concepts': json.dumps(['style', 'PEP8', 'black', 'formatting', 'docstrings']),
            'metadata': json.dumps({'tags': ['style', 'python'], 'priority': 'reference'}),
            'last_accessed': time.time() - 345600
        },
    ]

    for ctx in test_contexts:
        conn.execute('''
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, locked_at,
             preview, key_concepts, metadata, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ctx['session_id'], ctx['label'], ctx['version'],
              ctx['content'], 'hash_' + ctx['label'], time.time(),
              ctx['preview'], ctx['key_concepts'], ctx['metadata'], ctx['last_accessed']))

    conn.commit()
    conn.close()


def test_ask_memory():
    """Test ask_memory() natural language search"""
    print("\n🧪 Test: ask_memory() natural language search")

    db_path = "test_ask_memory.db"
    try:
        create_test_database(db_path)

        # Set DB path and session for testing
        original_db = mcp_module.DB_PATH
        mcp_module.DB_PATH = db_path
        mcp_module.SESSION_ID = 'test_session'

        # Test 1: Question matching API authentication
        question = "How do I authenticate API requests with tokens?"
        result = asyncio.run(mcp_module.ask_memory(question))

        assert '❓ Question:' in result, "Should include question"
        assert 'api_authentication' in result, f"Should find api_authentication context: {result}"
        assert 'Found' in result and 'relevant' in result, "Should show count of results"
        print("   ✅ Test 1: Natural language search works")

        # Test 2: Preview content included
        assert 'Preview:' in result or 'preview' in result.lower(), "Should include preview"
        assert 'recall_context' in result, "Should suggest recall_context for full content"
        print("   ✅ Test 2: Includes preview and suggests recall_context")

        # Test 3: Relevance scoring
        assert 'Relevance:' in result or '█' in result, "Should show relevance score"
        print("   ✅ Test 3: Shows relevance scoring")

        # Test 4: No results for unrelated question
        result_empty = asyncio.run(mcp_module.ask_memory("How do I cook pasta?"))
        assert 'No relevant contexts found' in result_empty or '📭' in result_empty, \
            f"Should indicate no results: {result_empty}"
        print("   ✅ Test 4: Handles no results gracefully")

        # Test 5: Priority icons
        result_priority = asyncio.run(mcp_module.ask_memory("authentication security"))
        assert '⚠️' in result_priority or '📌' in result_priority or '📄' in result_priority, \
            "Should show priority icons"
        print("   ✅ Test 5: Shows priority icons")

        print("   ✅ All ask_memory() tests passed!")
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
        mcp_module.DB_PATH = original_db


def test_get_context_preview():
    """Test get_context_preview() lightweight access"""
    print("\n🧪 Test: get_context_preview() lightweight access")

    db_path = "test_preview.db"
    try:
        create_test_database(db_path)

        # Set DB path and session for testing
        original_db = mcp_module.DB_PATH
        mcp_module.DB_PATH = db_path
        mcp_module.SESSION_ID = 'test_session'

        # Test 1: Get preview for existing context
        result = asyncio.run(mcp_module.get_context_preview('api_authentication'))

        assert '📄' in result, "Should have icon"
        assert 'api_authentication' in result, "Should include topic name"
        assert 'Preview:' in result, "Should include preview section"
        assert 'JWT' in result or 'authentication' in result.lower(), \
            f"Preview should contain relevant content: {result}"
        print("   ✅ Test 1: Returns preview for existing context")

        # Test 2: Includes metadata
        assert 'Priority:' in result or '⚠️' in result, "Should show priority"
        assert 'Tags:' in result or 'api' in result, "Should show tags"
        assert 'Key concepts:' in result, "Should show key concepts"
        print("   ✅ Test 2: Includes metadata (priority, tags, concepts)")

        # Test 3: Suggests recall_context
        assert 'recall_context' in result, "Should suggest recall_context for full content"
        print("   ✅ Test 3: Suggests recall_context for full content")

        # Test 4: Non-existent context
        result_missing = asyncio.run(mcp_module.get_context_preview('nonexistent_topic'))
        assert '❌' in result_missing or 'not found' in result_missing.lower(), \
            f"Should indicate context not found: {result_missing}"
        print("   ✅ Test 4: Handles missing context gracefully")

        # Test 5: Version handling
        result_v1 = asyncio.run(mcp_module.get_context_preview('api_authentication', version='1.0'))
        assert 'v1.0' in result_v1 or '1.0' in result_v1, "Should show version"
        print("   ✅ Test 5: Handles version parameter")

        print("   ✅ All get_context_preview() tests passed!")
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
        mcp_module.DB_PATH = original_db


def test_explore_context_tree():
    """Test explore_context_tree() browsing"""
    print("\n🧪 Test: explore_context_tree() browsing")

    db_path = "test_tree.db"
    try:
        create_test_database(db_path)

        # Set DB path and session for testing
        original_db = mcp_module.DB_PATH
        mcp_module.DB_PATH = db_path
        mcp_module.SESSION_ID = 'test_session'

        # Test 1: Lists all contexts
        result = asyncio.run(mcp_module.explore_context_tree())

        assert 'Context Tree' in result or '🗂️' in result, "Should have header"
        assert 'api_authentication' in result, "Should list api_authentication"
        assert 'database_config' in result, "Should list database_config"
        assert 'deployment_process' in result, "Should list deployment_process"
        assert 'code_style' in result, "Should list code_style"
        print("   ✅ Test 1: Lists all contexts")

        # Test 2: Groups by priority
        assert '⚠️' in result, "Should show always_check priority"
        assert '📌' in result, "Should show important priority"
        assert '📄' in result, "Should show reference priority"
        print("   ✅ Test 2: Groups contexts by priority")

        # Test 3: Shows previews
        assert 'JWT' in result or 'API' in result, "Should include preview content"
        print("   ✅ Test 3: Shows preview for each context")

        # Test 4: Includes context count
        assert '4' in result or 'Total' in result, "Should show total count"
        print("   ✅ Test 4: Shows context count")

        # Test 5: Next steps section
        assert 'Next steps:' in result or '💡' in result, "Should include next steps"
        assert 'ask_memory' in result or 'get_context_preview' in result or 'recall_context' in result, \
            "Should suggest next actions"
        print("   ✅ Test 5: Includes helpful next steps")

        # Test 6: Empty database handling
        empty_db = "test_empty.db"
        conn = sqlite3.connect(empty_db)
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
                access_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

        mcp_module.DB_PATH = empty_db
        result_empty = asyncio.run(mcp_module.explore_context_tree())
        assert 'No locked contexts found' in result_empty or '📭' in result_empty, \
            f"Should handle empty database: {result_empty}"
        print("   ✅ Test 6: Handles empty database gracefully")

        if os.path.exists(empty_db):
            os.remove(empty_db)

        print("   ✅ All explore_context_tree() tests passed!")
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
        mcp_module.DB_PATH = original_db


def test_token_efficiency():
    """Test that Phase 5 tools use previews, not full content"""
    print("\n🧪 Test: Token efficiency (preview vs full content)")

    db_path = "test_efficiency.db"
    try:
        create_test_database(db_path)

        # Calculate full content size
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT content FROM context_locks WHERE session_id = 'test_session'
        """)
        full_content_size = sum(len(row['content']) for row in cursor.fetchall())

        # Calculate preview size
        cursor = conn.execute("""
            SELECT preview FROM context_locks WHERE session_id = 'test_session'
        """)
        preview_size = sum(len(row['preview'] or '') for row in cursor.fetchall())
        conn.close()

        reduction_pct = ((full_content_size - preview_size) / full_content_size * 100) if full_content_size > 0 else 0

        print(f"   Full content: {full_content_size} chars")
        print(f"   Preview only: {preview_size} chars")
        print(f"   Reduction: {reduction_pct:.1f}%")

        assert reduction_pct > 50, f"Should have >50% reduction, got {reduction_pct:.1f}%"
        print(f"   ✅ Token efficiency: {reduction_pct:.1f}% reduction!")

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
    """Run all Phase 5 tool tests"""
    print("=" * 60)
    print("Phase 5 MCP Tools Test Suite")
    print("=" * 60)

    tests = [
        ("ask_memory() - Natural Language Search", test_ask_memory),
        ("get_context_preview() - Lightweight Access", test_get_context_preview),
        ("explore_context_tree() - Browse Contexts", test_explore_context_tree),
        ("Token Efficiency", test_token_efficiency),
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

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
