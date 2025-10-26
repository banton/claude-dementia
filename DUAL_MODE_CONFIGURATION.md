# Dual-Mode Configuration: Local vs Online

Claude Dementia now supports two operational modes with a single configuration flag:

1. **Local Mode**: SQLite + Ollama (free, requires local setup)
2. **Online Mode**: PostgreSQL + Voyage AI + OpenRouter (paid, cloud-hosted)

## Quick Start

### Switch to Online Mode (Default)

```bash
# .env file
DATABASE_MODE=postgresql
EMBEDDING_PROVIDER=voyage_ai
LLM_PROVIDER=openrouter
```

### Switch to Local Mode

```bash
# .env file
DATABASE_MODE=sqlite
EMBEDDING_PROVIDER=ollama
LLM_PROVIDER=ollama
```

## Configuration Reference

### Environment Variables

| Variable | Local Mode | Online Mode |
|----------|-----------|-------------|
| `DATABASE_MODE` | `sqlite` | `postgresql` |
| `DATABASE_URL` | (not used) | PostgreSQL connection string |
| `EMBEDDING_PROVIDER` | `ollama` | `voyage_ai` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | `voyage-3.5-lite` |
| `EMBEDDING_DIMENSIONS` | `768` | `1024` |
| `LLM_PROVIDER` | `ollama` | `openrouter` |
| `LLM_MODEL` | `mistral` / `qwen2.5-coder:1.5b` | `anthropic/claude-3.5-haiku` |

### API Keys (Online Mode Only)

```bash
VOYAGEAI_API_KEY=pa-xxxxx
OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

## Mode Comparison

### Local Mode (SQLite + Ollama)

**Pros:**
- ✅ Free (no API costs)
- ✅ Works offline
- ✅ Fast embedding generation (local GPU)
- ✅ Complete privacy (data never leaves your machine)

**Cons:**
- ❌ Requires Ollama installation and model downloads
- ❌ Limited to single machine (no cloud sync)
- ❌ SQLite database per project (file-based)
- ❌ Slower LLM responses (CPU-based)

**Setup Requirements:**
1. Install Ollama: `brew install ollama` (macOS)
2. Pull models:
   ```bash
   ollama pull nomic-embed-text
   ollama pull mistral
   ```
3. Start Ollama: `ollama serve`

### Online Mode (PostgreSQL + Voyage AI + OpenRouter)

**Pros:**
- ✅ No local setup required
- ✅ Multi-tenant schema isolation (perfect for hosted service)
- ✅ Connection pooling (1-10 concurrent connections)
- ✅ Fast, high-quality embeddings (Voyage AI)
- ✅ Fast, high-quality LLM (Claude 3.5 Haiku via OpenRouter)
- ✅ Accessible from anywhere

**Cons:**
- ❌ Requires paid API keys
- ❌ Internet connection required
- ❌ Data stored in cloud (Neon PostgreSQL)

**Estimated Costs (Monthly):**
- Voyage AI: ~$5-10 (embeddings)
- OpenRouter: ~$5-15 (LLM calls)
- Neon PostgreSQL: $0-19 (Free tier: 0.5GB, Launch: $19/month)
- **Total: ~$10-45/month** (vs $0 for local mode)

## Database Isolation

### SQLite Mode (Local)

- One database file per project: `~/.claude-dementia/{hash}.db`
- Hash-based isolation via working directory
- File-based storage (no network access)
- Supports multiple projects via path mapping

### PostgreSQL Mode (Online)

- Multi-tenant schema-based isolation
- Schema naming:
  - Priority 1: `DEMENTIA_SCHEMA` env var (explicit)
  - Priority 2: `user_{USER_ID}_project_{PROJECT_NAME}`
  - Priority 3: `project_{PROJECT_NAME}` (if no user ID)
  - Priority 4: `local_{hash}` (fallback)
- Complete data isolation between schemas
- Shared database instance with separate namespaces

**Example Schema Names:**
```
user_alice_project_innkeeper
user_alice_project_linkedin
user_bob_project_blog
project_shared_docs
local_5ac15a2e
```

## Testing Both Modes

### Test Online Mode

```bash
# Set environment
export DEMENTIA_USER_ID=test_user
export DEMENTIA_PROJECT_NAME=test_online_mode
export DATABASE_MODE=postgresql

# Test connection
python3 -c "
import claude_mcp_hybrid
conn = claude_mcp_hybrid.get_db()
print(f'Connected: {type(conn).__name__}')
conn.close()
"
```

Expected output:
```
✅ PostgreSQL connection pool initialized (schema: user_test_user_project_test_online_mode)
✅ Schema 'user_test_user_project_test_online_mode' ready with all tables
✅ PostgreSQL mode enabled (schema: user_test_user_project_test_online_mode)
Connected: AutoClosingPostgreSQLConnection
```

### Test Local Mode

```bash
# Set environment
export DEMENTIA_USER_ID=test_user
export DEMENTIA_PROJECT_NAME=test_local_mode
export DATABASE_MODE=sqlite

# Test connection
python3 -c "
import claude_mcp_hybrid
conn = claude_mcp_hybrid.get_db()
print(f'Connected: {type(conn).__name__}')
conn.close()
"
```

Expected output:
```
Connected: AutoClosingConnection
```

## Implementation Details

### Connection Handling

Both modes return **dict-like rows** for compatibility:

```python
# SQLite mode
conn = get_db()  # Returns AutoClosingConnection
cur = conn.cursor()
cur.execute("SELECT * FROM sessions")
row = cur.fetchone()
print(row['id'])  # Dict-like access via sqlite3.Row

# PostgreSQL mode
conn = get_db()  # Returns AutoClosingPostgreSQLConnection
cur = conn.cursor()  # RealDictCursor
cur.execute("SELECT * FROM sessions")
row = cur.fetchone()
print(row['id'])  # Dict-like access via RealDictCursor
```

### Auto-Closing Behavior

**SQLite:**
- `AutoClosingConnection` closes the connection when garbage collected

**PostgreSQL:**
- `AutoClosingPostgreSQLConnection` returns connection to pool (not closed)
- Pool managed by `postgres_adapter.PostgreSQLAdapter`
- Min 1 connection, Max 10 connections

### Fallback Logic

If PostgreSQL initialization fails, the system automatically falls back to SQLite:

```python
try:
    _postgres_adapter = PostgreSQLAdapter(...)
    _postgres_adapter.ensure_schema_exists()
    print("✅ PostgreSQL mode enabled")
except Exception as e:
    print(f"⚠️  PostgreSQL initialization failed: {e}")
    print(f"   Falling back to SQLite mode")
    config.database_mode = 'sqlite'
    _postgres_adapter = None
```

## Production Recommendations

### For Local Development
- Use **Local Mode** (SQLite + Ollama)
- Free, fast, private
- Perfect for development and testing

### For Hosted Service
- Use **Online Mode** (PostgreSQL + Voyage AI + OpenRouter)
- Multi-tenant isolation required
- Connection pooling for performance
- Cloud-native architecture

### For Hybrid Deployment
- Development: Local mode
- Staging: Online mode (test schema)
- Production: Online mode (production schema)

## Troubleshooting

### PostgreSQL Won't Connect

```bash
# Check DATABASE_URL
echo $DATABASE_URL

# Test connection directly
psql "$DATABASE_URL"

# Check schema exists
psql "$DATABASE_URL" -c "SELECT schema_name FROM information_schema.schemata;"
```

### Ollama Not Working

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Check models are installed
ollama list

# Pull missing models
ollama pull nomic-embed-text
ollama pull mistral
```

### Wrong Mode Active

```bash
# Check current config
python3 -c "
from src.config import config
import json
print(json.dumps(config.to_dict(), indent=2))
"
```

## Migration Between Modes

### Local → Online

1. Export SQLite data (if needed):
   ```bash
   sqlite3 ~/.claude-dementia/{hash}.db .dump > backup.sql
   ```

2. Update .env:
   ```bash
   DATABASE_MODE=postgresql
   EMBEDDING_PROVIDER=voyage_ai
   LLM_PROVIDER=openrouter
   ```

3. Restart MCP server

### Online → Local

1. Update .env:
   ```bash
   DATABASE_MODE=sqlite
   EMBEDDING_PROVIDER=ollama
   LLM_PROVIDER=ollama
   ```

2. Ensure Ollama running:
   ```bash
   ollama serve
   ```

3. Restart MCP server

## Summary

| Feature | Local Mode | Online Mode |
|---------|-----------|------------|
| **Database** | SQLite (file-based) | PostgreSQL (cloud) |
| **Embeddings** | Ollama (local) | Voyage AI (API) |
| **LLM** | Ollama (local) | OpenRouter (API) |
| **Cost** | Free | ~$10-45/month |
| **Setup** | Ollama install | API keys only |
| **Performance** | Local GPU | Cloud API |
| **Multi-tenant** | No | Yes (schema-based) |
| **Best For** | Development | Production hosting |

---

**Current Status:**
- ✅ Both modes fully implemented
- ✅ Automatic fallback (PostgreSQL → SQLite)
- ✅ Connection pooling (PostgreSQL)
- ✅ Multi-tenant isolation (PostgreSQL)
- ✅ Compatible row formats (dict-like)
- ✅ Tested and working

**Configuration:**
- Edit `.env` to switch modes
- Restart MCP server after changes
- Check `wake_up()` output to verify active mode
