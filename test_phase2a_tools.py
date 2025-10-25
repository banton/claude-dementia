#!/usr/bin/env python3
"""
Test Phase 2A Tool Enhancements

Tests the 4 new tools and 1 enhanced tool:
1. batch_lock_contexts() - Multi-context locking
2. batch_recall_contexts() - Multi-context retrieval
3. search_contexts() - Full-text search
4. memory_analytics() - Usage insights
5. explore_context_tree(flat=True/False) - Enhanced with flat mode

Usage:
    python3 test_phase2a_tools.py
"""

import asyncio
import json
import sys

# Add parent directory to path to import MCP server
sys.path.insert(0, '/Users/banton/Sites/claude-dementia')

from claude_mcp_hybrid import (
    batch_lock_contexts,
    batch_recall_contexts,
    search_contexts,
    memory_analytics,
    explore_context_tree,
    unlock_context
)


async def test_batch_lock():
    """Test 1: batch_lock_contexts()"""
    print("\n" + "="*70)
    print("TEST 1: batch_lock_contexts()")
    print("="*70)

    test_contexts = [
        {
            "topic": "test_api_spec",
            "content": "API v2.0 specification with JWT authentication and rate limiting",
            "priority": "important",
            "tags": "api,authentication,security"
        },
        {
            "topic": "test_database_schema",
            "content": "PostgreSQL schema for users, posts, and comments tables",
            "priority": "always_check",
            "tags": "database,postgres,schema"
        },
        {
            "topic": "test_deployment_config",
            "content": "Docker compose setup with nginx, postgres, and redis services",
            "priority": "reference",
            "tags": "docker,deployment,infrastructure"
        }
    ]

    result = await batch_lock_contexts(json.dumps(test_contexts))
    result_json = json.loads(result)

    print(f"Result: {result_json['summary']}")

    if result_json['summary']['successful'] == 3 and result_json['summary']['failed'] == 0:
        print("✅ TEST 1 PASSED: All 3 contexts locked successfully")
        return True
    else:
        print("❌ TEST 1 FAILED: Some contexts failed to lock")
        print(json.dumps(result_json, indent=2))
        return False


async def test_batch_recall():
    """Test 2: batch_recall_contexts()"""
    print("\n" + "="*70)
    print("TEST 2: batch_recall_contexts()")
    print("="*70)

    topics = ["test_api_spec", "test_database_schema", "test_deployment_config"]

    result = await batch_recall_contexts(json.dumps(topics))
    result_json = json.loads(result)

    print(f"Result: {result_json['summary']}")

    # Verify we found all 3 contexts
    if result_json['summary']['found'] == 3:
        print("✅ TEST 2 PASSED: All 3 contexts recalled successfully")

        # Verify content is present
        for ctx in result_json['results']:
            if ctx['status'] == 'found':
                print(f"   - {ctx['topic']}: {len(ctx['content'])} characters")

        return True
    else:
        print("❌ TEST 2 FAILED: Not all contexts found")
        print(json.dumps(result_json, indent=2))
        return False


async def test_search():
    """Test 3: search_contexts()"""
    print("\n" + "="*70)
    print("TEST 3: search_contexts()")
    print("="*70)

    # Test 3a: Search by content
    print("\n3a. Searching for 'PostgreSQL'...")
    result = await search_contexts("PostgreSQL")
    result_json = json.loads(result)

    print(f"   Found {result_json['total_found']} contexts")

    if result_json['total_found'] >= 1:
        print("   ✅ Content search working")
        for ctx in result_json['results'][:2]:  # Show top 2
            print(f"      - {ctx['label']} (score: {ctx['score']})")
    else:
        print("   ❌ Content search failed")
        return False

    # Test 3b: Search by priority filter
    print("\n3b. Searching for 'test' with priority=important...")
    result = await search_contexts("test", priority="important")
    result_json = json.loads(result)

    print(f"   Found {result_json['total_found']} contexts")

    if result_json['total_found'] >= 1:
        print("   ✅ Priority filter working")
    else:
        print("   ❌ Priority filter failed")
        return False

    # Test 3c: Search by tags
    print("\n3c. Searching for 'database' with tags filter...")
    result = await search_contexts("database", tags="postgres")
    result_json = json.loads(result)

    print(f"   Found {result_json['total_found']} contexts")

    if result_json['total_found'] >= 1:
        print("   ✅ Tags filter working")
        print("✅ TEST 3 PASSED: All search modes working")
        return True
    else:
        print("   ❌ Tags filter failed")
        return False


async def test_analytics():
    """Test 4: memory_analytics()"""
    print("\n" + "="*70)
    print("TEST 4: memory_analytics()")
    print("="*70)

    result = await memory_analytics()
    result_json = json.loads(result)

    print(f"\nOverview:")
    print(f"   Total contexts: {result_json['overview']['total_contexts']}")
    print(f"   Total size: {result_json['overview']['total_size_mb']} MB")
    print(f"   Average size: {result_json['overview']['average_size_kb']} KB")

    print(f"\nBy priority:")
    for priority, stats in result_json['by_priority'].items():
        print(f"   {priority}: {stats['count']} contexts ({stats['size_mb']} MB)")

    print(f"\nMost accessed ({len(result_json['most_accessed'])} contexts):")
    for ctx in result_json['most_accessed'][:3]:  # Show top 3
        print(f"   - {ctx['label']} v{ctx['version']}: {ctx['access_count']} accesses")

    print(f"\nLeast accessed ({len(result_json['least_accessed'])} contexts):")
    for ctx in result_json['least_accessed'][:3]:  # Show top 3
        print(f"   - {ctx['label']} v{ctx['version']}: Never accessed")

    print(f"\nRecommendations:")
    for rec in result_json['recommendations']:
        print(f"   - {rec}")

    # Verify we have all expected sections
    required_sections = ['overview', 'most_accessed', 'least_accessed',
                         'largest_contexts', 'by_priority', 'recommendations']

    all_present = all(section in result_json for section in required_sections)

    if all_present and result_json['overview']['total_contexts'] >= 3:
        print("\n✅ TEST 4 PASSED: Analytics working correctly")
        return True
    else:
        print("\n❌ TEST 4 FAILED: Missing sections or no contexts")
        return False


async def test_explore_tree():
    """Test 5: explore_context_tree() with flat mode"""
    print("\n" + "="*70)
    print("TEST 5: explore_context_tree(flat=True/False)")
    print("="*70)

    # Test 5a: Flat mode
    print("\n5a. Testing flat mode (flat=True)...")
    result_flat = await explore_context_tree(flat=True)

    print("   Output:")
    for line in result_flat.split('\n')[:5]:  # Show first 5 lines
        print(f"      {line}")

    # Verify flat format (should be "label vX.Y" lines)
    lines = result_flat.strip().split('\n')
    flat_valid = all(' v' in line for line in lines if line.strip())

    if flat_valid and len(lines) >= 3:
        print("   ✅ Flat mode working")
    else:
        print("   ❌ Flat mode failed")
        return False

    # Test 5b: Tree mode (default)
    print("\n5b. Testing tree mode (flat=False, default)...")
    result_tree = await explore_context_tree(flat=False)

    print("   Output (first 10 lines):")
    for line in result_tree.split('\n')[:10]:
        print(f"      {line}")

    # Verify tree format (should have emojis and structure)
    tree_valid = '📚' in result_tree or 'Context Tree' in result_tree

    if tree_valid:
        print("   ✅ Tree mode working")
        print("\n✅ TEST 5 PASSED: Both flat and tree modes working")
        return True
    else:
        print("   ❌ Tree mode failed")
        return False


async def cleanup():
    """Cleanup: Remove test contexts"""
    print("\n" + "="*70)
    print("CLEANUP: Removing test contexts")
    print("="*70)

    test_topics = ["test_api_spec", "test_database_schema", "test_deployment_config"]

    for topic in test_topics:
        result = await unlock_context(topic)
        print(f"   - Unlocked {topic}")

    print("✅ Cleanup complete")


async def main():
    """Run all Phase 2A tests"""
    print("\n" + "="*70)
    print("PHASE 2A TOOL ENHANCEMENTS - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print("\nTesting 4 new tools + 1 enhanced tool:")
    print("1. batch_lock_contexts()")
    print("2. batch_recall_contexts()")
    print("3. search_contexts()")
    print("4. memory_analytics()")
    print("5. explore_context_tree(flat=True/False)")

    results = []

    try:
        # Run tests in sequence
        results.append(("batch_lock_contexts", await test_batch_lock()))
        results.append(("batch_recall_contexts", await test_batch_recall()))
        results.append(("search_contexts", await test_search()))
        results.append(("memory_analytics", await test_analytics()))
        results.append(("explore_context_tree", await test_explore_tree()))

        # Cleanup
        await cleanup()

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for name, result in results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"   {status}: {name}")

        print(f"\nTotal: {passed}/{total} tests passed")

        if passed == total:
            print("\n🎉 ALL TESTS PASSED! Phase 2A tools are working correctly.")
            return 0
        else:
            print(f"\n⚠️  {total - passed} test(s) failed. Please review output above.")
            return 1

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
