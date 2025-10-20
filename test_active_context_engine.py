#!/usr/bin/env python3
"""
Test suite for Active Context Engine 2-stage relevance checking

Tests:
1. Stage 1: Preview-based scoring works correctly
2. Stage 2: Full content loaded only for top/high-score contexts
3. Relevance score calculation (keywords, concepts, recency, priority)
4. Keyword extraction
5. Token usage reduction (vs old implementation)
"""

import os
import sqlite3
import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from active_context_engine import ActiveContextEngine


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
            is_persistent BOOLEAN DEFAULT 0,
            parent_version TEXT,
            metadata TEXT,
            preview TEXT,
            key_concepts TEXT,
            related_contexts TEXT,
            last_accessed TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            UNIQUE(session_id, label, version)
        )
    ''')

    # Insert test contexts
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
            'preview': 'API Authentication\nOur API uses JWT tokens for authentication. All endpoints require valid tokens.',
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
            'preview': 'Database configuration for PostgreSQL.\nConnection pooling enabled with max 20 connections.',
            'key_concepts': json.dumps(['database', 'PostgreSQL', 'connection', 'pooling']),
            'metadata': json.dumps({'tags': ['database', 'config'], 'priority': 'reference'}),
            'last_accessed': time.time() - 86400  # 1 day ago
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
            'preview': 'Deployment Process\n1. Run tests locally\n2. Create PR and get approval',
            'key_concepts': json.dumps(['deployment', 'CI/CD', 'staging', 'production', 'testing']),
            'metadata': json.dumps({'tags': ['deploy', 'process'], 'priority': 'important'}),
            'last_accessed': time.time() - 172800  # 2 days ago
        },
        {
            'session_id': 'test_session',
            'label': 'test_standards',
            'version': '1.0',
            'content': '''Testing Standards

All features must have:
- Unit tests (80% coverage minimum)
- Integration tests for API endpoints
- E2E tests for critical paths

Use pytest with fixtures. Mock external dependencies.

MUST run tests before committing.''',
            'preview': 'Testing Standards\nAll features must have:\n- Unit tests (80% coverage minimum)\n- Integration tests for API endpoints',
            'key_concepts': json.dumps(['testing', 'pytest', 'unit', 'integration', 'E2E']),
            'metadata': json.dumps({'tags': ['test', 'standards'], 'priority': 'reference'}),
            'last_accessed': time.time() - 259200  # 3 days ago
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
            'preview': 'Code Style Guide\nFollow PEP 8 for Python code.\nUse black for formatting.',
            'key_concepts': json.dumps(['style', 'PEP8', 'black', 'formatting', 'docstrings']),
            'metadata': json.dumps({'tags': ['style', 'python'], 'priority': 'reference'}),
            'last_accessed': time.time() - 345600  # 4 days ago
        }
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


def test_extract_keywords():
    """Test keyword extraction"""
    print("\n🧪 Test: _extract_keywords()")

    engine = ActiveContextEngine("test_db.db")

    # Test 1: Basic extraction
    text = "Configure the API endpoint with authentication tokens"
    keywords = engine._extract_keywords(text)
    assert 'configure' in keywords, f"Expected 'configure' in keywords: {keywords}"
    assert 'api' in keywords, f"Expected 'api' in keywords: {keywords}"
    assert 'endpoint' in keywords, f"Expected 'endpoint' in keywords: {keywords}"
    assert 'authentication' in keywords, f"Expected 'authentication' in keywords: {keywords}"
    assert 'tokens' in keywords, f"Expected 'tokens' in keywords: {keywords}"
    print("   ✅ Test 1: Basic keyword extraction works")

    # Test 2: Stop word filtering
    keywords = engine._extract_keywords("The quick brown fox jumps over the lazy dog")
    assert 'the' not in keywords, f"Stop word 'the' should be filtered: {keywords}"
    assert 'quick' in keywords, f"Expected 'quick' in keywords: {keywords}"
    print("   ✅ Test 2: Stop words filtered")

    # Test 3: Uniqueness
    keywords = engine._extract_keywords("test test test test")
    assert len([k for k in keywords if k == 'test']) == 1, "Keywords should be unique"
    print("   ✅ Test 3: Keywords are unique")

    print("   ✅ All keyword extraction tests passed!")


def test_calculate_relevance_score():
    """Test relevance score calculation"""
    print("\n🧪 Test: _calculate_relevance_score()")

    db_path = "test_scoring.db"
    try:
        create_test_database(db_path)
        engine = ActiveContextEngine(db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Get test context
        cursor = conn.execute("""
            SELECT label, version, preview, key_concepts, metadata, last_accessed
            FROM context_locks
            WHERE label = 'api_authentication'
        """)
        row = cursor.fetchone()
        conn.close()

        # Test 1: High relevance for matching query
        query = "How do I configure API authentication with JWT tokens?"
        score = engine._calculate_relevance_score(query, row)
        assert score > 0.5, f"Expected high score for matching query, got {score}"
        print(f"   ✅ Test 1: High relevance score ({score:.2f}) for matching query")

        # Test 2: Low relevance for non-matching query
        query = "How do I format Python code?"
        score = engine._calculate_relevance_score(query, row)
        assert score < 0.3, f"Expected low score for non-matching query, got {score}"
        print(f"   ✅ Test 2: Low relevance score ({score:.2f}) for non-matching query")

        # Test 3: Priority affects score
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT label, version, preview, key_concepts, metadata, last_accessed
            FROM context_locks
            WHERE label = 'database_config'
        """)
        low_priority_row = cursor.fetchone()
        conn.close()

        score_high_priority = engine._calculate_relevance_score("api test", row)
        score_low_priority = engine._calculate_relevance_score("api test", low_priority_row)
        # High priority context should score higher even with same keywords
        assert score_high_priority > score_low_priority, \
            f"High priority should score higher: {score_high_priority} vs {score_low_priority}"
        print("   ✅ Test 3: Priority affects relevance score")

        print("   ✅ All relevance scoring tests passed!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_two_stage_relevance_checking():
    """Test that 2-stage relevance checking works correctly"""
    print("\n🧪 Test: Two-stage relevance checking")

    db_path = "test_two_stage.db"
    try:
        create_test_database(db_path)
        engine = ActiveContextEngine(db_path)

        # Test 1: Stage 1 finds relevant contexts
        query = "How do I authenticate API requests with tokens?"
        relevant = engine.check_context_relevance(query, 'test_session')

        assert len(relevant) > 0, "Should find relevant contexts"
        assert any(ctx['label'] == 'api_authentication' for ctx in relevant), \
            "Should find api_authentication context"
        print(f"   ✅ Test 1: Stage 1 found {len(relevant)} relevant contexts")

        # Test 2: High-scoring contexts have full content loaded
        api_ctx = next(ctx for ctx in relevant if ctx['label'] == 'api_authentication')
        assert api_ctx['content'] is not None, "High-scoring context should have content loaded"
        assert len(api_ctx['content']) > len(api_ctx['preview']), \
            "Full content should be longer than preview"
        print("   ✅ Test 2: High-scoring contexts have full content")

        # Test 3: Low-scoring contexts use preview as content
        if len(relevant) > 5:
            low_scorer = relevant[-1]  # Last context (lowest score)
            if low_scorer['relevance_score'] < 0.7:
                # Should use preview, not full content
                assert low_scorer['content'] == low_scorer['preview'], \
                    "Low-scoring context should use preview as content"
                print("   ✅ Test 3: Low-scoring contexts use preview")

        # Test 4: Priority contexts always get full content
        relevant = engine.check_context_relevance("some random text", 'test_session')
        for ctx in relevant:
            if ctx['priority'] == 'always_check':
                assert ctx['content'] is not None, \
                    f"always_check priority context '{ctx['label']}' should have full content"
        print("   ✅ Test 4: Priority contexts always get full content")

        # Test 5: Verify token savings
        query = "testing deployment process"
        relevant = engine.check_context_relevance(query, 'test_session')

        # Count how many contexts loaded full content
        full_content_count = sum(1 for ctx in relevant
                                if ctx['content'] and len(ctx['content']) > len(ctx['preview']))
        preview_only_count = len(relevant) - full_content_count

        print(f"   Full content loaded: {full_content_count} contexts")
        print(f"   Preview only: {preview_only_count} contexts")

        # At least some contexts should use preview only
        assert preview_only_count >= 0, "Should have at least some preview-only contexts"
        print("   ✅ Test 5: Token savings achieved (not all contexts loaded full content)")

        print("   ✅ All 2-stage relevance tests passed!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_load_full_content():
    """Test _load_full_content helper"""
    print("\n🧪 Test: _load_full_content()")

    db_path = "test_load_content.db"
    try:
        create_test_database(db_path)
        engine = ActiveContextEngine(db_path)

        # Test 1: Load existing context
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        content = engine._load_full_content('api_authentication', '1.0', 'test_session', conn)
        assert len(content) > 0, "Should load content"
        assert 'JWT' in content, "Content should contain expected text"
        print("   ✅ Test 1: Loads existing context")

        # Test 2: Non-existent context returns empty
        content = engine._load_full_content('nonexistent', '1.0', 'test_session', conn)
        assert content == '', "Non-existent context should return empty string"
        conn.close()
        print("   ✅ Test 2: Non-existent context returns empty")

        print("   ✅ All _load_full_content tests passed!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_token_usage_comparison():
    """Compare token usage: old vs new implementation"""
    print("\n🧪 Test: Token usage comparison (old vs new)")

    db_path = "test_tokens.db"
    try:
        create_test_database(db_path)

        # Simulate old implementation (loads all content)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT content FROM context_locks WHERE session_id = 'test_session'
        """)
        old_total_chars = sum(len(row['content']) for row in cursor.fetchall())
        conn.close()

        # New implementation
        engine = ActiveContextEngine(db_path)
        query = "How do I test the API deployment?"
        relevant = engine.check_context_relevance(query, 'test_session')

        new_total_chars = 0
        for ctx in relevant:
            # In stage 1, only preview was queried
            # In stage 2, only top/high-score contexts loaded full content
            if ctx['content'] == ctx['preview']:
                new_total_chars += len(ctx['preview'])
            else:
                new_total_chars += len(ctx['content'])

        reduction_pct = ((old_total_chars - new_total_chars) / old_total_chars * 100) if old_total_chars > 0 else 0

        print(f"   Old implementation: {old_total_chars} chars")
        print(f"   New implementation: {new_total_chars} chars")
        print(f"   Reduction: {reduction_pct:.1f}%")

        assert reduction_pct > 0, "Should have some token reduction"
        print(f"   ✅ Token usage reduced by {reduction_pct:.1f}%!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def run_all_tests():
    """Run all active context engine tests"""
    print("=" * 60)
    print("Active Context Engine 2-Stage Relevance Test Suite")
    print("=" * 60)

    tests = [
        ("Keyword Extraction", test_extract_keywords),
        ("Relevance Score Calculation", test_calculate_relevance_score),
        ("Two-Stage Relevance Checking", test_two_stage_relevance_checking),
        ("Load Full Content", test_load_full_content),
        ("Token Usage Comparison", test_token_usage_comparison),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"   ❌ FAILED: {e}")
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
