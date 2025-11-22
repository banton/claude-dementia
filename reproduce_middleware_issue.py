
import asyncio
import json
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from unittest.mock import MagicMock

# Import the middleware to test
from mcp_session_middleware import MCPSessionPersistenceMiddleware

# Mock DB pool
class MockDBPool:
    def get_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock fetchone to return a valid session row
        mock_cursor.fetchone.return_value = {
            'session_id': 'test_session',
            'created_at': '2023-01-01T00:00:00',
            'last_active': '2023-01-01T00:00:00',
            'expires_at': '2099-01-01T00:00:00',
            'capabilities': '{}',
            'client_info': '{}',
            'project_name': 'default',
            'session_summary': '{}'
        }
        return mock_conn
    
    def release_connection(self, conn):
        pass

async def mock_endpoint(request):
    # Try to read the body via stream to simulate FastMCP behavior
    body_content = b""
    async for chunk in request.stream():
        body_content += chunk
    
    try:
        if not body_content:
            return JSONResponse({"status": "error", "detail": "Body stream was empty"}, status_code=400)
            
        body = json.loads(body_content)
        return JSONResponse({"status": "ok", "body": body})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

def test_middleware_body_consumption():
    # Setup mock DB pool
    db_pool = MockDBPool()
    
    # Setup app with middleware
    middleware = [
        Middleware(MCPSessionPersistenceMiddleware, db_pool=db_pool)
    ]
    
    app = Starlette(routes=[Route("/mcp", mock_endpoint, methods=["POST"])], middleware=middleware)
    
    client = TestClient(app)
    
    # Test payload
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 1
    }
    
    # Send request
    print("Sending request to /mcp...")
    response = client.post("/mcp", json=payload)
    
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")
    
    if response.status_code == 200 and response.json().get("body") == payload:
        print("SUCCESS: Body was correctly passed to endpoint.")
    else:
        print("FAILURE: Body was NOT correctly passed to endpoint or other error occurred.")

if __name__ == "__main__":
    test_middleware_body_consumption()
