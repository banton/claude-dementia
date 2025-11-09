# CLAUDE.md - Claude Dementia Development Guide

> **Claude Code Development Guide for the Dementia MCP Server - a persistent memory system for Claude that works across sessions using PostgreSQL/NeonDB.**

## 🧠 What is Claude Dementia?

Claude Dementia is an MCP (Model Context Protocol) server that gives Claude persistent memory between sessions. Instead of forgetting everything when a conversation ends, Claude can:

- **Lock contexts** with perfect recall (API specs, configs, decisions)
- **Search memory** semantically and by keywords
- **Track sessions** with automatic handovers
- **Isolate projects** with per-project PostgreSQL schemas
- **Scan codebases** automatically to understand file structure

## 🏗️ Project Architecture

### Technology Stack
```yaml
language: Python 3.8+
database: PostgreSQL (NeonDB for production)
embedding_provider: Voyage AI (voyage-3.5-lite, 1024 dims)
llm_provider: OpenRouter (claude-3.5-haiku)
mcp_protocol: Anthropic MCP SDK
deployment: DigitalOcean App Platform

disabled_features:
  - SQLite (code preserved, PostgreSQL-only mode)
  - Ollama (code preserved, cloud APIs only)
```

### Key Files
```
claude_mcp_hybrid_sessions.py   # Main MCP server (sessions enabled)
postgres_adapter.py              # PostgreSQL abstraction layer
server_hosted.py                 # FastAPI hosted API server
mcp_session_store.py            # Session persistence
mcp_session_middleware.py       # Session middleware
mcp_session_cleanup.py          # Background cleanup
src/config.py                   # Configuration (PostgreSQL + Voyage + OpenRouter)
src/services/                   # Service layer (embedding, LLM, etc.)
```

### Database Schema (PostgreSQL)
```sql
-- Each project gets isolated schema: dementia_<project_hash>
CREATE SCHEMA dementia_abc123;

-- Core tables in each schema:
sessions              -- Session tracking
context_locks         -- Versioned immutable contexts
memory_entries        -- Categorized memories
file_tags            -- File semantic model
context_archives     -- Deleted contexts backup
workspace_*          -- Temporary user tables
```

## 🔄 Development Workflow

### 1. Session Start
```bash
# Check git status
git status
git log --oneline -5

# Check current branch
git branch --show-current

# If working on a feature
git checkout -b feature/descriptive-name
```

### 2. Understanding the Codebase
```bash
# Main server files
cat claude_mcp_hybrid_sessions.py    # MCP tools implementation
cat postgres_adapter.py               # Database layer
cat server_hosted.py                 # Hosted API

# Configuration
cat src/config.py                    # Environment config
cat .env.example                     # Required env vars

# Documentation
cat docs/SESSION_MANAGEMENT_ENHANCEMENTS.md
cat README.md
```

### 3. Testing Workflow (TDD)
```bash
# Run specific test
python3 -m pytest tests/test_specific.py -v

# Run all tests
python3 -m pytest tests/ -v

# Test with coverage
python3 -m pytest --cov=. tests/
```

### 4. Making Changes
```bash
# Write tests first (RED)
# Edit: tests/test_new_feature.py
python3 -m pytest tests/test_new_feature.py  # Should fail

# Implement feature (GREEN)
# Edit: claude_mcp_hybrid_sessions.py or relevant file
python3 -m pytest tests/test_new_feature.py  # Should pass

# Refactor (REFACTOR)
# Improve code while keeping tests green
python3 -m pytest tests/  # All should pass
```

### 5. Committing
```bash
# Stage changes selectively
git add -p

# Commit with conventional format
git commit -m "feat(sessions): add session fork capability"
git commit -m "fix(postgres): correct schema isolation bug"
git commit -m "test(handover): add handover loading tests"

# Push to remote
git push origin feature/descriptive-name
```

## 🎯 Common Development Tasks

### Adding a New MCP Tool

1. **Design the API** (docs first)
```markdown
## Tool: `new_tool_name(param1, param2)`

**Purpose:** What it does

**Parameters:**
- param1: Description
- param2: Description

**Returns:** JSON with...

**Example:**
```python
new_tool_name("value1", "value2")
```
```

2. **Write tests** (tests/test_new_tool.py)
```python
def test_new_tool_basic():
    """Test basic functionality."""
    # Arrange
    db = setup_test_db()

    # Act
    result = new_tool_name("test")

    # Assert
    assert result["status"] == "success"
```

3. **Implement in claude_mcp_hybrid_sessions.py**
```python
@server.call_tool()
async def new_tool_name(
    arguments: dict
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Tool implementation."""
    try:
        # Implementation
        return [TextContent(type="text", text=json.dumps(result))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
```

### Working with PostgreSQL

```python
# Get adapter instance
from postgres_adapter import PostgreSQLAdapter
adapter = PostgreSQLAdapter()  # Uses DATABASE_URL env var

# Execute query
result = adapter.execute_query(
    "SELECT * FROM context_locks WHERE label = %s",
    params=["api_spec"]
)

# Execute with transaction
adapter.execute_update(
    "INSERT INTO context_locks (label, content) VALUES (%s, %s)",
    params=["new_lock", "content"]
)
```

### Testing Session Management

```python
# Test session creation
from mcp_session_store import MCPSessionStore
store = MCPSessionStore(database_url="postgresql://...")

session_id = await store.create_session(user_id="test_user")
assert session_id

# Test session retrieval
session = await store.get_session(session_id)
assert session["status"] == "active"

# Test cleanup
await store.cleanup_expired_sessions()
```

## 📝 Code Style Guidelines

### Python Conventions
- Use `snake_case` for functions and variables
- Use `PascalCase` for classes
- Type hints for all function parameters
- Docstrings for all public functions
- Maximum line length: 100 characters

### Error Handling
```python
# Always return JSON errors in MCP tools
try:
    result = perform_operation()
    return [TextContent(type="text", text=json.dumps(result))]
except Exception as e:
    error_response = {
        "error": str(e),
        "type": type(e).__name__,
        "status": "failed"
    }
    return [TextContent(type="text", text=json.dumps(error_response))]
```

### SQL Queries
```python
# Use parameterized queries (NEVER string interpolation)
# GOOD
cursor.execute("SELECT * FROM table WHERE id = %s", [user_id])

# BAD (SQL injection risk!)
cursor.execute(f"SELECT * FROM table WHERE id = '{user_id}'")
```

## 🚨 Important Constraints

### Database
- **PostgreSQL ONLY**: No SQLite code in new features
- **Schema isolation**: Each project gets its own schema
- **Connection pooling**: Use shared pool via postgres_adapter
- **Transactions**: Use for multi-statement operations

### API Keys
- **Never commit secrets**: Use .env files
- **Required keys**:
  - `DATABASE_URL`: PostgreSQL connection string
  - `VOYAGEAI_API_KEY`: For embeddings
  - `OPENROUTER_API_KEY`: For AI summarization

### MCP Tools
- **Always return JSON**: Use `json.dumps()`
- **Handle errors gracefully**: Return error objects, don't throw
- **Document thoroughly**: Update README.md and docs/
- **Test extensively**: Unit + integration tests

## 🔍 Debugging Tips

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Database Connection
```bash
# Test connection
python3 -c "
from postgres_adapter import PostgreSQLAdapter
adapter = PostgreSQLAdapter()
print('Connected:', adapter.test_connection())
"
```

### Inspect Session State
```bash
# Check active sessions
python3 -c "
import asyncio
from mcp_session_store import MCPSessionStore
store = MCPSessionStore()
sessions = asyncio.run(store.get_active_sessions())
print(f'Active sessions: {len(sessions)}')
"
```

### View PostgreSQL Schemas
```sql
-- Connect to database
psql $DATABASE_URL

-- List all schemas
\dn

-- List tables in a schema
\dt dementia_abc123.*

-- View table structure
\d dementia_abc123.context_locks
```

## 📚 Key Documentation Files

### Architecture & Design
- `docs/SESSION_MANAGEMENT_ENHANCEMENTS.md` - Session system details
- `HOSTED_SERVICE_ARCHITECTURE.md` - Cloud deployment architecture
- `MULTI_PROJECT_ISOLATION.md` - Project isolation design
- `DEPLOYMENT.md` - Deployment procedures

### Features
- `FILE_SEMANTIC_MODEL_DESIGN.md` - File scanning system
- `SQL_TOOLS_DESIGN.md` - Database tools design
- `WORKSPACE_TABLES.md` - Temporary tables feature

### Testing & Operations
- `TESTING_GUIDE.md` - How to test
- `CLOUD_TESTING_SUMMARY.md` - Cloud testing results
- `SAFE_WORKFLOW_CLAUDE_DESKTOP.md` - Local testing workflow

## 🎓 Development Principles

### 1. Test-Driven Development
- Write tests BEFORE implementation
- Tests should be deterministic (no random data)
- Mock external dependencies (APIs, time, etc.)

### 2. Immutable Tests
```python
# GOOD - Fixed test data
def test_lock_context():
    content = "API_KEY = 'test_key_123'"
    result = lock_context(content, "api_config")
    assert result["topic"] == "api_config"

# BAD - Non-deterministic
def test_lock_context():
    content = f"timestamp = {time.time()}"  # Changes every run!
    result = lock_context(content, "api_config")
```

### 3. API-First Design
- Design API contracts before implementation
- Document endpoints/tools with examples
- Use type hints and validation

### 4. Security First
- No secrets in code
- Parameterized SQL queries only
- Validate all user input
- Use read-only queries where possible

## ✅ Pre-Commit Checklist

Before committing code:
- [ ] Tests passing (`pytest tests/`)
- [ ] No hardcoded secrets or API keys
- [ ] Type hints on all functions
- [ ] Docstrings on public functions
- [ ] README.md updated if public API changed
- [ ] Git commit message follows convention
- [ ] Code follows style guidelines
- [ ] Error handling is comprehensive

## 🚀 Quick Reference Commands

```bash
# Run MCP server locally
./claude-dementia-server.sh

# Run hosted API server
python3 server_hosted.py

# Run tests
python3 -m pytest tests/ -v

# Check code style
python3 -m flake8 *.py

# Format code
python3 -m black *.py

# Database migrations
python3 migrate_v4_1_rlm.py

# Test PostgreSQL connection
python3 -c "from postgres_adapter import PostgreSQLAdapter; print(PostgreSQLAdapter().test_connection())"
```

## 🔗 Important Links

- **GitHub Repo**: https://github.com/banton/claude-dementia
- **MCP Protocol**: https://github.com/anthropics/mcp
- **NeonDB Docs**: https://neon.tech/docs
- **Voyage AI Docs**: https://docs.voyageai.com
- **OpenRouter Docs**: https://openrouter.ai/docs

---

**Remember**: This is a production system. Write tests first, handle errors gracefully, and never commit secrets.

**Current Version**: 4.2.0
**Database**: PostgreSQL (Neon)
**Protocol**: MCP (Model Context Protocol)
**Last Updated**: November 2025
