# Claude Dementia v4.0.0-rc1 - Installation Guide

Claude Dementia is an MCP server that gives Claude persistent memory across sessions, with intelligent project understanding and context management.

## Requirements

- Python 3.8 or higher
- pip package manager
- Claude Desktop or Claude Code with MCP support

## Installation for Claude Code

### Step 1: Clone or Update

**For new installation:**
```bash
git clone https://github.com/banton/claude-dementia.git
cd claude-dementia
```

**For updating existing installation:**
```bash
# Check if Claude Dementia is already installed
if [ -f "$HOME/Library/Application Support/Claude/claude_desktop_config.json" ]; then
    grep -q "dementia" "$HOME/Library/Application Support/Claude/claude_desktop_config.json" && echo "✅ Found existing installation"
fi

# Update to latest version
cd /path/to/claude-dementia
git pull origin main

# Or replace with fresh copy
rm -rf /path/to/claude-dementia
git clone https://github.com/banton/claude-dementia.git
cd claude-dementia
```

### Step 2: Install Python dependencies

```bash
pip install mcp
```

### Step 3: Make scripts executable

```bash
chmod +x claude-dementia-server.sh
```

### Step 4: Configure Claude

Add to your Claude configuration file:

**For macOS/Linux:**
Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (Claude Desktop) or `~/.claude/mcp.json` (Claude Code)

```json
{
  "mcpServers": {
    "dementia": {
      "command": "/absolute/path/to/claude-dementia/claude-dementia-server.sh"
    }
  }
}
```

**For Windows:**
Edit `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "dementia": {
      "command": "python",
      "args": ["C:\\path\\to\\claude-dementia\\claude_mcp_hybrid.py"]
    }
  }
}
```

### Step 5: Restart Claude

Restart Claude Desktop or Claude Code to load the MCP server.

## Installation in Your Project

To add Claude Dementia memory to your project:

### Option 1: Copy Core Files (Recommended)

```bash
# From your project root
curl -o CLAUDE.md https://raw.githubusercontent.com/banton/claude-dementia/main/CLAUDE.md
curl -o .gitignore-append https://raw.githubusercontent.com/banton/claude-dementia/main/.gitignore
cat .gitignore-append >> .gitignore && rm .gitignore-append
```

### Option 2: Use System-Wide Installation

If you've installed Claude Dementia globally (Step 1-4 above), it will automatically:
- Detect project directories (has .git, package.json, etc.)
- Create `.claude-memory.db` in your project root
- Or use `~/.claude-dementia/{hash}.db` for non-project directories

## Usage

Once installed, Claude will have access to these memory tools:

### Session Management
- `wake_up()` - Start session, load context
- `sleep()` - End session with summary

### Memory Operations
- `memory_update(category, content)` - Track progress/decisions/errors
- `memory_status()` - View memory statistics
- `search_semantic(query)` - Search all memory

### Context Locking
- `lock_context(content, topic)` - Save immutable snapshots
- `recall_context(topic)` - Perfect recall of locked content
- `list_topics()` - View all locked contexts

### Project Intelligence
- `project_update()` - Scan and tag all files intelligently
- `project_status()` - View project insights
- `file_insights(path)` - Get recommendations for specific files
- `search_by_tags(query)` - Find files by metadata

### Example Workflow

```python
# Start your day
wake_up()

# Track your work
memory_update("progress", "Implemented authentication system")

# Lock important context
lock_context("API_KEY = os.environ['SECRET']", "api_config")

# Search for context
search_semantic("authentication")

# Analyze project
project_update()
search_by_tags("quality:has-mock-data")

# End session
sleep()
```

## Features

### Smart File Tagging
Automatically detects and tags:
- **Status**: deprecated, poc, beta, stable
- **Domain**: auth, payment, user, admin, api
- **Layer**: model, view, controller, service, test
- **Quality**: needs-work, has-mock-data, has-placeholder-data, has-dev-urls

### Mock Data Detection
Finds development artifacts Claude often creates:
- Mock/dummy/fake/sample data
- Placeholder values (foo/bar/test@example)
- Localhost/development URLs
- Hardcoded values and magic numbers

### Per-Project Isolation
- Project directories get local `.claude-memory.db`
- Non-project contexts use `~/.claude-dementia/{hash}.db`
- Complete isolation between projects

## Files Included

- `claude_mcp_hybrid.py` - The MCP server
- `claude-dementia-server.sh` - Launch script
- `CLAUDE.md` - Project guide for Claude
- `.gitignore` - Excludes memory database
- `README.md` - Documentation

## Troubleshooting

### "Unexpected token" error in Claude
The server is outputting non-JSON. Ensure no print statements in claude_mcp_hybrid.py.

### Memory not persisting
Check database location with `wake_up()` - shows where memory is stored.

### Can't find tools
Ensure MCP server is configured correctly and Claude was restarted.

### "Unable to open database file" error
- v4.0.0-rc1 fixes automatic database path detection
- For project directories: creates `.claude-memory.db` in project root
- For non-project directories: uses `~/.claude-dementia/{hash}.db`

### "Permission denied" errors during scanning
- v4.0.0-rc1 adds boundary protection to prevent scanning outside project
- Symlinks are automatically skipped to prevent escaping project directory

### "Database is locked" error
- v4.0.0-rc1 uses SQLite WAL mode for better concurrency
- Auto-closing connections prevent lock retention

### project_update times out
- v4.0.0-rc1 limits scanning to 500 files to prevent timeout
- Large projects are handled gracefully

## Support

Report issues at: https://github.com/banton/claude-dementia/issues