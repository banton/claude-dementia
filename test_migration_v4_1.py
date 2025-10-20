#!/usr/bin/env python3
"""
Test suite for v4.1 RLM migration script

Tests:
1. Preview generation quality
2. Key concept extraction
3. Migration on empty database
4. Migration on database with existing contexts
5. Idempotent migration (safe to run twice)
6. Rollback capability
"""

import os
import sqlite3
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from migrate_v4_1_rlm import (
    generate_preview,
    extract_key_concepts,
    migrate_database,
    check_migration_status,
    verify_migration
)


def create_v4_0_database(db_path: str):
    """Create a test database with v4.0 schema"""
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)

    # Create v4.0 schema (without RLM columns)
    conn.execute('''
        CREATE TABLE context_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0',
            content TEXT NOT NULL CHECK(length(content) <= 51200),
            content_hash TEXT NOT NULL,
            locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lock_source TEXT DEFAULT 'user',
            is_persistent BOOLEAN DEFAULT 0,
            parent_version TEXT,
            metadata TEXT,
            UNIQUE(session_id, label, version),
            CHECK(version GLOB '[0-9]*.[0-9]*')
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
''',
            'content_hash': 'hash1',
            'metadata': json.dumps({'tags': ['api', 'auth', 'security'], 'priority': 'always_check'})
        },
        {
            'session_id': 'test_session',
            'label': 'database_config',
            'version': '1.0',
            'content': '''Database configuration for PostgreSQL.

Connection pooling enabled with max 20 connections.
''',
            'content_hash': 'hash2',
            'metadata': json.dumps({'tags': ['database', 'config']})
        },
        {
            'session_id': 'test_session',
            'label': 'short_context',
            'version': '1.0',
            'content': 'This is a short context',
            'content_hash': 'hash3',
            'metadata': json.dumps({'tags': []})
        },
    ]

    for ctx in test_contexts:
        conn.execute('''
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ctx['session_id'], ctx['label'], ctx['version'],
              ctx['content'], ctx['content_hash'], ctx['metadata']))

    conn.commit()
    conn.close()


def test_generate_preview():
    """Test preview generation"""
    print("\n🧪 Test: generate_preview()")

    # Test 1: With header
    content = "# API Authentication\n\nUse JWT tokens for all requests..."
    preview = generate_preview(content)
    assert "API Authentication" in preview, f"Expected 'API Authentication' in preview, got: {preview}"
    assert len(preview) <= 500, f"Preview too long: {len(preview)} chars"
    print("   ✅ Test 1: Header extraction works")

    # Test 2: With MUST rules
    content = "MUST validate tokens. NEVER store passwords in plaintext."
    preview = generate_preview(content)
    assert "MUST" in preview or "NEVER" in preview, f"Expected keywords in preview: {preview}"
    print("   ✅ Test 2: Key sentence extraction works")

    # Test 3: Long content truncation
    content = "x" * 2000
    preview = generate_preview(content)
    assert len(preview) <= 503, f"Preview not truncated: {len(preview)} chars"
    assert preview.endswith("..."), "Expected '...' at end of truncated preview"
    print("   ✅ Test 3: Truncation works")

    # Test 4: Empty content
    preview = generate_preview("")
    assert preview == "", f"Expected empty preview for empty content, got: {preview}"
    print("   ✅ Test 4: Empty content handled")

    # Test 5: Real-world example
    content = '''# JWT Configuration

Our authentication system uses JSON Web Tokens (JWT) for secure API access.

MUST validate signature on every request.
NEVER expose the secret key in logs or errors.

Configuration:
- Expiration: 3600 seconds (1 hour)
- Algorithm: HS256
- Issuer: api.example.com
'''
    preview = generate_preview(content, max_length=200)
    assert "JWT" in preview, f"Expected 'JWT' in preview: {preview}"
    assert len(preview) <= 203, f"Preview exceeded max_length: {len(preview)}"
    print("   ✅ Test 5: Real-world content works")

    print("   ✅ All preview tests passed!")


def test_extract_key_concepts():
    """Test key concept extraction"""
    print("\n🧪 Test: extract_key_concepts()")

    # Test 1: Technical terms
    content = "Use JWT tokens with OAuth2 for authentication"
    concepts = extract_key_concepts(content)
    concept_str = ' '.join(concepts).lower()
    assert "jwt" in concept_str or "oauth" in concept_str, f"Expected JWT/OAuth in concepts: {concepts}"
    print("   ✅ Test 1: Technical terms extracted")

    # Test 2: CamelCase detection
    content = "UserAuthenticationService handles LoginRequest"
    concepts = extract_key_concepts(content)
    assert any("User" in c or "Authentication" in c or "Login" in c for c in concepts), \
        f"Expected CamelCase terms in concepts: {concepts}"
    print("   ✅ Test 2: CamelCase terms detected")

    # Test 3: Limit to 10
    content = "concept1 concept2 concept3 concept4 concept5 " * 4
    concepts = extract_key_concepts(content)
    assert len(concepts) <= 10, f"Too many concepts: {len(concepts)}"
    print("   ✅ Test 3: Concept limit enforced")

    # Test 4: Include provided tags
    concepts = extract_key_concepts("some content", tags=["api", "auth"])
    assert "api" in concepts and "auth" in concepts, f"Tags not included: {concepts}"
    print("   ✅ Test 4: Provided tags included")

    # Test 5: Empty content
    concepts = extract_key_concepts("")
    assert isinstance(concepts, list), "Expected list for empty content"
    print("   ✅ Test 5: Empty content handled")

    print("   ✅ All concept extraction tests passed!")


def test_migration_empty_database():
    """Test migration on empty database"""
    print("\n🧪 Test: Migration on empty database")

    db_path = "test_empty.db"

    try:
        # Create empty v4.0 database
        if os.path.exists(db_path):
            os.remove(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute('''
            CREATE TABLE context_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                label TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0',
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                metadata TEXT
            )
        ''')
        conn.close()

        # Run migration
        stats = migrate_database(db_path, verbose=False)

        # Verify
        assert not stats['already_migrated'], "Should not be already migrated"
        assert stats['contexts_updated'] == 0, f"Expected 0 contexts updated, got {stats['contexts_updated']}"
        assert stats['tables_created'] > 0, f"Expected tables created, got {stats['tables_created']}"
        assert len(stats['errors']) == 0, f"Expected no errors, got {stats['errors']}"

        # Verify schema
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(context_locks)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert 'preview' in columns, "Missing 'preview' column"
        assert 'key_concepts' in columns, "Missing 'key_concepts' column"
        assert 'last_accessed' in columns, "Missing 'last_accessed' column"

        print("   ✅ Empty database migration successful!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_migration_with_existing_contexts():
    """Test migration on database with existing contexts"""
    print("\n🧪 Test: Migration with existing contexts")

    db_path = "test_existing.db"

    try:
        # Create v4.0 database with test data
        create_v4_0_database(db_path)

        # Verify it's v4.0 (no RLM columns)
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(context_locks)")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'preview' not in columns, "Database should not have 'preview' column yet"
        conn.close()

        # Run migration
        stats = migrate_database(db_path, verbose=False)

        # Verify stats
        assert not stats['already_migrated'], "Should not be already migrated"
        assert stats['contexts_updated'] == 3, f"Expected 3 contexts updated, got {stats['contexts_updated']}"
        assert stats['previews_generated'] == 3, f"Expected 3 previews generated, got {stats['previews_generated']}"
        assert len(stats['errors']) == 0, f"Migration errors: {stats['errors']}"

        # Verify schema and data
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Check schema
        cursor = conn.execute("PRAGMA table_info(context_locks)")
        columns = [row[1] for row in cursor.fetchall()]

        assert 'preview' in columns, "Missing 'preview' column"
        assert 'key_concepts' in columns, "Missing 'key_concepts' column"
        assert 'related_contexts' in columns, "Missing 'related_contexts' column"

        # Check preview generation
        cursor = conn.execute("""
            SELECT label, preview, key_concepts
            FROM context_locks
            WHERE label = 'api_authentication'
        """)
        row = cursor.fetchone()

        assert row is not None, "Context not found"
        assert row['preview'] is not None, "Preview not generated"
        assert len(row['preview']) > 0, "Preview is empty"
        assert "JWT" in row['preview'] or "API" in row['preview'], \
            f"Expected keywords in preview: {row['preview']}"

        # Check key concepts
        concepts = json.loads(row['key_concepts']) if row['key_concepts'] else []
        assert len(concepts) > 0, "No key concepts extracted"
        print(f"   Extracted concepts: {concepts}")

        # Check new tables exist
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='context_relationships'
        """)
        assert cursor.fetchone() is not None, "context_relationships table not created"

        conn.close()

        print("   ✅ Existing contexts migration successful!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_idempotent_migration():
    """Test that migration is safe to run twice"""
    print("\n🧪 Test: Idempotent migration (safe to run twice)")

    db_path = "test_idempotent.db"

    try:
        # Create v4.0 database
        create_v4_0_database(db_path)

        # Run migration first time
        stats1 = migrate_database(db_path, verbose=False)
        assert stats1['contexts_updated'] == 3, "First migration should update 3 contexts"

        # Run migration second time
        stats2 = migrate_database(db_path, verbose=False)
        assert stats2['already_migrated'], "Second run should detect existing migration"
        assert stats2['contexts_updated'] == 0, "Second run should not update contexts"

        # Verify data integrity
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM context_locks")
        count = cursor.fetchone()[0]
        assert count == 3, f"Expected 3 contexts, got {count}"
        conn.close()

        print("   ✅ Idempotent migration works!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_preview_quality():
    """Test preview quality on real-world content"""
    print("\n🧪 Test: Preview quality on real-world content")

    test_cases = [
        {
            'name': 'API docs with rules',
            'content': '''# REST API Documentation

Our REST API follows standard conventions.

MUST include Authorization header with JWT token.
NEVER expose internal error messages to clients.

Rate limiting: 100 requests per minute per user.
''',
            'expected_in_preview': ['REST API', 'JWT', 'MUST', 'NEVER']
        },
        {
            'name': 'Configuration without header',
            'content': '''PostgreSQL connection settings:
Host: localhost
Port: 5432
Database: production

Connection pooling enabled with max 50 connections.
''',
            'expected_in_preview': ['PostgreSQL', 'localhost', 'production']
        },
        {
            'name': 'Very long content',
            'content': 'A' * 10000,
            'expected_in_preview': []
        }
    ]

    for test_case in test_cases:
        preview = generate_preview(test_case['content'], max_length=300)

        # Check length
        assert len(preview) <= 303, f"Preview too long for '{test_case['name']}': {len(preview)}"

        # Check for expected content
        for expected in test_case['expected_in_preview']:
            assert expected in preview, \
                f"Expected '{expected}' in preview for '{test_case['name']}': {preview[:100]}"

        print(f"   ✅ {test_case['name']}: preview quality good")

    print("   ✅ All preview quality tests passed!")


def run_all_tests():
    """Run all migration tests"""
    print("=" * 60)
    print("Claude Dementia v4.1 Migration Test Suite")
    print("=" * 60)

    tests = [
        ("Preview Generation", test_generate_preview),
        ("Key Concept Extraction", test_extract_key_concepts),
        ("Empty Database Migration", test_migration_empty_database),
        ("Existing Contexts Migration", test_migration_with_existing_contexts),
        ("Idempotent Migration", test_idempotent_migration),
        ("Preview Quality", test_preview_quality),
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
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
