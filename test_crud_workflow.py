#!/usr/bin/env python3
"""
Integration test for complete CRUD workflow

Tests CREATE → READ → UPDATE → DELETE
"""

import os
import sqlite3
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import claude_mcp_hybrid as mcp


def test_complete_crud_workflow():
    """Test complete CRUD lifecycle"""
    print("\n🧪 Integration Test: Complete CRUD Workflow")

    db_path = "test_crud_integration.db"
    try:
        # Clean start
        if os.path.exists(db_path):
            os.remove(db_path)

        original_db = mcp.DB_PATH
        mcp.DB_PATH = db_path
        mcp.SESSION_ID = 'test_session'

        # Initialize database with proper schema
        conn = mcp.get_db()
        mcp.initialize_database(conn)
        conn.close()

        # 1. CREATE
        print("\n   📝 Step 1: CREATE - lock_context()")
        result = asyncio.run(mcp.lock_context(
            content="API v1.0: REST endpoints with basic auth",
            topic="api_spec",
            tags="api,rest",
            priority="important"
        ))
        assert '✅' in result, f"CREATE failed: {result}"
        assert 'v1.0' in result, f"Should create v1.0: {result}"
        print(f"      ✅ Created: {result}")

        # 2. READ
        print("\n   📖 Step 2: READ - recall_context(), get_context_preview(), explore_context_tree()")

        # 2a. Recall full content
        full_content = asyncio.run(mcp.recall_context("api_spec"))
        assert 'basic auth' in full_content, f"Should have full content: {full_content}"
        print("      ✅ recall_context() works")

        # 2b. Get preview
        preview_result = asyncio.run(mcp.get_context_preview("api_spec"))
        assert 'REST' in preview_result, f"Should show preview: {preview_result}"
        print("      ✅ get_context_preview() works")

        # 2c. Explore tree
        tree = asyncio.run(mcp.explore_context_tree())
        assert 'api_spec' in tree, f"Should list in tree: {tree}"
        print("      ✅ explore_context_tree() works")

        # 3. UPDATE
        print("\n   ✏️  Step 3: UPDATE - update_context()")
        update_result = asyncio.run(mcp.update_context(
            topic="api_spec",
            content="API v2.0: GraphQL with OAuth",
            reason="Migrated to GraphQL"
        ))
        assert '✅' in update_result, f"UPDATE failed: {update_result}"
        assert 'v1.1' in update_result, f"Should create v1.1: {update_result}"
        print(f"      ✅ Updated: {update_result}")

        # Verify both versions exist
        v1_content = asyncio.run(mcp.recall_context("api_spec", version="1.0"))
        v2_content = asyncio.run(mcp.recall_context("api_spec", version="1.1"))
        assert 'REST' in v1_content, "v1.0 should have old content"
        assert 'GraphQL' in v2_content, "v1.1 should have new content"
        print("      ✅ Version history preserved")

        # 4. DELETE
        print("\n   🗑️  Step 4: DELETE - unlock_context()")

        # 4a. Delete specific version
        delete_v1 = asyncio.run(mcp.unlock_context("api_spec", version="1.0"))
        assert '✅' in delete_v1, f"DELETE failed: {delete_v1}"
        print(f"      ✅ Deleted v1.0: {delete_v1}")

        # Verify v1.0 deleted but v1.1 remains
        v1_after = asyncio.run(mcp.recall_context("api_spec", version="1.0"))
        v2_after = asyncio.run(mcp.recall_context("api_spec", version="1.1"))
        assert '❌' in v1_after, "v1.0 should be deleted"
        assert 'GraphQL' in v2_after, "v1.1 should still exist"
        print("      ✅ Selective delete works")

        # 4b. Delete remaining
        delete_all = asyncio.run(mcp.unlock_context("api_spec", version="all"))
        assert '✅' in delete_all, f"DELETE all failed: {delete_all}"
        print(f"      ✅ Deleted remaining: {delete_all}")

        # Verify completely gone
        tree_after = asyncio.run(mcp.explore_context_tree())
        assert 'api_spec' not in tree_after or 'No locked contexts' in tree_after, \
            f"Should not find deleted context in tree: {tree_after}"
        print("      ✅ Removed from context tree")

        # Verify archive exists
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM context_archives WHERE label = 'api_spec'")
        archive_count = cursor.fetchone()[0]
        assert archive_count >= 2, f"Should have archived contexts, found {archive_count}"
        conn.close()
        print(f"      ✅ Archived {archive_count} versions")

        mcp.DB_PATH = original_db

        print("\n   ✅ Complete CRUD workflow PASSED!")
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
    print("CRUD Integration Test")
    print("=" * 60)

    success = test_complete_crud_workflow()

    print("\n" + "=" * 60)
    if success:
        print("✅ CRUD Integration Test PASSED")
        print("\nFull CRUD Operations Available:")
        print("  • CREATE: lock_context()")
        print("  • READ: ask_memory(), get_context_preview(), recall_context(), explore_context_tree()")
        print("  • UPDATE: update_context()")
        print("  • DELETE: unlock_context()")
    else:
        print("❌ CRUD Integration Test FAILED")
    print("=" * 60)

    sys.exit(0 if success else 1)
