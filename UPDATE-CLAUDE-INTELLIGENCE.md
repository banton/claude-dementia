# Update Claude Intelligence Installation

Copy this prompt and paste it into Claude Code when you're in a project that already has Claude Intelligence installed:

---

Please update the Claude Intelligence installation in this project to include the new session memory features. Follow these steps:

1. First, check what's currently installed:
```bash
echo "Checking current installation..."
ls -la mcp_server.py claude_session_memory.py 2>/dev/null || echo "Files to check"
if [ -f ".claude-memory.db" ]; then
    echo "✓ Database exists"
    sqlite3 .claude-memory.db "SELECT name FROM sqlite_master WHERE type='table';" 2>/dev/null | head -5
fi
```

2. Update the existing files with the new memory system:
```bash
# Backup existing database (if any)
if [ -f ".claude-memory.db" ]; then
    cp .claude-memory.db .claude-memory.backup.db
    echo "✓ Database backed up to .claude-memory.backup.db"
fi

# Copy updated files
echo "Updating Claude Intelligence files..."
cp /Users/banton/Sites/claude-dementia/claude-intelligence/mcp_server.py ./
cp /Users/banton/Sites/claude-dementia/claude-intelligence/claude_session_memory.py ./
cp /Users/banton/Sites/claude-dementia/claude-intelligence/mcp_wrapper.py ./

echo "✅ Core files updated"
```

3. Test the new memory features:
```bash
python3 -c "
print('Testing new memory features...')
from claude_session_memory import ClaudeMemory, integrate_with_intelligence
from mcp_server import ClaudeIntelligence

# Test standalone memory
memory = ClaudeMemory()
memory.add_update('Testing memory system update')
todo_id = memory.add_todo('Verify new memory features work')
print('✓ Memory system works')

# Test integration
if integrate_with_intelligence():
    server = ClaudeIntelligence()
    server.add_update('Memory integration successful')
    print('✓ Integration with Claude Intelligence works')
    
    # Show what's in memory
    summary = server.get_session_summary()
    print(f\"\\n📊 Current Memory:\")
    print(f\"  Updates: {summary['stats']['updates']}\")
    print(f\"  TODOs: {summary['stats']['pending_todos']}\")
    print(f\"  Questions: {summary['stats']['open_questions']}\")
else:
    print('⚠️ Running memory standalone')
"
```

4. Update your CLAUDE.md file with new memory capabilities:
```bash
# Check if CLAUDE.md exists
if [ -f "CLAUDE.md" ]; then
    echo "Updating existing CLAUDE.md..."
    
    # Add memory section if not present
    if ! grep -q "Session Memory" CLAUDE.md; then
        cat >> CLAUDE.md << 'EOF'

## Session Memory Features (NEW)

Claude Intelligence now includes full session memory:

### Track Your Work
```python
# Import with memory features
from mcp_server import ClaudeIntelligence
from claude_session_memory import integrate_with_intelligence

integrate_with_intelligence()
server = ClaudeIntelligence()

# Log updates
server.add_update("Implemented new feature X")

# Track TODOs
server.add_todo("Review PR feedback", priority=1)
server.update_todo_status(todo_id, "in_progress")

# Document fixes
server.add_fix(
    problem="API timeout errors",
    cause="Connection pool exhaustion",
    solution="Increased pool size to 100",
    prevention="Added monitoring alert"
)

# Record decisions
server.add_question(
    "Should we migrate to PostgreSQL?",
    context="Current SQLite hitting performance limits",
    options=["Yes - migrate now", "No - optimize first", "Hybrid approach"]
)

# Get session summary
summary = server.get_session_summary()
print(f"Pending TODOs: {summary['stats']['pending_todos']}")
```

### Restore Previous Session
```python
# On session start
print(server.restore_session())
```
EOF
        echo "✅ Added memory documentation to CLAUDE.md"
    else
        echo "ℹ️ CLAUDE.md already has memory section"
    fi
else
    echo "⚠️ No CLAUDE.md found - you may want to create one"
fi
```

5. Quick demo of the new features:
```bash
python3 -c "
print('\\n🧠 Memory Features Demo')
print('=' * 50)

from mcp_server import ClaudeIntelligence
from claude_session_memory import integrate_with_intelligence
import asyncio

# Setup
integrate_with_intelligence()
server = ClaudeIntelligence()

# Simulate a work session
print('\\nSimulating work session...')
server.add_update('Updated authentication to use OAuth2')
server.add_update('Fixed CORS issues in API endpoints', category='fix')

server.add_todo('Add rate limiting to prevent abuse', priority=1)
server.add_todo('Update API documentation', priority=2)
server.add_todo('Write integration tests', priority=1)

server.add_fix(
    problem='Users unable to login with Google',
    cause='Incorrect redirect URI in OAuth config',
    solution='Updated redirect URI to match production domain',
    prevention='Added config validation in CI/CD'
)

server.add_question(
    'Should we implement WebSocket support for real-time features?',
    context='Users requesting live notifications',
    options=['Yes - Socket.io', 'Yes - native WebSockets', 'No - use polling', 'SSE instead']
)

# Show summary
summary = server.get_session_summary()
print(f\"\\n📊 Session Summary:\")
print(f\"  Total updates: {summary['stats']['updates']}\")
print(f\"  Pending TODOs: {summary['stats']['pending_todos']}\")
print(f\"  Documented fixes: {summary['stats']['documented_fixes']}\")
print(f\"  Open questions: {summary['stats']['open_questions']}\")

print(f\"\\nRecent Updates:\")
for update in summary['recent_updates'][:3]:
    print(f\"  - {update['message']}\")

print(f\"\\nActive TODOs:\")
for todo in summary['active_todos'][:3]:
    print(f\"  - {todo['content']} (P{todo['priority']})\")

if summary['open_questions']:
    print(f\"\\nOpen Questions:\")
    for q in summary['open_questions']:
        print(f\"  - {q['question']}\")

print('\\n✅ Memory system fully operational!')
"
```

6. Verify everything works:
```bash
echo ""
echo "=== Update Complete ==="
echo ""
echo "✅ Claude Intelligence updated with memory features!"
echo ""
echo "New capabilities:"
echo "  • Session persistence between Claude restarts"
echo "  • TODO tracking with priorities"
echo "  • Problem/solution documentation"
echo "  • Decision tracking"
echo "  • Status update logging"
echo ""
echo "Try: 'What did I work on last?' or 'Show me my TODOs'"
echo ""
if [ -f ".claude-memory.backup.db" ]; then
    echo "Note: Your original database was backed up to .claude-memory.backup.db"
fi
```

---

After running this update, Claude will have full memory capabilities in this project, remembering not just your code but also your decisions, TODOs, and work context between sessions.