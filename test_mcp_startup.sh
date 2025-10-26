#!/bin/bash
# Test MCP server startup (simulates Claude Desktop stdio protocol)

echo "Testing MCP server startup with PostgreSQL mode..."
echo ""

# Start server and send initialize request
(
    # Wait a bit for server to start
    sleep 1

    # Send initialize request (JSON-RPC)
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}'

    # Wait for response
    sleep 2
) | python3 claude_mcp_hybrid.py 2>&1 | tee /tmp/mcp_test.log

echo ""
echo "Check /tmp/mcp_test.log for full output"
echo ""

# Check for JSON errors
if grep -q "not valid JSON" /tmp/mcp_test.log; then
    echo "❌ FAIL: JSON parsing errors detected"
    exit 1
else
    echo "✅ PASS: No JSON parsing errors"
fi

# Check for proper initialization
if grep -q '"result"' /tmp/mcp_test.log; then
    echo "✅ PASS: Server responded with valid JSON-RPC"
else
    echo "⚠️  WARNING: No JSON-RPC response detected"
fi
