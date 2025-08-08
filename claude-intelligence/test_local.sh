#!/bin/bash
# Local testing script for Claude Intelligence

echo "🧠 Testing Claude Intelligence Locally"
echo "======================================"
echo ""

# Test 1: Python imports
echo "Test 1: Checking Python imports..."
python3 -c "from mcp_server import ClaudeIntelligence; print('✓ Imports work')"

# Test 2: Initialization
echo ""
echo "Test 2: Testing initialization..."
python3 -c "
from mcp_server import ClaudeIntelligence
s = ClaudeIntelligence()
print('✓ Server initializes')
print(f'✓ Database: {s.db_path}')
"

# Test 3: Run tests
echo ""
echo "Test 3: Running test suite..."
python3 test_mcp_server.py 2>&1 | tail -3

# Test 4: Demo
echo ""
echo "Test 4: Running demo..."
python3 demo.py 2>&1 | grep "✅"

echo ""
echo "All local tests complete!"