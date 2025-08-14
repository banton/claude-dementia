# Install or Update Claude Dementia MCP Server

Please help me install or update Claude Dementia - an MCP server that gives you persistent memory across sessions.

## What You Should Do

### 1. Check for Existing Installation

First, check if I already have Claude Dementia or another memory system installed:

```bash
# Check for existing MCP configuration
if [ -f "$HOME/Library/Application Support/Claude/claude_desktop_config.json" ]; then
    echo "Checking Claude Desktop config..."
    grep -q "dementia" "$HOME/Library/Application Support/Claude/claude_desktop_config.json" && echo "✅ Found Claude Dementia" || echo "❌ Not found in Desktop"
fi

if [ -f "$HOME/.claude/mcp.json" ]; then
    echo "Checking Claude Code config..."
    grep -q "dementia" "$HOME/.claude/mcp.json" && echo "✅ Found Claude Dementia" || echo "❌ Not found in Code"
fi

# Check for old file-based memory system
if [ -d "./memory" ] && [ -f "./CLAUDE.md" ]; then
    echo "⚠️ Found old file-based memory system - needs migration to MCP"
fi
```

### 2. Install or Update

**If NOT installed (new installation):**

```bash
# Clone the repository
git clone https://github.com/banton/claude-dementia.git ~/claude-dementia
cd ~/claude-dementia

# Install Python dependencies
pip install mcp

# Make script executable
chmod +x claude-dementia-server.sh

# Get the full path for configuration
echo "Installation path: $(pwd)"
```

**If already installed (update):**

```bash
# Find existing installation
INSTALL_PATH=$(grep -l "claude-dementia" "$HOME/Library/Application Support/Claude/claude_desktop_config.json" 2>/dev/null | xargs grep -o '"command":\s*"[^"]*' | cut -d'"' -f4 | xargs dirname 2>/dev/null)

if [ -z "$INSTALL_PATH" ]; then
    INSTALL_PATH="$HOME/claude-dementia"  # Default location
fi

echo "Found installation at: $INSTALL_PATH"

# Update to latest version
cd "$INSTALL_PATH"
git pull origin main

# Or do a clean reinstall
# rm -rf "$INSTALL_PATH"
# git clone https://github.com/banton/claude-dementia.git "$INSTALL_PATH"
```

### 3. Configure Claude

Add or update the configuration:

**For Claude Desktop:**
Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dementia": {
      "command": "/absolute/path/to/claude-dementia/claude-dementia-server.sh"
    }
  }
}
```

**For Claude Code:**
Edit `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "dementia": {
      "command": "/absolute/path/to/claude-dementia/claude-dementia-server.sh"
    }
  }
}
```

### 4. Migrate Old Memory System (if applicable)

If you find the old file-based memory system:

```bash
# Remove old file-based memory system
rm -rf ./memory
rm -f ./CLAUDE.md

# The new MCP system will automatically:
# - Create .claude-memory.db in project directories
# - Or use ~/.claude-dementia/{hash}.db for non-projects
```

### 5. Restart Claude

After configuration, restart Claude Desktop or Claude Code.

## Test the Installation

Once restarted, test with these commands:

```python
# Start a session
wake_up()

# You should see:
# 🌅 Good morning! Loading your context...
# Session: [id]
# Context: [project name]
# Memory: [database location]

# If you see this, installation is successful!
```

## Features You Now Have

- `wake_up()` / `sleep()` - Session management
- `memory_update()` - Track progress, decisions, errors
- `lock_context()` / `recall_context()` - Perfect recall of important info
- `project_update()` - Intelligent file analysis and tagging
- `search_by_tags("quality:has-mock-data")` - Find dev artifacts
- `what_needs_attention()` - See issues and TODOs

## Key Improvements in This Version

1. **MCP Protocol** - No more Python script approval prompts
2. **Smart Database Location** - Projects get local DB, Desktop uses cache
3. **Mock Data Detection** - Finds placeholder values Claude creates
4. **Better Semantics** - "quality:needs-work" instead of "has-todos"
5. **Project Isolation** - No context bleeding between projects

## Need Help?

If you encounter issues:
1. Check database location with `wake_up()`
2. Ensure MCP config has correct absolute path
3. Report issues at: https://github.com/banton/claude-dementia/issues