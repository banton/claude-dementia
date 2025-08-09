# MCP Server Setup for Claude Intelligence

## What is MCP?

MCP (Model Context Protocol) is how Claude Code communicates with external tools and services. Claude Intelligence can run as an MCP server for proper integration.

## Installation Options

### Option 1: Standalone Mode (Current)
Just copy the files into your project and import them directly. This works but doesn't persist between Claude restarts.

### Option 2: MCP Server Mode (Recommended)
Install as a proper MCP server that Claude automatically starts with each session.

## MCP Server Installation

### 1. Install Claude Intelligence
```bash
curl -sSL https://raw.githubusercontent.com/banton/claude-dementia/feature/claude-intelligence/claude-intelligence/install.sh | bash
```

This installs to `~/.claude-intelligence/`

### 2. Configure Claude

Find your Claude configuration file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Add the Claude Intelligence server to the `mcpServers` section:

```json
{
  "mcpServers": {
    "claude-intelligence": {
      "command": "python3",
      "args": ["/Users/YOUR_USERNAME/.claude-intelligence/mcp_wrapper.py"],
      "description": "Persistent memory - file search, TODOs, session tracking",
      "alwaysAllow": [
        "understand_project",
        "find_files",
        "recent_changes", 
        "restore_session",
        "get_todos"
      ]
    }
  }
}
```

**Important**: Replace `/Users/YOUR_USERNAME` with your actual home directory path.

### 3. Restart Claude

After updating the config, restart Claude Desktop for the changes to take effect.

## Verify Installation

Once configured, Claude will automatically have access to these tools:

- `understand_project()` - Get project overview and tech stack
- `find_files(query)` - Search files by content/meaning
- `recent_changes()` - See what changed since last session
- `add_update(message)` - Log status updates
- `add_todo(content)` - Track TODOs
- `get_todos()` - List current TODOs
- `restore_session()` - Get previous session context

## How It Works

1. When Claude starts, it launches the MCP server
2. The server creates/opens `.claude-memory.db` in your project
3. Claude can call tools to read/write memory
4. Memory persists between sessions in the SQLite database

## Per-Project Memory

Each project gets its own `.claude-memory.db` file, so:
- Memory is project-specific
- No cross-contamination between projects
- Add `.claude-memory.db` to `.gitignore` to keep it local

## Troubleshooting

### Server not starting
- Check Python path: `which python3`
- Verify installation: `ls ~/.claude-intelligence/`
- Check Claude logs for errors

### Tools not available
- Ensure Claude was restarted after config change
- Check JSON syntax in config file
- Verify file paths are absolute, not relative

### Memory not persisting
- Check if `.claude-memory.db` exists in project
- Verify write permissions in project directory
- Ensure server is running (check Claude's MCP status)

## Manual Testing

Test the MCP server directly:
```bash
cd your-project
python3 ~/.claude-intelligence/mcp_wrapper.py
```

Then send JSON-RPC commands via stdin:
```json
{"jsonrpc":"2.0","method":"initialize","id":1}
{"jsonrpc":"2.0","method":"tools/invoke","params":{"name":"understand_project"},"id":2}
```

## Benefits of MCP Mode

- **Automatic startup** - No need to manually load modules
- **Consistent API** - Same tools available in every session
- **Clean separation** - Server runs independently of Claude
- **Better performance** - Server stays running between tool calls
- **Proper lifecycle** - Initializes and cleans up correctly