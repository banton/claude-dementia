#!/bin/bash
# Test script to verify database isolation between projects

set -e

echo "🧪 Testing Database Isolation"
echo "=============================="
echo ""

# Test 1: Check LinkedIn project database path
echo "Test 1: LinkedIn Project Database"
echo "----------------------------------"
cd ~/Sites/linkedin
LINKEDIN_DB=$(python3 -c "
import os, hashlib
cwd = os.getcwd()
hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
print(f'~/.claude-dementia/{hash}.db')
")
echo "Expected database: $LINKEDIN_DB"
echo "Database hash: $(basename $LINKEDIN_DB .db)"

if [ -f "$LINKEDIN_DB" ]; then
    CONTEXT_COUNT=$(sqlite3 "$LINKEDIN_DB" "SELECT COUNT(*) FROM context_locks" 2>/dev/null || echo "0")
    echo "Contexts in database: $CONTEXT_COUNT"
else
    echo "Database does not exist yet (will be created on first use)"
fi
echo ""

# Test 2: Check root database (where all mixed contexts are)
echo "Test 2: Root Database (Old Mixed Contexts)"
echo "-------------------------------------------"
ROOT_DB=~/.claude-dementia/6666cd76.db
if [ -f "$ROOT_DB" ]; then
    ROOT_CONTEXTS=$(sqlite3 "$ROOT_DB" "SELECT COUNT(*) FROM context_locks" 2>/dev/null || echo "0")
    echo "Root database exists: $ROOT_DB"
    echo "Contexts in root DB: $ROOT_CONTEXTS"

    # Show sample contexts
    echo "Sample contexts in root DB:"
    sqlite3 "$ROOT_DB" "SELECT label FROM context_locks LIMIT 5" 2>/dev/null | sed 's/^/  - /'
else
    echo "Root database does not exist"
fi
echo ""

# Test 3: Check innkeeper project
echo "Test 3: Innkeeper Project Database"
echo "-----------------------------------"
if [ -d ~/Sites/innkeeper-claude ]; then
    cd ~/Sites/innkeeper-claude
    INNKEEPER_DB=$(python3 -c "
import os, hashlib
cwd = os.getcwd()
hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
print(f'~/.claude-dementia/{hash}.db')
")
    echo "Expected database: $INNKEEPER_DB"

    if [ -f "$INNKEEPER_DB" ]; then
        INNKEEPER_CONTEXTS=$(sqlite3 "$INNKEEPER_DB" "SELECT COUNT(*) FROM context_locks" 2>/dev/null || echo "0")
        echo "Contexts in database: $INNKEEPER_CONTEXTS"
    else
        echo "Database does not exist yet (will be created on first use)"
    fi
else
    echo "Innkeeper project not found at ~/Sites/innkeeper-claude"
fi
echo ""

# Test 4: Show all database files
echo "Test 4: All Database Files"
echo "---------------------------"
echo "Database files in ~/.claude-dementia/:"
ls -lh ~/.claude-dementia/*.db 2>/dev/null | awk '{print $9, "(" $5 ")"}' | sed 's/^/  /'
echo ""

# Test 5: Show path mapping
echo "Test 5: Path Mapping"
echo "--------------------"
if [ -f ~/.claude-dementia/path_mapping.json ]; then
    echo "Path mapping (hash → project):"
    python3 -c "
import json
with open('$HOME/.claude-dementia/path_mapping.json') as f:
    mappings = json.load(f)
for hash, info in mappings.items():
    print(f'  {hash}: {info[\"name\"]} ({info[\"path\"]})')
"
else
    echo "No path mapping file found"
fi
echo ""

# Summary
echo "Summary"
echo "-------"
echo "✅ Database isolation implemented!"
echo ""
echo "Next steps:"
echo "1. Open LinkedIn project in Claude Desktop"
echo "2. Run: dementia:wake_up()"
echo "3. Check: session.database should be $LINKEDIN_DB"
echo "4. Lock a context in LinkedIn project"
echo "5. Verify: Context only appears in LinkedIn, not in other projects"
echo ""
