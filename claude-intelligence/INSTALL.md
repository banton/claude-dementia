# Claude Intelligence - Installation

## One-Line Install

```bash
curl -sSL https://raw.githubusercontent.com/banton/claude-dementia/main/claude-intelligence/install.sh | bash
```

## Manual Install

1. **Download the server:**
```bash
mkdir -p ~/.claude-intelligence
curl -sSL https://raw.githubusercontent.com/banton/claude-dementia/main/claude-intelligence/mcp_server.py \
  -o ~/.claude-intelligence/mcp_server.py
```

2. **Optional: Install xxhash for better performance:**
```bash
pip install xxhash
```

3. **Test it:**
```bash
cd your-project
python3 ~/.claude-intelligence/mcp_server.py
```

## MCP Configuration

Add to your MCP config file:

```json
{
  "claude-intelligence": {
    "command": "python3",
    "args": ["~/.claude-intelligence/mcp_server.py"],
    "description": "Project memory for Claude Code"
  }
}
```

## Usage

Once installed, Claude will automatically:
- Detect your project's tech stack
- Index and search files by content
- Track changes between sessions
- Remember what you worked on

### Available MCP Tools

- `understand_project()` - Get project overview and tech stack
- `find_files(query)` - Search files by content
- `recent_changes()` - See what changed since last session

## Requirements

- Python 3.8+
- SQLite3 (included with Python)
- Optional: xxhash for faster hashing

## Uninstall

```bash
rm -rf ~/.claude-intelligence
```

## Support

Issues: https://github.com/banton/claude-dementia/issues