"""
Test basic PostgreSQL operations with multi-tenant isolation.

Demonstrates:
1. Creating sessions in different schemas
2. Creating context locks in different schemas
3. Querying data within schema boundaries
4. Verifying complete isolation between schemas
"""

import os
import time
import json
from postgres_adapter import PostgreSQLAdapter


def test_schema_isolation():
    """Test that different schemas are completely isolated."""

    print("=" * 60)
    print("Testing Multi-Tenant Schema Isolation")
    print("=" * 60)

    # Schema 1: User ABC's Innkeeper Project
    print("\n📁 Schema 1: User ABC - Innkeeper Project")
    os.environ['DEMENTIA_USER_ID'] = 'abc123'
    os.environ['DEMENTIA_PROJECT_NAME'] = 'innkeeper'
    adapter1 = PostgreSQLAdapter()
    adapter1.ensure_schema_exists()

    conn1 = adapter1.get_connection()
    try:
        with conn1.cursor() as cur:
            # Insert session
            cur.execute("""
                INSERT INTO sessions (id, started_at, last_active, project_name, project_path)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET last_active = EXCLUDED.last_active
            """, ('innk_test123', time.time(), time.time(), 'innkeeper', '/path/to/innkeeper'))

            # Insert context lock
            cur.execute("""
                INSERT INTO context_locks (session_id, label, version, content, tags, locked_at, last_accessed)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, ('innk_test123', 'screenplay_rules', 'v1.0', 'Keep dialogue natural', 'screenplay,rules', time.time(), time.time()))

            context_id = cur.fetchone()['id']
            conn1.commit()

            print(f"   ✅ Created session: innk_test123")
            print(f"   ✅ Created context: screenplay_rules (id: {context_id})")

            # Count records
            cur.execute("SELECT COUNT(*) as count FROM sessions")
            session_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM context_locks")
            context_count = cur.fetchone()['count']

            print(f"   📊 Schema has {session_count} sessions, {context_count} contexts")

    finally:
        adapter1.release_connection(conn1)

    # Schema 2: User ABC's LinkedIn Project
    print("\n📁 Schema 2: User ABC - LinkedIn Project")
    os.environ['DEMENTIA_USER_ID'] = 'abc123'
    os.environ['DEMENTIA_PROJECT_NAME'] = 'linkedin'
    adapter2 = PostgreSQLAdapter()
    adapter2.ensure_schema_exists()

    conn2 = adapter2.get_connection()
    try:
        with conn2.cursor() as cur:
            # Insert session
            cur.execute("""
                INSERT INTO sessions (id, started_at, last_active, project_name, project_path)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET last_active = EXCLUDED.last_active
            """, ('link_test456', time.time(), time.time(), 'linkedin', '/path/to/linkedin'))

            # Insert context lock
            cur.execute("""
                INSERT INTO context_locks (session_id, label, version, content, tags, locked_at, last_accessed)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, ('link_test456', 'content_strategy', 'v1.0', 'Post consistently', 'linkedin,strategy', time.time(), time.time()))

            context_id = cur.fetchone()['id']
            conn2.commit()

            print(f"   ✅ Created session: link_test456")
            print(f"   ✅ Created context: content_strategy (id: {context_id})")

            # Count records
            cur.execute("SELECT COUNT(*) as count FROM sessions")
            session_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM context_locks")
            context_count = cur.fetchone()['count']

            print(f"   📊 Schema has {session_count} sessions, {context_count} contexts")

    finally:
        adapter2.release_connection(conn2)

    # Verify isolation
    print("\n🔒 Verifying Isolation:")

    # Schema 1 should NOT see Schema 2's data
    conn1 = adapter1.get_connection()
    try:
        with conn1.cursor() as cur:
            cur.execute("SELECT label FROM context_locks")
            contexts = [row['label'] for row in cur.fetchall()]
            print(f"   Schema 1 contexts: {contexts}")
            assert 'screenplay_rules' in contexts, "Should see own context"
            assert 'content_strategy' not in contexts, "Should NOT see other schema's context"
            print(f"   ✅ Schema 1 isolation verified")
    finally:
        adapter1.release_connection(conn1)

    # Schema 2 should NOT see Schema 1's data
    conn2 = adapter2.get_connection()
    try:
        with conn2.cursor() as cur:
            cur.execute("SELECT label FROM context_locks")
            contexts = [row['label'] for row in cur.fetchall()]
            print(f"   Schema 2 contexts: {contexts}")
            assert 'content_strategy' in contexts, "Should see own context"
            assert 'screenplay_rules' not in contexts, "Should NOT see other schema's context"
            print(f"   ✅ Schema 2 isolation verified")
    finally:
        adapter2.release_connection(conn2)

    # Cleanup
    adapter1.close()
    adapter2.close()

    print("\n✅ All isolation tests passed!")
    print("=" * 60)


def test_query_operations():
    """Test standard query operations within a schema."""

    print("\n" + "=" * 60)
    print("Testing Query Operations")
    print("=" * 60)

    os.environ['DEMENTIA_USER_ID'] = 'test_user'
    os.environ['DEMENTIA_PROJECT_NAME'] = 'test_project'
    adapter = PostgreSQLAdapter()
    adapter.ensure_schema_exists()

    conn = adapter.get_connection()
    try:
        with conn.cursor() as cur:
            # Create session
            cur.execute("""
                INSERT INTO sessions (id, started_at, last_active, project_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET last_active = EXCLUDED.last_active
            """, ('test_session', time.time(), time.time(), 'test_project'))

            # Create multiple contexts
            contexts = [
                ('context_1', 'v1.0', 'Content 1', 'tag1,tag2'),
                ('context_2', 'v1.0', 'Content 2', 'tag2,tag3'),
                ('context_3', 'v2.0', 'Content 3', 'tag1,tag3'),
            ]

            for label, version, content, tags in contexts:
                cur.execute("""
                    INSERT INTO context_locks (session_id, label, version, content, tags, locked_at, last_accessed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, ('test_session', label, version, content, tags, time.time(), time.time()))

            conn.commit()
            print(f"   ✅ Created {len(contexts)} test contexts")

            # Query all contexts
            cur.execute("SELECT label, version FROM context_locks ORDER BY label")
            results = cur.fetchall()
            print(f"\n   📋 All contexts:")
            for row in results:
                print(f"      - {row['label']} ({row['version']})")

            # Query with filter
            cur.execute("SELECT label FROM context_locks WHERE tags LIKE %s", ('%tag1%',))
            filtered = [row['label'] for row in cur.fetchall()]
            print(f"\n   🔍 Contexts with 'tag1': {filtered}")

            # Update context
            cur.execute("""
                UPDATE context_locks
                SET access_count = access_count + 1, last_accessed = %s
                WHERE label = %s
                RETURNING access_count
            """, (time.time(), 'context_1'))
            new_count = cur.fetchone()['access_count']
            conn.commit()
            print(f"\n   ✏️  Updated context_1 access count: {new_count}")

            # Delete context
            cur.execute("DELETE FROM context_locks WHERE label = %s", ('context_3',))
            conn.commit()
            print(f"   🗑️  Deleted context_3")

            # Final count
            cur.execute("SELECT COUNT(*) as count FROM context_locks")
            final_count = cur.fetchone()['count']
            print(f"   📊 Final context count: {final_count}")

    finally:
        adapter.release_connection(conn)
        adapter.close()

    print("\n✅ All query operations passed!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_schema_isolation()
        test_query_operations()
        print("\n🎉 All PostgreSQL tests passed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
