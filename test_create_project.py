#!/usr/bin/env python3
"""
Test script to reproduce create_project failure locally.
"""

import asyncio
import json
import sys

# Add current directory to path
sys.path.insert(0, '/Users/banton/Sites/claude-dementia')

async def test_create_project():
    """Test create_project tool directly."""
    from claude_mcp_hybrid_sessions import create_project

    print("🔍 Testing create_project...")
    print()

    # Test 1: Create new project
    print("Test 1: Create new project 'test_debug'")
    try:
        result = await create_project(name="test_debug")
        result_json = json.loads(result)
        print(f"✅ Result: {json.dumps(result_json, indent=2)}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("-" * 80)
    print()

    # Test 2: Try to create same project again (should fail gracefully)
    print("Test 2: Create same project again (should report exists)")
    try:
        result = await create_project(name="test_debug")
        result_json = json.loads(result)
        print(f"✅ Result: {json.dumps(result_json, indent=2)}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("-" * 80)
    print()

    # Test 3: Create project with special characters
    print("Test 3: Create project with special characters 'My-Project #2'")
    try:
        result = await create_project(name="My-Project #2")
        result_json = json.loads(result)
        print(f"✅ Result: {json.dumps(result_json, indent=2)}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_create_project())
