"""
Verify Phase 2: Check if server_hosted.py imports correctly.
"""
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    print("Importing server_hosted...")
    import server_hosted
    print("Successfully imported server_hosted.")
    print(f"Middleware count: {len(server_hosted.app.user_middleware)}")
    
    # Check if MCPSessionPersistenceMiddleware is added
    from mcp_session_middleware import MCPSessionPersistenceMiddleware
    has_middleware = any(m.cls == MCPSessionPersistenceMiddleware for m in server_hosted.app.user_middleware)
    print(f"Has MCPSessionPersistenceMiddleware: {has_middleware}")
    
except Exception as e:
    print(f"Failed to import server_hosted: {e}")
    sys.exit(1)
