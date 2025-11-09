# Local Testing Guide for Cloud MCP Solution

## Overview

This document provides a comprehensive guide for testing the cloud-hosted MCP solution locally. The goal is to validate that the session persistence, connection pool fixes, and enhanced cleanup features work as intended before deployment.

## Testing Environment Setup

### 1. Prerequisites
- Python 3.9+ installed
- Docker and Docker Compose installed
- Required dependencies from `requirements.txt`

### 2. Database Setup (Docker)
```bash
# Start PostgreSQL container with test database
docker run --name claude-test-db \
  -e POSTGRES_DB=claude_test_db \
  -e POSTGRES_USER=testuser \
  -e POSTGRES_PASSWORD=testpass \
  -p 5432:5432 \
  -d postgres:15

# Run schema initialization script
docker exec claude-test-db psql -U testuser -d claude_test_db -f /tmp/create_test_content_db.sql

# Copy schema file to container
cp create_test_content_db.sql /tmp/
docker cp /tmp/create_test_content_db.sql claude-test-db:/tmp/
```

### 3. Environment Configuration
Create a `.env` file with test-specific settings:
```bash
# Database connection (use Docker PostgreSQL)
DATABASE_URL=postgresql://testuser:testpass@localhost:5432/claude_test_db

# Enable enhanced session management features
MCP_AGGRESSIVE_CLEANUP=true
CLAUDE_MEMORY_DB=test_mcp.db

# Use test API key for authentication
DEMENTIA_API_KEY=test_api_key_12345

# Reduce pool size for testing (simulates production conditions)
POOL_MIN_CONNECTIONS=1
POOL_MAX_CONNECTIONS=5

# Enable detailed logging for debugging
LOG_LEVEL=DEBUG
```

### 4. Start Test Server
```bash
# Run the hosted server in test mode (uses same code as production)
python3 server_hosted.py
```

## Testing Scenarios

### 1. Session Persistence Test
**Objective**: Verify sessions survive server restarts.

```bash
# Step 1: Start server and create a session
curl -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"wake_up","arguments":{}}'

# Note the session_id from response (e.g., "session_id": "abc123def456")

# Step 2: Restart server
pkill -f "server_hosted.py"
python3 server_hosted.py

# Step 3: Use the same session_id to verify persistence
curl -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"recall_context","arguments":{"topic":"output_folder_rule"}}'
```

**Expected Result**: Session data is restored and context recall works.

### 2. Connection Pool Exhaustion Test
**Objective**: Verify connection pool fixes prevent exhaustion.

```bash
# Simulate high concurrency with multiple parallel requests
for i in {1..20}; do
  curl -X POST http://localhost:8080/execute \
    -H "Authorization: Bearer test_api_key_12345" \
    -H "Content-Type: application/json" \
    -d '{"tool":"wake_up","arguments":{}}' &
done
wait

# Check server logs for connection pool errors
grep -i "pool.*exhaust" server.log  # Should return nothing

# Check for timeout messages (expected under heavy load)
grep -i "Connection pool timeout" server.log  # May appear occasionally
```

**Expected Result**: No "connection pool exhausted" errors. Occasional timeouts are acceptable.

### 3. Enhanced Cleanup Test
**Objective**: Verify aggressive cleanup removes expired sessions promptly.

```bash
# Step 1: Create a session and note its ID
curl -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"wake_up","arguments":{}}'

# Step 2: Wait for session to expire (set a breakpoint or manually wait)
sleep 30

# Step 3: Check session health endpoint
curl -H "Authorization: Bearer test_api_key_12345" http://localhost:8080/session-health

# Step 4: Verify cleanup task runs (check logs)
grep -i "MCP session cleanup" server.log

# Step 5: Query database directly to verify expired sessions are removed
psql claude_test_db -c "SELECT count(*) FROM mcp_sessions WHERE expires_at < NOW();"
```

**Expected Result**: Expired sessions are cleaned up within 10 minutes.

### 4. Session Health Endpoint Test
**Objective**: Verify the new health endpoint provides accurate session statistics.

```bash
# Test with valid authentication
curl -H "Authorization: Bearer test_api_key_12345" http://localhost:8080/session-health

# Test with invalid authentication
curl -H "Authorization: Bearer wrong_key" http://localhost:8080/session-health

# Test with no authentication
curl http://localhost:8080/session-health
```

**Expected Result**: 
- Valid auth: Returns JSON with session statistics
- Invalid auth: Returns 401 Unauthorized
- No auth: Returns 401 Unauthorized

### 5. Tool Execution Test
**Objective**: Verify all tools work correctly with the new connection handling.

```bash
# Test multiple tools in sequence
curl -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"lock_context","arguments":{"content":"Test context","topic":"test_topic"}}'

curl -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"recall_context","arguments":{"topic":"test_topic"}}'

curl -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"list_topics","arguments":{}}'

curl -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"check_contexts","arguments":{"content":"Test query"}}'
```

**Expected Result**: All tools execute successfully with proper response formats.

## Automated Testing Script

Create a test script to automate these tests:

```bash
#!/bin/bash
# test_mcp_local.sh

echo "=== Testing Local MCP Solution ==="

# Start server in background
python3 server_hosted.py > server.log 2>&1 &
SERVER_PID=$!
echo "Server started with PID $SERVER_PID"

# Wait for server to be ready
sleep 3

# Test 1: Session persistence
echo "Testing session persistence..."
SESSION_ID=$(curl -s -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"wake_up","arguments":{}}' | jq -r '.result.session_id')

if [ "$SESSION_ID" = "null" ] || [ -z "$SESSION_ID" ]; then
    echo "❌ Session creation failed"
    exit 1
fi

echo "Session created: $SESSION_ID"

# Restart server
echo "Restarting server..."
kill -TERM $SERVER_PID
sleep 2

python3 server_hosted.py > server.log 2>&1 &
SERVER_PID=$!
sleep 3

# Verify session persistence
echo "Verifying session persistence..."
curl -s -X POST http://localhost:8080/execute \
  -H "Authorization: Bearer test_api_key_12345" \
  -H "Content-Type: application/json" \
  -d '{"tool":"recall_context","arguments":{"topic":"output_folder_rule"}}' | grep -q "ALWAYS use 'output'"
if [ $? -eq 0 ]; then
    echo "✅ Session persistence verified"
else
    echo "❌ Session persistence failed"
    exit 1
fi

# Test session health endpoint
echo "Testing session health endpoint..."
curl -H "Authorization: Bearer test_api_key_12345" http://localhost:8080/session-health | jq

# Test connection pool
echo "Testing connection pool under load..."
for i in {1..10}; do
    curl -s -X POST http://localhost:8080/execute \
      -H "Authorization: Bearer test_api_key_12345" \
      -H "Content-Type: application/json" \
      -d '{"tool":"wake_up","arguments":{}}' > /dev/null &
done
wait

# Check logs for errors
echo "Checking server logs for errors..."
grep -i "pool.*exhaust" server.log | grep -v "not found"
if [ $? -eq 0 ]; then
    echo "❌ Connection pool exhaustion detected!"
    exit 1
else
    echo "✅ No connection pool exhaustion"
fi

# Cleanup
echo "Cleaning up..."
kill -TERM $SERVER_PID
sleep 2

echo "=== ALL TESTS PASSED ==="
</file>
<task_progress>
- [x] Analyze current MCP session architecture
- [x] Identify testing requirements for cloud MCP solution
- [x] Design local testing environment setup
- [x] Propose test cases and validation methods
- [x] Document testing approach
</task_progress>
</write_to_file>
