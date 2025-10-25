# Claude Dementia 🧠 v4.1.0

> An MCP server that gives Claude persistent memory between sessions, with powerful search, batch operations, and analytics.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-4.1.0-blue)](https://github.com/banton/claude-dementia/releases)

## What is Claude Dementia?

Claude Dementia solves the "forgetting Claude" problem - where Claude loses context between conversations. It provides:

- **Persistent Memory**: Context and progress tracked across sessions
- **Project Intelligence**: Automatic code analysis and quality detection  
- **Context Locking**: Save and recall exact information with versioning
- **Smart Isolation**: Per-project databases prevent context bleeding

## Key Features

### 🔒 Context Locking
Save important information with perfect recall:
```python
# Lock single context
lock_context("API_KEY = os.environ['SECRET']", "api_config")

# Lock multiple contexts (efficient!)
batch_lock_contexts([
    {"topic": "api_v2", "content": "...", "tags": "api,auth"},
    {"topic": "database_schema", "content": "...", "priority": "always_check"}
])

# Later, in a new session
recall_context("api_config")  # Returns exact content

# Or recall multiple at once
batch_recall_contexts(["api_config", "database_schema"])
```

### 🔍 Full-Text Search
Find contexts by content, not just name:
```python
# Simple search
search_contexts("authentication")

# Search with filters
search_contexts("JWT", priority="important", tags="api,security")

# Results include relevance scores
```

### 📊 Memory Analytics
Understand your memory usage:
```python
memory_analytics()
# Returns:
# - Overview (total contexts, size, age)
# - Most/least accessed contexts
# - Stale contexts (not accessed in 30+ days)
# - Size distribution by priority
# - Recommendations for cleanup
```

### ⚡ Cloud-Ready Performance
Optimized for cloud deployment:
- **Batch operations** reduce API round-trips
- **Structured JSON** output (token-efficient)
- **Access tracking** for usage insights
- **Staleness detection** for automatic maintenance

## Requirements

- Python 3.8 or higher
- Claude Desktop or Claude Code with MCP support
- pip package manager

## Quick Start

### 1. Install for Claude Desktop/Code

```bash
# Clone repository
git clone https://github.com/banton/claude-dementia.git
cd claude-dementia

# Install dependencies
pip install mcp

# Make scripts executable (macOS/Linux)
chmod +x claude-dementia-server.sh
```

### 2. Configure Claude

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dementia": {
      "command": "/path/to/claude-dementia/claude-dementia-server.sh"
    }
  }
}
```

### 3. Use in Claude

```python
# Start session (automatic context loading)
wake_up()
# Output: JSON with session info, git status, contexts, staleness warnings

# Lock important context
lock_context(config_code, "oauth_setup", priority="important")

# Or lock multiple contexts at once (efficient!)
batch_lock_contexts([
    {"topic": "oauth_setup", "content": config_code},
    {"topic": "api_routes", "content": routes_code}
])

# Search for related contexts
search_contexts("authentication", tags="api")

# Check memory health
memory_analytics()

# End session
sleep()  # Saves summary for next session
```

## How It Works

### Smart Database Location

Claude Dementia intelligently determines where to store memory:

1. **Project Directory** (has .git, package.json, etc.)
   - Creates `.claude-memory.db` in project root
   - Memory stays with project
   
2. **Non-Project Directory** (Desktop, random folders)
   - Creates `~/.claude-dementia/{hash}.db`
   - Each unique path gets its own database

3. **Environment Override**
   - Set `CLAUDE_MEMORY_DB=/custom/path.db` for full control

### Memory Categories

Track different types of information:
- `progress` - Work completed
- `decision` - Technical decisions made
- `error` - Issues encountered
- `todo` - Tasks to complete
- `question` - Open questions
- `insight` - Important discoveries

## Available Tools (16)

### Session Management (2)
- `wake_up()` - Initialize session, load context, check staleness
- `sleep()` - End session with handover summary

### Context Management (5)
- `lock_context(content, topic, tags, priority)` - Save immutable context
- `recall_context(topic, version)` - Retrieve context (tracks access)
- `unlock_context(topic, version)` - Remove context lock
- `check_contexts(text)` - Check relevance to current work
- `explore_context_tree(flat=False)` - Browse contexts (tree or flat list)

### Batch Operations (2) - NEW in v4.1
- `batch_lock_contexts(contexts)` - Lock multiple contexts at once
- `batch_recall_contexts(topics)` - Recall multiple contexts at once

### Search & Analytics (2) - NEW in v4.1
- `search_contexts(query, priority, tags, limit)` - Full-text search with filters
- `memory_analytics()` - Usage insights and recommendations

### Memory Operations (2)
- `memory_status()` - Memory system statistics
- `sync_project_memory()` - Sync file metadata to memory

### Database Tools (3)
- `query_database(sql)` - Safe read-only SQL queries
- `inspect_database()` - View schema and tables
- `execute_sql(sql)` - Execute write operations (admin only)

## Example Workflows

### Starting a New Feature
```python
# Initialize session
wake_up()

# Lock multiple related contexts efficiently
batch_lock_contexts([
    {"topic": "auth_requirements", "content": "...", "priority": "important"},
    {"topic": "api_endpoints", "content": "...", "tags": "api,auth"}
])

# Search for existing auth code
search_contexts("authentication", tags="api")
```

### Debugging Session
```python
# Start with context
wake_up()

# Search for related contexts
search_contexts("database connection", priority="important")

# Recall multiple contexts at once
batch_recall_contexts(["database_config", "error_handling"])

# Lock new findings
lock_context("Fixed connection pool issue...", "db_fix", priority="important")
```

### Memory Maintenance
```python
# Check memory health
analytics = memory_analytics()

# Find stale contexts
# analytics shows contexts not accessed in 30+ days

# Search for specific contexts
search_contexts("experimental", tags="poc,deprecated")

# Clean up unnecessary contexts
unlock_context("old_experiment")
```

## Project Structure

```
claude-dementia/
├── claude_mcp_hybrid.py      # MCP server implementation
├── claude-dementia-server.sh  # Launch script
├── CLAUDE.md                  # Guide for Claude
├── INSTALL.md                 # Installation guide
├── README.md                  # This file
├── example-mcp-config.json    # Example configuration
└── .gitignore                 # Excludes .claude-memory.db
```

## Database Schema

All data stored in `.claude-memory.db`:
- `sessions` - Development sessions
- `memory_entries` - Categorized memory
- `context_locks` - Version-controlled snapshots
- `file_tags` - File metadata and quality indicators
- `todos` - Task management
- `project_variables` - Project intelligence

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## Troubleshooting

### Memory not persisting between sessions
- Check database location with `wake_up()` 
- Ensure working directory is consistent

### "Unexpected token" error in Claude
- Server outputting non-JSON
- Check for print statements in code

### Can't find memory tools
- Verify MCP configuration
- Restart Claude after config changes

## License

MIT License - see [LICENSE](LICENSE) file

## Support

- **Issues**: [GitHub Issues](https://github.com/banton/claude-dementia/issues)
- **Discussions**: [GitHub Discussions](https://github.com/banton/claude-dementia/discussions)

## Acknowledgments

Built using Anthropic's [MCP (Model Context Protocol)](https://github.com/anthropics/mcp) framework.

---

## Recent Updates

### v4.1.0 - Phase 2A Tool Enhancements (January 2025)

Major update with new capabilities:
- ✅ **4 new tools**: batch operations, full-text search, analytics
- ✅ **Tool consolidation**: 24 → 16 tools (removed 12 redundant)
- ✅ **Enhanced**: `explore_context_tree()` with flat mode
- ✅ **Access tracking**: Last accessed, access count
- ✅ **Staleness detection**: Automatic context maintenance
- ✅ **Cloud-ready**: Optimized for PostgreSQL migration

**📖 See [PHASE_2A_TOOLS.md](PHASE_2A_TOOLS.md) for complete documentation and migration guide.**

---

*Claude Dementia - Because Claude shouldn't forget what you were working on.*