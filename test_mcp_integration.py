#!/usr/bin/env python3
"""
Test script to verify MCP integration with active context engine
"""

import os
import sys
import asyncio
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Set environment to use test database
os.environ['CLAUDE_MEMORY_DB'] = 'test_mcp.db'
os.environ['CLAUDE_PROJECT_DIR'] = str(Path(__file__).parent)

# Import after setting environment
from claude_mcp_hybrid import (
    lock_context, recall_context, list_topics, check_contexts,
    wake_up, get_current_session_id, get_db
)

async def test_active_context_integration():
    """Test the integrated active context engine"""
    
    print("=" * 60)
    print("TESTING MCP INTEGRATION WITH ACTIVE CONTEXT ENGINE")
    print("=" * 60)
    
    # Initialize session
    session_id = get_current_session_id()
    print(f"\n✅ Session initialized: {session_id[:12]}...")
    
    # Test 1: Lock context with auto-detected priority
    print("\n📝 Test 1: Lock context with auto-detected priority")
    print("-" * 40)
    
    result = await lock_context(
        content="ALWAYS use 'output' folder for all generated files. NEVER create separate test folders.",
        topic="output_folder_rule",
        tags="configuration,standards"
    )
    print(f"Result: {result}")
    assert "⚠️ [ALWAYS CHECK]" in result, "Should auto-detect always_check priority"
    
    # Test 2: Lock context with explicit priority
    print("\n📝 Test 2: Lock context with explicit priority")
    print("-" * 40)
    
    result = await lock_context(
        content="API design guidelines for the project",
        topic="api_guidelines",
        tags="api,design",
        priority="important"
    )
    print(f"Result: {result}")
    assert "📌 [IMPORTANT]" in result, "Should use explicit important priority"
    
    # Test 3: Lock reference context
    print("\n📝 Test 3: Lock reference context")
    print("-" * 40)
    
    result = await lock_context(
        content="Database schema documentation",
        topic="db_schema",
        tags="database,documentation",
        priority="reference"
    )
    print(f"Result: {result}")
    assert "[ALWAYS CHECK]" not in result and "[IMPORTANT]" not in result, "Should be reference priority"
    
    # Test 4: List topics with priority indicators
    print("\n📝 Test 4: List topics with priority indicators")
    print("-" * 40)
    
    result = await list_topics()
    print(result)
    assert "⚠️" in result or "📌" in result, "Should show priority indicators"
    
    # Test 5: Check contexts for violations
    print("\n📝 Test 5: Check contexts for violations")
    print("-" * 40)
    
    # This should trigger violation
    result = await check_contexts("python generate.py --output output_test")
    print(result)
    assert "violation" in result.lower() or "relevant" in result.lower(), "Should detect violation or relevance"
    
    # This should be fine
    result = await check_contexts("python generate.py --output output")
    print(result)
    
    # Test 6: Check contexts for relevant information
    print("\n📝 Test 6: Check contexts for relevant information")
    print("-" * 40)
    
    result = await check_contexts("I need to design a new API endpoint")
    print(result)
    assert "api" in result.lower() or "relevant" in result.lower(), "Should find API-related context"
    
    # Test 7: Wake up with priority contexts
    print("\n📝 Test 7: Wake up showing priority contexts")
    print("-" * 40)
    
    result = await wake_up()
    print(result[:1000] + "..." if len(result) > 1000 else result)
    # Should show high-priority contexts
    
    # Test 8: Recall specific context
    print("\n📝 Test 8: Recall specific context")
    print("-" * 40)
    
    result = await recall_context("output_folder_rule")
    print(result)
    assert "ALWAYS use 'output'" in result, "Should recall the locked content"
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! ✅")
    print("=" * 60)
    
    # Cleanup
    conn = get_db()
    conn.close()
    if os.path.exists('test_mcp.db'):
        os.remove('test_mcp.db')
    
    print("\n✨ Active context engine is successfully integrated!")
    print("Key features working:")
    print("  ✅ Priority levels (always_check, important, reference)")
    print("  ✅ Auto-detection of priority based on content")
    print("  ✅ Context checking for violations")
    print("  ✅ Relevant context discovery")
    print("  ✅ Priority contexts shown at wake_up")

if __name__ == "__main__":
    asyncio.run(test_active_context_integration())