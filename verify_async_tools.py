import inspect
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

try:
    import claude_mcp_async_sessions
    print("✅ Successfully imported claude_mcp_async_sessions")
except ImportError as e:
    print(f"❌ Failed to import claude_mcp_async_sessions: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error during import: {e}")
    sys.exit(1)

def verify_tools():
    print("\n🔍 Verifying tools...")
    
    # Get all functions decorated with @mcp.tool()
    # Since we can't easily access the registry without running the server,
    # we'll inspect the module functions and check if they are async.
    
    functions = inspect.getmembers(claude_mcp_async_sessions, inspect.isfunction)
    
    tools_to_check = [
        'recall_context',
        'search_contexts',
        'lock_context',
        'update_context',
        'unlock_context',
        'create_project',
        'select_project_for_session',
        'list_projects',
        'get_project_info',
        'delete_project',
        'check_contexts',
        'get_query_page',
        'get_last_handover',
        'wake_up',
        'sleep'
    ]
    
    all_passed = True
    
    for name, func in functions:
        if name in tools_to_check:
            is_async = inspect.iscoroutinefunction(func)
            status = "✅ ASYNC" if is_async else "❌ SYNC"
            print(f"{status} {name}")
            
            if not is_async:
                all_passed = False
                
    if all_passed:
        print("\n✨ All checked tools are async!")
    else:
        print("\n⚠️  Some tools are still synchronous!")

if __name__ == "__main__":
    verify_tools()
