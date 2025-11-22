
import asyncio
import sys
import os
import json
import time
from datetime import datetime

# Add current directory to path
sys.path.append(os.getcwd())

# Import necessary modules
try:
    import claude_mcp_hybrid_sessions
    from tool_breadcrumbs import log_breadcrumb, BreadcrumbMarkers
    print("✅ Successfully imported MCP modules.")
except ImportError as e:
    print(f"❌ Failed to import MCP modules: {e}")
    sys.exit(1)

async def test_breadcrumbs():
    print("\n🧪 Testing Breadcrumb Tracking...")

    # 1. Initialize local session
    print("\n1️⃣  Initializing local session...")
    try:
        session_id = claude_mcp_hybrid_sessions._init_local_session()
        print(f"   Session ID: {session_id}")
    except Exception as e:
        print(f"❌ Failed to initialize session: {e}")
        return

    # 2. Select a project (required for tools to work)
    print("\n2️⃣  Selecting project...")
    try:
        # We can use the session store to update the project directly
        store = claude_mcp_hybrid_sessions._session_store
        if store:
            store.update_session_project(session_id, 'default')
            print("   ✅ Project set to 'default'")
        else:
            print("   ❌ Session store not available")
            return
    except Exception as e:
        print(f"❌ Failed to select project: {e}")
        return

    # 3. Generate some breadcrumbs
    print("\n3️⃣  Generating breadcrumbs...")
    try:
        # Manual log
        log_breadcrumb(BreadcrumbMarkers.ENTRY, "Test entry breadcrumb", tool="test_tool")
        log_breadcrumb("CUSTOM_MARKER", "Custom marker breadcrumb", tool="test_tool", extra_data="test_value")
        
        # Simulate tool execution via MCP (if possible, or just call function directly)
        # We'll just use the logging function directly for this test as we want to verify persistence
        log_breadcrumb(BreadcrumbMarkers.EXIT, "Test exit breadcrumb", tool="test_tool", status="success")
        
        print("   Breadcrumbs logged.")
    except Exception as e:
        print(f"❌ Failed to log breadcrumbs: {e}")
        return

    # 4. Retrieve breadcrumbs via store directly
    print("\n4️⃣  Verifying persistence via SessionStore...")
    try:
        # Access store from module to get updated reference
        store = claude_mcp_hybrid_sessions._session_store
        
        if store:
            breadcrumbs = store.get_breadcrumbs(session_id)
            print(f"   Found {len(breadcrumbs)} breadcrumbs in database.")
            
            if len(breadcrumbs) >= 3:
                print("   ✅ Persistence verified!")
                for b in breadcrumbs[:3]:
                    print(f"      - [{b['timestamp']}] {b['marker']}: {b['message']}")
            else:
                print("   ❌ Persistence failed or incomplete.")
                print(f"   Breadcrumbs: {breadcrumbs}")
        else:
            print("   ❌ Session store is None.")
            
    except Exception as e:
        print(f"❌ Failed to retrieve breadcrumbs from store: {e}")

    # 5. Retrieve breadcrumbs via MCP tool
    print("\n5️⃣  Verifying retrieval via MCP tool...")
    try:
        # Call the tool function directly
        from claude_mcp_hybrid_sessions import get_breadcrumbs
        
        result_json = await get_breadcrumbs(limit=5)
        result = json.loads(result_json)
        
        if result.get('breadcrumbs') and len(result['breadcrumbs']) > 0:
            print("   ✅ Tool execution verified!")
            print(f"   Tool returned {result['count']} breadcrumbs.")
        else:
            print("   ❌ Tool execution failed or returned no data.")
            print(f"   Result: {result}")

    except Exception as e:
        print(f"❌ Failed to call get_breadcrumbs tool: {e}")

if __name__ == "__main__":
    asyncio.run(test_breadcrumbs())
