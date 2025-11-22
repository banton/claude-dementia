import requests
import json
import os
import sys

# Configuration
BASE_URL = "http://localhost:8080"
API_KEY = os.getenv("DEMENTIA_API_KEY", "test-key")

def test_tools_endpoint():
    print("\n--- Testing /tools (GET) ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "TestClient/1.0"
    }
    try:
        response = requests.get(f"{BASE_URL}/tools", headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Tool Count: {data.get('count')}")
            print("Tools found: " + ", ".join([t['name'] for t in data.get('tools', [])][:5]) + "...")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

def test_mcp_initialize():
    print("\n--- Testing /mcp (initialize) ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "TestClient/1.0",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "TestClient", "version": "1.0"}
        }
    }
    try:
        response = requests.post(f"{BASE_URL}/mcp/", headers=headers, json=payload)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Initialize successful")
            # Get session ID
            session_id = response.headers.get("Mcp-Session-Id")
            print(f"Session ID: {session_id}")
            return session_id
        else:
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def test_mcp_tools_list(session_id):
    print("\n--- Testing /mcp (tools/list) ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "TestClient/1.0",
        "Content-Type": "application/json",
        "Mcp-Session-Id": session_id,
        "Accept": "application/json, text/event-stream"
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    try:
        response = requests.post(f"{BASE_URL}/mcp/", headers=headers, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        print(f"Response Text: {response.text[:500]}...")
        if response.status_code == 200:
            data = response.json()
            if 'result' in data:
                tools = data['result'].get('tools', [])
                print(f"Tool Count: {len(tools)}")
                print("Tools found: " + ", ".join([t['name'] for t in tools][:5]) + "...")
            else:
                print(f"Error in response: {data}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

def test_mcp_delete(session_id):
    print("\n--- Testing /mcp (DELETE) ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "TestClient/1.0",
        "Mcp-Session-Id": session_id
    }
    try:
        response = requests.delete(f"{BASE_URL}/mcp/", headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 202:
            print("DELETE successful (Graceful Shutdown)")
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    # Ensure server is running
    try:
        requests.get(f"{BASE_URL}/health")
    except:
        print("Server not running. Please run 'python3 server_hosted.py' in another terminal.")
        sys.exit(1)

    test_tools_endpoint()
    session_id = test_mcp_initialize()
    if session_id:
        test_mcp_tools_list(session_id)
        test_mcp_delete(session_id)
