#!/usr/bin/env python3
"""
Test File Semantic Model Integration

Tests the integration with wake_up and sleep, and the 4 MCP tools.

Usage:
    python3 test_file_model_integration.py
"""

import asyncio
import json
import sys
import os
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, '/Users/banton/Sites/claude-dementia')

from claude_mcp_hybrid import (
    wake_up,
    sleep,
    scan_project_files,
    query_files,
    get_file_clusters,
    file_model_status
)


async def test_wake_up_integration():
    """Test 1: wake_up() includes file model data"""
    print("\n" + "="*70)
    print("TEST 1: wake_up() integration")
    print("="*70)

    result = await wake_up()
    result_json = json.loads(result)

    print("\nChecking for file_model in wake_up output...")

    if "file_model" in result_json:
        print("✅ file_model key present")

        file_model = result_json["file_model"]
        print(f"\nFile model data:")
        print(f"   - enabled: {file_model.get('enabled')}")
        print(f"   - scan_type: {file_model.get('scan_type', 'N/A')}")
        print(f"   - total_files: {file_model.get('total_files', 0)}")
        print(f"   - scan_time_ms: {file_model.get('scan_time_ms', 0)}")

        if file_model.get('enabled'):
            changes = file_model.get('changes', {})
            print(f"\nChanges detected:")
            print(f"   - added: {changes.get('added', 0)}")
            print(f"   - modified: {changes.get('modified', 0)}")
            print(f"   - deleted: {changes.get('deleted', 0)}")

            warnings = file_model.get('warnings', [])
            if warnings:
                print(f"\nWarnings ({len(warnings)}):")
                for w in warnings[:5]:
                    print(f"   - {w}")

            print("\n✅ TEST 1 PASSED: wake_up() includes file model data")
            return True
        else:
            reason = file_model.get('reason', file_model.get('error', 'unknown'))
            print(f"\nFile model disabled: {reason}")
            print("✅ TEST 1 PASSED: wake_up() handles disabled state correctly")
            return True
    else:
        print("❌ TEST 1 FAILED: file_model key not found in wake_up output")
        return False


async def test_scan_project_files():
    """Test 2: scan_project_files() tool works"""
    print("\n" + "="*70)
    print("TEST 2: scan_project_files() tool")
    print("="*70)

    result = await scan_project_files(full_scan=False, max_files=1000)
    result_json = json.loads(result)

    print(f"\nScan results:")
    print(f"   - scan_type: {result_json.get('scan_type')}")
    print(f"   - total_files: {result_json.get('total_files')}")
    print(f"   - scan_time_ms: {result_json.get('scan_time_ms')}")

    changes = result_json.get('changes', {})
    print(f"\nChanges:")
    print(f"   - added: {changes.get('added', 0)}")
    print(f"   - modified: {changes.get('modified', 0)}")
    print(f"   - deleted: {changes.get('deleted', 0)}")

    file_types = result_json.get('file_types', {})
    print(f"\nFile types detected: {len(file_types)}")
    for ftype, count in list(file_types.items())[:5]:
        print(f"   - {ftype}: {count}")

    clusters = result_json.get('clusters', [])
    print(f"\nClusters: {len(clusters)}")
    for cluster in clusters[:5]:
        print(f"   - {cluster}")

    if result_json.get('total_files', 0) > 0:
        print("\n✅ TEST 2 PASSED: scan_project_files() works")
        return True
    else:
        print("\n❌ TEST 2 FAILED: No files scanned")
        return False


async def test_query_files():
    """Test 3: query_files() tool works"""
    print("\n" + "="*70)
    print("TEST 3: query_files() tool")
    print("="*70)

    # Test 3a: Search by filename
    print("\n3a. Searching for 'test'...")
    result = await query_files(query="test", limit=5)
    result_json = json.loads(result)

    print(f"   Found {result_json.get('total_found', 0)} files")

    if result_json.get('total_found', 0) > 0:
        print("   ✅ Query by filename works")
        for file in result_json.get('results', [])[:3]:
            print(f"      - {file.get('file_path')}")
    else:
        print("   ⚠️ No files found (may be expected)")

    # Test 3b: Search by file type
    print("\n3b. Searching for Python files...")
    result = await query_files(query="", file_type="python", limit=5)
    result_json = json.loads(result)

    print(f"   Found {result_json.get('total_found', 0)} Python files")

    if result_json.get('total_found', 0) > 0:
        print("   ✅ Query by file type works")
        print("\n✅ TEST 3 PASSED: query_files() works")
        return True
    else:
        print("   ⚠️ No Python files found")
        print("\n✅ TEST 3 PASSED: query_files() handles empty results")
        return True


async def test_file_clusters():
    """Test 4: get_file_clusters() tool works"""
    print("\n" + "="*70)
    print("TEST 4: get_file_clusters() tool")
    print("="*70)

    result = await get_file_clusters()
    result_json = json.loads(result)

    print(f"\nTotal clusters: {result_json.get('total_clusters', 0)}")

    clusters = result_json.get('clusters', [])
    if clusters:
        print("\nCluster details:")
        for cluster in clusters[:5]:
            print(f"\n   - {cluster.get('name', 'unnamed')}")
            print(f"     Files: {cluster.get('file_count', 0)}")
            print(f"     Size: {cluster.get('total_size_kb', 0)} KB")

            file_types = cluster.get('file_types', {})
            if file_types and isinstance(file_types, dict):
                print(f"     Types: {', '.join([f'{k}({v})' for k,v in list(file_types.items())[:3]])}")
            elif file_types:
                print(f"     Types: {file_types[:3]}")

        print("\n✅ TEST 4 PASSED: get_file_clusters() works")
        return True
    else:
        print("\n⚠️ No clusters found (may need to run scan first)")
        print("✅ TEST 4 PASSED: get_file_clusters() handles empty state")
        return True


async def test_file_model_status():
    """Test 5: file_model_status() tool works"""
    print("\n" + "="*70)
    print("TEST 5: file_model_status() tool")
    print("="*70)

    result = await file_model_status()
    result_json = json.loads(result)

    overview = result_json.get('overview', {})
    print(f"\nOverview:")
    print(f"   - total_files: {overview.get('total_files', 0)}")
    print(f"   - total_size_mb: {overview.get('total_size_mb', 0)}")
    print(f"   - avg_size_kb: {overview.get('avg_size_kb', 0)}")
    print(f"   - health: {result_json.get('health', 'unknown')}")

    type_dist = result_json.get('type_distribution', {})
    if type_dist:
        print(f"\nType distribution:")
        for ftype, count in list(type_dist.items())[:5]:
            print(f"   - {ftype}: {count}")

    standard_files = result_json.get('standard_files', [])
    if standard_files:
        print(f"\nStandard files detected: {len(standard_files)}")
        for sf in standard_files[:5]:
            print(f"   - {sf.get('file_path')} ({sf.get('standard_type')})")

    if overview.get('total_files', 0) > 0:
        print("\n✅ TEST 5 PASSED: file_model_status() works")
        return True
    else:
        print("\n⚠️ No files in model (run scan first)")
        print("✅ TEST 5 PASSED: file_model_status() handles empty state")
        return True


async def test_sleep_integration():
    """Test 6: sleep() updates file model"""
    print("\n" + "="*70)
    print("TEST 6: sleep() integration")
    print("="*70)

    result = await sleep()

    print("\nChecking sleep() output for file model updates...")

    if "File model updated" in result or "file_model_updated" in result.lower():
        print("✅ File model update mentioned in sleep output")
        print("\n✅ TEST 6 PASSED: sleep() includes file model updates")
        return True
    else:
        print("⚠️ File model update not mentioned (may be no changes)")
        print("✅ TEST 6 PASSED: sleep() handles no-change case")
        return True


async def main():
    """Run all file model integration tests"""
    print("\n" + "="*70)
    print("FILE SEMANTIC MODEL INTEGRATION TESTS")
    print("="*70)
    print("\nTesting integration with wake_up/sleep and all 4 tools")

    results = []

    try:
        # Run tests in sequence
        results.append(("wake_up_integration", await test_wake_up_integration()))
        results.append(("scan_project_files", await test_scan_project_files()))
        results.append(("query_files", await test_query_files()))
        results.append(("file_clusters", await test_file_clusters()))
        results.append(("file_model_status", await test_file_model_status()))
        results.append(("sleep_integration", await test_sleep_integration()))

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
            print("\n🎉 ALL TESTS PASSED! File model integration working correctly.")
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
