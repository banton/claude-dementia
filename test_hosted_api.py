#!/usr/bin/env python3
"""
Local test script for hosted API server.

Run this BEFORE deploying to validate the server works locally.

Usage:
    # Terminal 1: Start server
    python3 server_hosted.py

    # Terminal 2: Run tests
    python3 test_hosted_api.py
"""

import requests
import os
import json

BASE_URL = "http://localhost:8080"
API_KEY = os.getenv('DEMENTIA_API_KEY', 'test-key-123')

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def test_health():
    """Test health endpoint (no auth required)."""
    print("\n1. Testing /health...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("   ✅ Health check passed")

def test_auth_missing():
    """Test authentication rejection."""
    print("\n2. Testing auth rejection...")
    response = requests.get(f"{BASE_URL}/tools")
    print(f"   Status: {response.status_code}")
    assert response.status_code == 401
    print("   ✅ Auth correctly rejected")

def test_auth_invalid():
    """Test invalid API key rejection."""
    print("\n3. Testing invalid API key...")
    response = requests.get(
        f"{BASE_URL}/tools",
        headers={"Authorization": "Bearer wrong-key"}
    )
    print(f"   Status: {response.status_code}")
    assert response.status_code == 401
    print("   ✅ Invalid key correctly rejected")

def test_list_tools():
    """Test tool listing."""
    print("\n4. Testing /tools...")
    response = requests.get(f"{BASE_URL}/tools", headers=headers)
    print(f"   Status: {response.status_code}")
    data = response.json()
    print(f"   Found {data['count']} tools")
    print(f"   Sample tools: {[t['name'] for t in data['tools'][:3]]}")
    assert response.status_code == 200
    assert data['count'] > 0
    print("   ✅ Tool listing passed")

def test_execute_wake_up():
    """Test executing wake_up tool."""
    print("\n5. Testing /execute with wake_up...")
    response = requests.post(
        f"{BASE_URL}/execute",
        headers=headers,
        json={
            "tool": "wake_up",
            "arguments": {}
        }
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Success: {data['success']}")
        print(f"   Result keys: {list(data['result'].keys()) if isinstance(data['result'], dict) else 'string'}")
        print("   ✅ wake_up executed successfully")
    else:
        print(f"   ❌ Error: {response.text}")

def test_execute_invalid_tool():
    """Test executing non-existent tool."""
    print("\n6. Testing invalid tool...")
    response = requests.post(
        f"{BASE_URL}/execute",
        headers=headers,
        json={
            "tool": "nonexistent_tool",
            "arguments": {}
        }
    )
    print(f"   Status: {response.status_code}")
    # Accept either 404 or 500 (FastMCP raises ToolError which becomes 500)
    assert response.status_code in [404, 500]
    print("   ✅ Invalid tool correctly rejected")

def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Dementia MCP Hosted API")
    print("=" * 60)

    try:
        test_health()
        test_auth_missing()
        test_auth_invalid()
        test_list_tools()
        test_execute_wake_up()
        test_execute_invalid_tool()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nServer is ready for deployment!")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except requests.exceptions.ConnectionError:
        print("\n❌ Cannot connect to server. Is it running?")
        print("   Start it with: python3 server_hosted.py")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
