# Claude Dementia 🧠

> An MCP server that gives Claude persistent memory between sessions, with intelligent project understanding and context management.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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
# Lock API configuration
lock_context("API_KEY = os.environ['SECRET']", "api_config")

# Later, in a new session
recall_context("api_config")  # Returns exact content
```

### 🏷️ Intelligent File Tagging
Automatically analyzes and tags your codebase:
- **Status**: `deprecated`, `poc`, `beta`, `stable`
- **Quality**: `needs-work`, `has-mock-data`, `has-placeholder-data`
- **Domain**: `auth`, `payment`, `user`, `api`
- **Layer**: `model`, `controller`, `service`, `test`

### 🎭 Mock Data Detection
Finds development artifacts Claude often creates:
```python
project_update()  # Scans project
search_by_tags("quality:has-mock-data")  # Find all mock data
search_by_tags("quality:has-dev-urls")   # Find localhost URLs
```

### 📊 Project Insights
Get actionable recommendations:
```python
file_insights("src/api/auth.py")
# Returns:
# • Status: stable
# • Quality: needs-work, has-placeholder-data
# Recommendations:
# 🔧 Address improvement markers
# 📝 Replace placeholder values (foo/bar/test@example)
```

## Quick Start

### 1. Install for Claude Desktop/Code

```bash
# Clone repository
git clone https://github.com/banton/claude-dementia.git
cd claude-dementia

# Install dependencies
pip install mcp

# Make scripts executable
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
# Start session
wake_up()
# Output: Session loaded, showing TODOs, recent changes

# Track work  
memory_update("progress", "Implemented OAuth login")

# Lock important context
lock_context(config_code, "oauth_setup")

# Analyze project
project_update()  # Scans and tags all files
what_needs_attention()  # Shows issues to fix

# End session
sleep()  # Saves summary
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

## Available Tools

### Session Management
- `wake_up()` - Start session with context
- `sleep()` - End session with summary

### Memory Operations
- `memory_update(category, content, metadata)` - Add memory
- `memory_status()` - View statistics
- `search_semantic(query)` - Search all memory

### Context Locking
- `lock_context(content, topic, tags)` - Save snapshot
- `recall_context(topic, version)` - Retrieve content
- `list_topics()` - Show all locked contexts

### Project Intelligence  
- `project_update()` - Scan and tag files
- `project_status()` - View project insights
- `tag_path(path, tags, comment)` - Manual tagging
- `search_by_tags(query)` - Query files by tags
- `file_insights(path)` - Get file recommendations

### Smart Queries
- `what_changed()` - Recent updates
- `what_needs_attention()` - Issues requiring action
- `search_semantic(query)` - Natural language search

## Example Workflows

### Starting a New Feature
```python
wake_up()
memory_update("todo", "Implement user authentication", '{"priority": "HIGH"}')
project_update()  # Understand codebase
search_by_tags("domain:auth")  # Find auth-related files
```

### Debugging Session
```python
wake_up()
what_needs_attention()  # See errors and issues
search_semantic("database connection")  # Find related context
memory_update("error", "Connection timeout", '{"file": "db.py"}')
```

### Code Review
```python
project_update()
search_by_tags("quality:needs-work")  # Files with TODOs
search_by_tags("quality:has-mock-data")  # Find mock data
file_insights("src/main.py")  # Get specific recommendations
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

*Claude Dementia - Because Claude shouldn't forget what you were working on.*