# Session-Aware MCP Fork

## Overview

`claude_mcp_hybrid_sessions.py` is a fork of `claude_mcp_hybrid.py` with built-in PostgreSQL session management.

**Purpose:** Test session management and project selection locally without needing HTTP middleware.

## Key Differences

### Original (`claude_mcp_hybrid.py`)
- No session tracking
- No PostgreSQL session storage
- Tools work immediately
- No project selection required

### Fork (`claude_mcp_hybrid_sessions.py`)
- ✅ Creates PostgreSQL session on startup
- ✅ Session ID stored in `config._current_session_id`
- ✅ Session persists in `mcp_sessions` table
- ✅ Requires `select_project_for_session()` before using tools
- ✅ Same database schema as cloud version (`server_hosted.py`)

## Architecture

```
Startup Flow:
1. Initialize database adapter (PostgreSQL/Neon)
2. Generate unique session ID (uuid.uuid4().hex)
3. Create session in mcp_sessions table with project_name='__PENDING__'
4. Set config._current_session_id for tools to access
5. Start MCP server (FastMCP stdio transport)

Tool Usage Flow:
1. User calls ANY tool (e.g., lock_context)
2. Tool accesses config._current_session_id
3. Tool checks session's project_name
4. If '__PENDING__': User must call select_project_for_session() first
5. After project selected: All tools work normally
```

## Database Schema

Uses **identical** PostgreSQL schema as cloud version:

```sql
-- mcp_sessions table
CREATE TABLE mcp_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    capabilities JSONB DEFAULT '{}',
    expires_at TIMESTAMP WITH TIME ZONE,
    client_info JSONB DEFAULT '{}',
    project_name TEXT DEFAULT '__PENDING__',  -- NEW
    session_summary JSONB DEFAULT '{}'        -- NEW
)
```

## Usage

### Start the server:
```bash
# Set environment variables
export DATABASE_URL="postgresql://..."
export DEMENTIA_API_KEY="your_api_key"

# Run the session-aware fork
python3 claude_mcp_hybrid_sessions.py
```

### Expected startup output:
```
🔧 Initializing session-aware MCP server...
✅ PostgreSQL/Neon connected (schema: claude_dementia)
✅ MCP session created: 3a7f9b2e (project selection required)
📦 Session ID: 3a7f9b2e91c54da8b15c6f2a38d091fa
⚠️  Note: You must call select_project_for_session() before using other tools
```

### First tool call:
```python
# User tries any tool first
lock_context("API spec", "api_documentation")

# Tool will fail with:
# ❌ Error: Session project_name='__PENDING__'
# Must call select_project_for_session() first
```

### Project selection:
```python
# List available projects
select_project_for_session('innkeeper')

# Returns:
# ✅ Project 'innkeeper' selected
# 📦 Previous Session Handover:
# ...
# You can now use other tools.
```

### Subsequent tools work:
```python
lock_context("API spec", "api_documentation")
# ✅ Works now!
```

## Testing Workflow

### Test Project Selection:
1. Start server
2. Call `select_project_for_session('test_project')`
3. Verify session updated in database:
   ```sql
   SELECT session_id, project_name, created_at
   FROM mcp_sessions
   WHERE session_id = '...';
   ```

### Test Session Persistence:
1. Start server (creates session A)
2. Call `select_project_for_session('project1')`
3. Stop server
4. Check database - session A still exists
5. Restart server (creates new session B)
6. Both sessions A and B exist in database

### Test Tool Access:
1. Start server
2. Try calling `lock_context()` immediately
3. Should fail with project selection error
4. Call `select_project_for_session('project1')`
5. Try `lock_context()` again
6. Should succeed

## Code Changes Summary

### Added Imports (Line 71-75):
```python
from mcp_session_store import PostgreSQLSessionStore

_local_session_id = None
_session_store = None
```

### New Functions (Lines 125-173):
```python
def _init_local_session():
    """Initialize PostgreSQL session on startup"""

def _get_local_session_id():
    """Get current session ID"""

def _update_session_activity():
    """Update last_active timestamp"""
```

### Modified Main Block (Lines 8397-8407):
```python
# Before mcp.run():
session_id = _init_local_session()
print(f"📦 Session ID: {session_id}")
```

## Comparison with Cloud Version

| Feature | Local Fork | Cloud (`server_hosted.py`) |
|---------|------------|---------------------------|
| Transport | stdio/SSE | HTTP + SSE |
| Session Creation | On startup | On first HTTP request |
| Project Check | Manual (tool-level) | Automatic (middleware) |
| Error Handling | Tool returns error | Middleware returns 400 |
| Session Cleanup | Manual | Automatic (120min inactivity) |
| Database | Same (PostgreSQL) | Same (PostgreSQL) |
| Session Table | Same | Same |
| Tools | Same | Same |

## Benefits

1. **Local Testing**: Test session logic without deploying
2. **Same Database**: Uses identical schema as production
3. **Same Tools**: `select_project_for_session()` works identically
4. **Debugging**: Easier to debug than HTTP middleware
5. **Faster Iteration**: No deploy cycle needed

## Limitations

1. **No Automatic Checking**: Tools must manually check project selection
2. **No Session Timeout**: No automatic cleanup (yet)
3. **No HTTP Features**: No middleware, CORS, bearer auth, etc.
4. **Manual Cleanup**: Must manually delete old sessions

## Next Steps

To make this identical to cloud version:

1. **Auto-check project**: Wrap all tools to check `project_name != '__PENDING__'`
2. **Session timeout**: Add background task to check inactivity
3. **Session cleanup**: Auto-delete expired sessions
4. **Handover creation**: Auto-create handover on exit

## Files Modified

- `claude_mcp_hybrid_sessions.py` - Session-aware fork (NEW)
- Original `claude_mcp_hybrid.py` unchanged
- Uses existing `mcp_session_store.py`
- Uses existing `postgres_adapter.py`
- Uses existing `mcp_session_middleware.py` (for reference)

## Maintenance

**When updating:**
- Keep in sync with `claude_mcp_hybrid.py` tool implementations
- Session management code is isolated to lines 71-173 and 8397-8407
- Rest of file should match original exactly

**Git workflow:**
```bash
# To update fork with latest tools from original:
git diff claude_mcp_hybrid.py claude_mcp_hybrid_sessions.py > session_changes.patch
# Update original
git checkout main && git pull
# Apply session changes
git apply session_changes.patch
```
