# Claude Dementia 🧠 v4.2.0

> An MCP server that gives Claude persistent memory between sessions, with powerful search, batch operations, and analytics.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-4.2.0-blue)](https://github.com/banton/claude-dementia/releases)

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

### File Semantic Model (NEW in v4.2)

Automatic project awareness - Claude knows what files exist and what they do:

**Automatic Scanning:**
- `wake_up()` auto-scans on session start (incremental, ~20-50ms)
- `sleep()` captures final changes on session end
- Detects added, modified, and deleted files

**Three-Stage Change Detection:**
1. **mtime check** (~1ms for 1000 files) - instant filter
2. **size check** (instant) - quick confirmation
3. **hash check** (only if needed) - definitive answer
   - Full MD5 for files <1MB
   - Partial hash (first+last 64KB) for files >1MB

**Semantic Analysis:**
- File type detection (50+ types)
- Import/export extraction (Python, JavaScript, etc.)
- Standard file recognition (.env, package.json, requirements.txt)
- Warning generation (secrets in .env, unpinned dependencies)
- Automatic clustering (authentication, api, database, tests, etc.)

**Benefits:**
- Zero context rebuilding between sessions
- "Find all authentication files" queries
- "Show me files that import X" searches
- Automatic detection of config issues
- Persistent project understanding

**Example:**
```python
# Auto-scanned on wake_up
wake_up()
# Output includes: "file_model": {"changes": {"added": 5, "modified": 2}}

# Manual scan if needed
scan_project_files(full_scan=False, max_files=10000)

# Query by purpose
query_files("authentication", cluster="api")

# View semantic groupings
get_file_clusters()

# Check health
file_model_status()
```

## Available Tools (20)

### Session Management (2)
- `wake_up()` - Initialize session, load context, check staleness, **auto-scan project files**
- `sleep()` - End session with handover summary, **update file model**

### Context Management (5)
- `lock_context(content, topic, tags, priority)` - Save immutable context
- `recall_context(topic, version)` - Retrieve context (tracks access)
- `unlock_context(topic, version)` - Remove context lock
- `check_contexts(text)` - Check relevance to current work
- `explore_context_tree(flat=False)` - Browse contexts (tree or flat list)

### Batch Operations (2) - Phase 2A
- `batch_lock_contexts(contexts)` - Lock multiple contexts at once
- `batch_recall_contexts(topics)` - Recall multiple contexts at once

### Search & Analytics (2) - Phase 2A
- `search_contexts(query, priority, tags, limit)` - Full-text search with filters
- `memory_analytics()` - Usage insights and recommendations

### File Semantic Model (4) - **NEW in v4.2**
- `scan_project_files(full_scan, max_files)` - Build/update file semantic model
- `query_files(query, file_type, cluster, limit)` - Search files by content/purpose
- `get_file_clusters()` - View semantic file groupings
- `file_model_status()` - Check model health and statistics

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

### Using File Semantic Model
```python
# Automatic scan on wake_up
result = wake_up()
# Shows: "file_model": {"total_files": 156, "changes": {"added": 3, "modified": 5}}

# Find all authentication-related files
query_files("authentication", cluster="auth")
# Returns: auth.py, login.js, jwt_utils.py, etc.

# Find files that import a specific module
query_files("import sqlalchemy")

# View project structure by semantic clusters
get_file_clusters()
# Shows: authentication (15 files), api (23 files), database (8 files), tests (45 files)

# Check for configuration warnings
file_model_status()
# Warnings: ".env file not in .gitignore", "unpinned dependencies in requirements.txt"

# Manual full rescan if needed
scan_project_files(full_scan=True)
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

### v4.2.0 - File Semantic Model (January 2025)

Revolutionary project awareness system:
- ✅ **4 new tools**: scan, query, clusters, status
- ✅ **Automatic scanning**: wake_up/sleep integration
- ✅ **Three-stage change detection**: mtime → size → hash
- ✅ **Smart hashing**: Full <1MB, partial >1MB (100x faster)
- ✅ **Semantic analysis**: Imports, exports, dependencies
- ✅ **50+ file types**: Python, JavaScript, configs, docs, etc.
- ✅ **Standard file warnings**: .env, package.json, requirements.txt
- ✅ **Auto-clustering**: authentication, api, database, tests
- ✅ **~20-50ms scans**: Incremental updates only changed files
- ✅ **Persistent understanding**: Zero context rebuilding

**📖 See [FILE_SEMANTIC_MODEL_DESIGN.md](FILE_SEMANTIC_MODEL_DESIGN.md) for complete specification.**

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