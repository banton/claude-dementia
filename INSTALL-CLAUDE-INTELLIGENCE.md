# Install Claude Intelligence in My Project

Copy this prompt and paste it into Claude Code when you're in your project directory:

---

Please install Claude Intelligence (a project memory system) in my current project by copying it from my local development folder. Follow these steps:

1. First, check if we're in a git repository and note the current directory:
```bash
pwd
git status 2>/dev/null || echo "Not a git repo"
```

2. Copy the Claude Intelligence files from my local development:
```bash
# Copy the core files
cp /Users/banton/Sites/claude-dementia/claude-intelligence/mcp_server.py ./
cp /Users/banton/Sites/claude-dementia/claude-intelligence/test_mcp_server.py ./
cp /Users/banton/Sites/claude-dementia/claude-intelligence/demo.py ./
cp /Users/banton/Sites/claude-dementia/claude-intelligence/requirements.txt ./claude-intelligence-requirements.txt

# Create a local README for Claude Intelligence
cat > CLAUDE-INTELLIGENCE-README.md << 'EOF'
# Claude Intelligence - Project Memory

This project now has Claude Intelligence installed, giving Claude persistent memory of:
- Your tech stack and frameworks
- File contents and structure (searchable)
- Changes between sessions
- Git history and modifications

## How It Works

Claude Intelligence creates `.claude-memory.db` (SQLite database) that tracks:
- File contents indexed with FTS5 full-text search
- Session boundaries to know what changed
- Your technology stack
- Git commits and changes

## Usage

When Claude Code starts a session in this project, it can:
- Search for files by what they do: "find the payment processing code"
- Know what changed: "what files were modified since yesterday?"
- Understand your stack: "what frameworks does this project use?"

## Files Created

- `.claude-memory.db` - Local SQLite database (add to .gitignore)
- `mcp_server.py` - The intelligence server (can be deleted after setup)
- This README - Documentation for you

## Testing

Run the demo to see it work:
```bash
python3 demo.py
```

Run tests to verify:
```bash
python3 test_mcp_server.py
```

## Privacy

Everything is local. No external APIs, no cloud storage. The database only contains:
- File paths and contents from your project
- Metadata about when files were indexed
- Tech stack detection results

Add `.claude-memory.db` to your .gitignore to keep it local.
EOF

echo "✅ Claude Intelligence files copied"
```

3. Test that it works:
```bash
# Quick test
python3 -c "
from mcp_server import ClaudeIntelligence
import asyncio

async def test():
    server = ClaudeIntelligence()
    print('✅ Claude Intelligence initialized')
    
    # Index the project
    for update in server.index_progressive():
        print(f'  {update}')
    
    # Detect tech stack
    info = await server.understand_project()
    print(f\"\\n📊 Tech Stack: {', '.join(info['stack']) if info['stack'] else 'Not detected'}\" )
    print(f\"📁 Files indexed: {server.file_count}\")
    
    # Test search
    if server.file_count > 0:
        results = await server.find_files('test', k=3)
        print(f\"🔍 Search works: Found {len(results)} results for 'test'\")

asyncio.run(test())
"
```

4. Add the database to .gitignore:
```bash
echo "" >> .gitignore
echo "# Claude Intelligence local memory" >> .gitignore
echo ".claude-memory.db" >> .gitignore
echo "mcp_server.py" >> .gitignore
echo "test_mcp_server.py" >> .gitignore
echo "demo.py" >> .gitignore
echo "claude-intelligence-requirements.txt" >> .gitignore
echo "" >> .gitignore
echo "✅ Added to .gitignore"
```

5. Create a CLAUDE.md file for this project if it doesn't exist:
```bash
if [ ! -f CLAUDE.md ]; then
cat > CLAUDE.md << 'EOF'
# CLAUDE.md - Project Assistant Instructions

This project has Claude Intelligence installed for persistent memory.

## On Session Start

Load the project intelligence:
```python
from mcp_server import ClaudeIntelligence
server = ClaudeIntelligence()

# See what changed since last session
import asyncio
changes = asyncio.run(server.recent_changes())
print(changes['summary'])

# Understand the project
info = asyncio.run(server.understand_project())
print(f"Tech stack: {info['stack']}")
```

## During Development

Search for files by meaning:
```python
# Find payment-related code
results = asyncio.run(server.find_files("payment processing"))

# Find authentication logic  
results = asyncio.run(server.find_files("user login auth"))
```

## Project-Specific Notes

[Add your project-specific instructions here]
EOF
echo "✅ Created CLAUDE.md"
else
echo "ℹ️ CLAUDE.md already exists, skipping"
fi
```

6. Show me what was installed:
```bash
echo ""
echo "=== Claude Intelligence Installation Complete ==="
echo ""
echo "Installed files:"
ls -la mcp_server.py CLAUDE-INTELLIGENCE-README.md .claude-memory.db 2>/dev/null || echo "Database will be created on first run"
echo ""
echo "The project now has persistent memory for Claude!"
echo "Try asking: 'What files handle authentication?' or 'What changed since yesterday?'"
```

---

After running this, Claude will remember your project between sessions. The memory persists in `.claude-memory.db` which tracks your files, changes, and tech stack.