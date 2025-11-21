
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from claude_mcp_hybrid_sessions import mcp
    print("Successfully imported mcp object.")
except ImportError as e:
    print(f"Failed to import mcp object: {e}")
    sys.exit(1)

async def list_tools():
    print("Listing tools...")
    try:
        tools = await mcp.list_tools()
        print(f"Found {len(tools)} tools.")
        for tool in tools:
            if tool.name == 'semantic_search_contexts':
                print(f"\n--- Tool: {tool.name} ---")
                print(f"Input Schema: {tool.inputSchema}")
    except Exception as e:
        print(f"Error listing tools: {e}")

if __name__ == "__main__":
    from schema_patcher import patch_mcp_tools
    print("Patching tools...")
    patch_mcp_tools(mcp)
    
    print("\nListing tools after patching...")
    asyncio.run(list_tools())
